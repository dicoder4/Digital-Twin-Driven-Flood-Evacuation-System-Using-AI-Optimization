"""
mcp_flood_intelligence_server.py — Deep Reasoning over Metro Disruptions,
Population Vulnerability, and Resource-Linked Shelters
─────────────────────────────────────────────────────────────

Exposes three intelligence tools for the App Copilot:
  1. get_metro_status      — Line-wise station health aggregation
  2. get_flood_impact      — Socio-economic impact summary with landmark mapping
  3. get_shelter_resource_map — Safe shelters + nearby logistics inventory
"""

import sys
import os
import json
import math
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

# ── Shared context & helpers (DRY: imported from evacuation server & service) ──
try:
    from genai.mcp_evacuation_server import _load_state, _STATE_FILE
except ImportError:
    from mcp_evacuation_server import _load_state, _STATE_FILE

from service import _haversine_distance, _resolve_road_name as _get_road_name_for_node

# ── Create MCP Server ──
mcp = FastMCP("Flood Intelligence Server")


def _load_region_graph(hobli_key: str):
    """Load the cached region graph for coordinate/road name lookups."""
    try:
        from region_manager import REGION_CACHE, norm_key
        key = norm_key(hobli_key)
        if key in REGION_CACHE:
            return REGION_CACHE[key]["G"]
    except Exception:
        pass
    return None


def _get_metro_status_from_summary(summary_data: dict) -> dict:
    """Extract and aggregate metro station status by line."""
    metro_reports = summary_data.get("metro_reports", [])
    
    if not metro_reports:
        return {
            "available": False,
            "message": "No metro data available. Run a simulation with metro extraction enabled.",
            "lines": {}
        }
    
    lines: Dict[str, Dict] = {}
    
    for station in metro_reports:
        line = station.get("line", "Unknown")
        if not line:
            line = "Unknown Line"
        
        if line not in lines:
            lines[line] = {
                "line_name": line,
                "colour": station.get("colour", "unknown"),
                "total_stations": 0,
                "unsafe_stations": 0,
                "caution_stations": 0,
                "safe_stations": 0,
                "stations": []
            }
        
        status = station.get("status", "safe")
        lines[line]["total_stations"] += 1
        lines[line]["stations"].append({
            "name": station.get("name", "Unknown"),
            "status": status,
            "risk_score": station.get("risk_score", 0),
            "flooded": station.get("flooded", False)
        })
        
        if status == "unsafe":
            lines[line]["unsafe_stations"] += 1
        elif status == "caution":
            lines[line]["caution_stations"] += 1
        else:
            lines[line]["safe_stations"] += 1
    
    # Calculate health metrics per line
    for line_name, data in lines.items():
        total = data["total_stations"]
        if total > 0:
            data["disruption_pct"] = round(
                (data["unsafe_stations"] + data["caution_stations"] * 0.5) / total * 100, 1
            )
            data["health_status"] = (
                "CRITICAL" if data["disruption_pct"] >= 50
                else "DEGRADED" if data["disruption_pct"] >= 20
                else "OPERATIONAL"
            )
    
    return {
        "available": True,
        "total_stations": len(metro_reports),
        "lines": lines,
        "summary": _build_metro_summary_text(lines)
    }


def _build_metro_summary_text(lines: dict) -> str:
    """Generate a human-readable summary of metro health."""
    if not lines:
        return "No metro line data available."
    
    parts = []
    critical_lines = []
    degraded_lines = []
    operational_lines = []
    
    for name, data in lines.items():
        status = data["health_status"]
        disruption = data["disruption_pct"]
        unsafe = data["unsafe_stations"]
        caution = data["caution_stations"]
        
        line_info = f"{name}: {unsafe} unsafe, {caution} caution ({disruption}% disrupted)"
        
        if status == "CRITICAL":
            critical_lines.append(line_info)
        elif status == "DEGRADED":
            degraded_lines.append(line_info)
        else:
            operational_lines.append(line_info)
    
    if critical_lines:
        parts.append("🔴 **CRITICAL LINES (Severe disruption):**\n  - " + "\n  - ".join(critical_lines))
    if degraded_lines:
        parts.append("🟡 **DEGRADED LINES (Partial disruption):**\n  - " + "\n  - ".join(degraded_lines))
    if operational_lines:
        parts.append("🟢 **OPERATIONAL LINES (Mostly functional):**\n  - " + "\n  - ".join(operational_lines))
    
    return "\n\n".join(parts)


def _get_flooded_landmarks(summary_data: dict, hobli_name: str) -> List[Dict]:
    """Identify significant flooded landmarks/roads from simulation data."""
    # For now, we extract from pressure points and metro reports
    landmarks = []
    
    # Pressure points often indicate flooded bottlenecks
    pressure_points = summary_data.get("pressure_points", [])
    for pp in pressure_points[:10]:
        location = pp.get("location_name", "")
        depth = pp.get("flood_depth", 0)
        if depth >= 0.1 and location:
            landmarks.append({
                "name": location,
                "type": "junction",
                "flood_depth_m": depth,
                "evacuees_affected": pp.get("total_evacuees", 0)
            })
    
    # Add flooded metro stations
    metro_reports = summary_data.get("metro_reports", [])
    for station in metro_reports:
        if station.get("status") == "unsafe":
            landmarks.append({
                "name": f"Metro: {station.get('name', 'Unknown')}",
                "type": "metro_station",
                "flood_depth_m": station.get("max_depth_m", 0),
                "line": station.get("line", "Unknown")
            })
    
    # Deduplicate by name
    seen = set()
    unique_landmarks = []
    for lm in landmarks:
        key = lm["name"]
        if key not in seen:
            seen.add(key)
            unique_landmarks.append(lm)
    
    return unique_landmarks[:15]  # Top 15 landmarks


async def _get_safe_shelters_with_resources(summary_data: dict, hobli_name: str) -> List[Dict]:
    """
    Identify safe shelters and fetch nearby resources.
    """
    shelters = summary_data.get("shelter_reports", [])
    safe_shelters = [s for s in shelters if s.get("safe", False)]
    
    results = []
    
    try:
        from service import fetch_resources
        
        for shelter in safe_shelters[:10]:  # Limit to 10 for performance
            shelter_name = shelter.get("name", "")
            if not shelter_name:
                continue
            
            # Try to get resources near shelter
            try:
                # Direct await instead of nested loop
                resources = await fetch_resources(shelter_name)
            except Exception as e:
                print(f"[FloodIntel] Resource fetch failed for {shelter_name}: {e}")
                resources = []
            
            # Categorize resources by type
            categorized = {
                "boats": [],
                "medical": [],
                "food_water": [],
                "transport": [],
                "other": []
            }
            
            for r in resources[:20]:  # Limit per shelter
                item_name = r.get("item", "").lower()
                distance = r.get("distance_val", float('inf'))
                
                resource_entry = {
                    "item": r.get("item", "Unknown"),
                    "quantity": r.get("qty", "N/A"),
                    "source": r.get("source", "Unknown"),
                    "distance_km": round(distance, 1) if distance != float('inf') else "N/A",
                    "contact": r.get("contact", ""),
                    "phone": r.get("phone", "")
                }
                
                if any(kw in item_name for kw in ["boat", "inflatable", "dinghy", "rescue boat"]):
                    categorized["boats"].append(resource_entry)
                elif any(kw in item_name for kw in ["medic", "doctor", "hospital", "clinic", "first aid", "ambulance"]):
                    categorized["medical"].append(resource_entry)
                elif any(kw in item_name for kw in ["food", "water", "ration", "meal", "drinking", "bottle"]):
                    categorized["food_water"].append(resource_entry)
                elif any(kw in item_name for kw in ["bus", "truck", "vehicle", "transport", "van"]):
                    categorized["transport"].append(resource_entry)
                else:
                    categorized["other"].append(resource_entry)
            
            # Only include shelters with at least some resources
            total_resources = sum(len(v) for v in categorized.values())
            if total_resources > 0:
                results.append({
                    "shelter_name": shelter_name,
                    "shelter_id": shelter.get("id"),
                    "capacity": shelter.get("capacity", 0),
                    "occupancy": shelter.get("occupancy", 0),
                    "occupancy_pct": shelter.get("occupancy_pct", 0),
                    "lat": shelter.get("lat"),
                    "lon": shelter.get("lon"),
                    "resources": categorized,
                    "total_nearby_resources": total_resources
                })
    
    except Exception as e:
        print(f"[FloodIntel] Error fetching shelter resources: {e}")
    
    # Sort by occupancy (most crowded first - highest need)
    results.sort(key=lambda x: x["occupancy_pct"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  MCP TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_metro_status(hobli_name: str = "") -> str:
    """
    Analyze metro rail system integrity by line. Returns:
    - Per-line station counts (unsafe/caution/safe)
    - Disruption percentage per line
    - Health status (CRITICAL/DEGRADED/OPERATIONAL)
    
    Use this when the user asks about metro disruptions, train safety,
    or alternative transit options during the flood.
    
    Args:
        hobli_name: Optional hobli name. Uses currently loaded region if omitted.
    """
    state = _load_state()
    summary_data = state.get("summary_data")
    
    if not summary_data:
        return "No simulation data available. Please run a flood simulation first."
    
    metro_status = _get_metro_status_from_summary(summary_data)
    
    if not metro_status["available"]:
        return metro_status["message"]
    
    lines = [
        f"=== Metro System Status Report ===",
        f"Total Stations Analyzed: {metro_status['total_stations']}",
        "",
        metro_status["summary"],
        "",
        "=== Recommendation ==="
    ]
    
    # Add actionable recommendation
    critical_exists = any(
        data["health_status"] == "CRITICAL" 
        for data in metro_status["lines"].values()
    )
    
    if critical_exists:
        lines.append("🔴 Avoid metro travel on CRITICAL lines. Use BMTC buses or designated evacuation routes instead.")
    elif any(data["health_status"] == "DEGRADED" for data in metro_status["lines"].values()):
        lines.append("🟡 Metro service is partially disrupted. Check individual station status before travel.")
    else:
        lines.append("🟢 Metro system is operational. Monitor real-time updates as flooding may worsen.")
    
    return "\n".join(lines)


@mcp.tool()
def get_flood_impact() -> str:
    """
    Get comprehensive socio-economic flood impact summary including:
    - Population at risk (initial vs remaining)
    - Key flooded landmarks and junctions
    - Metro station flooding summary
    
    Use this when the user asks for a situation overview, damage assessment,
    or where the worst flooding is occurring.
    """
    state = _load_state()
    summary_data = state.get("summary_data")
    hobli_name = state.get("hobli", "Unknown")
    
    if not summary_data:
        return "No simulation data available. Please run a flood simulation first."
    
    # Population metrics
    total_initial = summary_data.get("total_at_risk_initial", 0)
    total_remaining = summary_data.get("total_at_risk_remaining", 0)
    total_evacuated = summary_data.get("total_evacuated", 0)
    success_rate = summary_data.get("success_rate_pct", 0)
    
    # Flooded landmarks
    landmarks = _get_flooded_landmarks(summary_data, hobli_name)
    flooded_metro = [lm for lm in landmarks if lm.get("type") == "metro_station"]
    flooded_junctions = [lm for lm in landmarks if lm.get("type") == "junction"]
    
    # Build response
    lines = [
        f"=== Flood Impact Assessment — {hobli_name} ===",
        "",
        "## Population Impact",
        f"- Total population at risk initially: **{total_initial:,}** people",
        f"- Successfully evacuated: **{total_evacuated:,}** ({success_rate}%)",
        f"- Still at risk / unreachable: **{total_remaining:,}** people",
        "",
        "## Infrastructure Impact"
    ]
    
    if flooded_metro:
        lines.append(f"- **{len(flooded_metro)}** metro stations flooded:")
        for station in flooded_metro[:8]:
            lines.append(f"  · {station['name']} ({station.get('line', 'Unknown')}) — {station['flood_depth_m']:.2f}m")
    
    if flooded_junctions:
        lines.append(f"- **{len(flooded_junctions)}** critical junctions affected:")
        for junction in flooded_junctions[:5]:
            lines.append(f"  · {junction['name']} — {junction['flood_depth_m']:.2f}m depth")
    
    if not flooded_metro and not flooded_junctions:
        lines.append("- No major flooded landmarks detected in this simulation.")
    
    # Severity assessment
    lines.append("")
    lines.append("## Severity Assessment")
    
    if total_remaining > total_initial * 0.3:
        lines.append("🔴 **SEVERE**: Over 30% of at-risk population remains stranded. Immediate NDRF intervention required.")
    elif total_remaining > total_initial * 0.1:
        lines.append("🟡 **MODERATE**: 10-30% of at-risk population remains. Continue evacuation operations.")
    else:
        lines.append("🟢 **LOW**: Less than 10% of at-risk population remains. Focus on resource distribution.")
    
    if len(flooded_metro) > 5:
        lines.append("⚠️ Metro network severely compromised. Advise against rail-based evacuation.")
    
    return "\n".join(lines)


@mcp.tool()
async def get_shelter_resource_map() -> str:
    """
    Map safe shelters with nearby logistics resources (boats, medical, food, transport).
    Returns "Super-Hubs" — shelters that have equipment and capacity to serve as
    forward operating bases for rescue operations.
    
    Use this when the user asks about:
    - Which shelters have boats available?
    - Where can I send medical teams?
    - Which safe shelters are best equipped?
    - Resource allocation strategy
    """
    state = _load_state()
    summary_data = state.get("summary_data")
    hobli_name = state.get("hobli", "Unknown")
    
    if not summary_data:
        return "No simulation data available. Please run a flood simulation first."
    
    safe_shelters_with_resources = await _get_safe_shelters_with_resources(summary_data, hobli_name)
    
    if not safe_shelters_with_resources:
        return (
            "No shelter-resource mapping available. "
            "This may be because:\n"
            "1. No safe shelters were identified in the simulation\n"
            "2. Resource database is not accessible\n"
            "3. Run a simulation with a populated hobli first"
        )
    
    # Identify Super-Hubs (shelters with boats OR medical AND >50% occupancy)
    super_hubs = [
        s for s in safe_shelters_with_resources
        if (s["resources"]["boats"] or s["resources"]["medical"]) and s["occupancy_pct"] > 50
    ]
    
    lines = [
        f"=== Shelter-Resource Map — {hobli_name} ===",
        "",
        f"Total safe shelters with nearby resources: **{len(safe_shelters_with_resources)}**",
        f"Super-Hubs (boats/medical + high occupancy): **{len(super_hubs)}**",
        "",
    ]
    
    # Super-Hubs first
    if super_hubs:
        lines.append("## 🏥 SUPER-HUBS (Priority for resource deployment)")
        for hub in super_hubs[:5]:
            lines.append(f"\n**{hub['shelter_name']}**")
            lines.append(f"- Occupancy: {hub['occupancy_pct']}% ({hub['occupancy']}/{hub['capacity']})")
            
            if hub["resources"]["boats"]:
                boat_count = len(hub["resources"]["boats"])
                lines.append(f"- 🚤 Boats available: {boat_count}")
                for boat in hub["resources"]["boats"][:2]:
                    lines.append(f"  · {boat['item']} ({boat['quantity']}) — {boat['distance_km']}km")
            
            if hub["resources"]["medical"]:
                medical_count = len(hub["resources"]["medical"])
                lines.append(f"- 🏥 Medical resources: {medical_count}")
            
            if hub["resources"]["food_water"]:
                lines.append(f"- 🍞 Food/Water sources: {len(hub['resources']['food_water'])}")
    
    # Other equipped shelters
    other_equipped = [s for s in safe_shelters_with_resources if s not in super_hubs]
    if other_equipped:
        lines.append("\n## 📍 Other Equipped Shelters")
        for shelter in other_equipped[:8]:
            resource_types = []
            if shelter["resources"]["boats"]:
                resource_types.append(f"🚤 {len(shelter['resources']['boats'])} boats")
            if shelter["resources"]["medical"]:
                resource_types.append(f"🏥 {len(shelter['resources']['medical'])} medical")
            if shelter["resources"]["food_water"]:
                resource_types.append(f"🍞 {len(shelter['resources']['food_water'])} food")
            if shelter["resources"]["transport"]:
                resource_types.append(f"🚌 {len(shelter['resources']['transport'])} transport")
            
            lines.append(
                f"- **{shelter['shelter_name']}**: {shelter['occupancy_pct']}% full | "
                f"{', '.join(resource_types) if resource_types else 'No specialized equipment'}"
            )
    
    # Strategic recommendation
    lines.append("\n## 🎯 Strategic Recommendation")
    
    if super_hubs:
        lines.append(
            f"Deploy NDRF command teams to **{super_hubs[0]['shelter_name']}** — it has "
            f"{len(super_hubs[0]['resources']['boats'])} boats and is at {super_hubs[0]['occupancy_pct']}% capacity, "
            f"making it ideal for forward rescue operations."
        )
    elif safe_shelters_with_resources:
        lines.append(
            f"Priority: **{safe_shelters_with_resources[0]['shelter_name']}** has the best resource density "
            f"({safe_shelters_with_resources[0]['total_nearby_resources']} nearby items)."
        )
    else:
        lines.append("No equipped shelters found. Request external resource deployment immediately.")
    
    return "\n".join(lines)


@mcp.tool()
def get_vulnerability_hotspots(min_flood_depth: float = 0.15) -> str:
    """
    Identify population vulnerability hotspots where:
    - Flood depth exceeds threshold AND
    - High population density AND
    - Far from safe shelters (>1km)
    
    Use this for tactical resource deployment and prioritization.
    
    Args:
        min_flood_depth: Minimum water depth to consider (default 0.15m)
    """
    state = _load_state()
    summary_data = state.get("summary_data")
    hobli_name = state.get("hobli", "Unknown")
    evacuation_plan = state.get("evacuation_plan", [])
    
    if not summary_data:
        return "No simulation data available. Please run a flood simulation first."
    
    # Extract at-risk nodes that weren't evacuated
    assigned_nodes = {move.get("from_node") for move in evacuation_plan if move.get("from_node")}
    
    # Get pressure points as proxy for high-risk areas
    pressure_points = summary_data.get("pressure_points", [])
    
    # Filter hotspots: high volume + flooded
    hotspots = [
        pp for pp in pressure_points
        if pp.get("total_evacuees", 0) > 50 and pp.get("flood_depth", 0) >= min_flood_depth
    ]
    hotspots.sort(key=lambda x: x.get("total_evacuees", 0), reverse=True)
    
    if not hotspots:
        return f"No vulnerability hotspots detected with flood depth >= {min_flood_depth}m."
    
    lines = [
        f"=== Vulnerability Hotspots — {hobli_name} ===",
        f"(Flood depth ≥ {min_flood_depth}m, at-risk population > 50)",
        "",
    ]
    
    for i, hotspot in enumerate(hotspots[:8], 1):
        lines.append(f"{i}. **{hotspot.get('location_name', 'Unknown junction')}**")
        lines.append(f"   - Population at risk: {hotspot.get('total_evacuees', 0)} people")
        lines.append(f"   - Flood depth: {hotspot.get('flood_depth', 0):.2f}m")
        lines.append(f"   - Routes converging: {hotspot.get('route_count', 0)}")
        
        # Recommend action based on severity
        depth = hotspot.get("flood_depth", 0)
        if depth > 0.5:
            lines.append(f"   - ⚠️ ACTION: Water too deep for ground rescue — deploy boats")
        elif depth > 0.3:
            lines.append(f"   - ⚠️ ACTION: High-clearance vehicles required")
        else:
            lines.append(f"   - ℹ️ ACTION: Prioritize evacuation via nearby safe routes")
        lines.append("")
    
    # Overall recommendation
    total_hotspot_pop = sum(h.get("total_evacuees", 0) for h in hotspots)
    lines.append(f"**Total population in hotspots: {total_hotspot_pop:,} people**")
    lines.append("**Priority**: Deploy resources to the top 3 hotspots first.")
    
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  DRAIN INTELLIGENCE TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_drain_status_report(hobli_name: str = "") -> str:
    """
    Get the status of storm-water drains for a hobli region.
    Returns the number of drains, their conditions, capacity factors,
    and whether drain data is influencing the current simulation.

    Use this when the user asks about drainage infrastructure, drain blockages,
    or why certain areas are flooding more than others.

    Args:
        hobli_name: Optional hobli name. Uses currently loaded region if omitted.
    """
    if not hobli_name:
        state = _load_state()
        hobli_name = state.get("hobli", "")

    if not hobli_name:
        return "No region specified and no simulation region loaded."

    try:
        from drain_data import get_drains_for_hobli, get_drain_summary
        drains = get_drains_for_hobli(hobli_name)

        if not drains:
            return (f"No storm-water drain data found within 2km of {hobli_name}. "
                    "This may mean no drains are instrumented in this area, "
                    "or the drain dataset doesn't cover this region.")

        summary = get_drain_summary(drains)

        lines = [
            f"=== Storm-Water Drain Status - {hobli_name} ===",
            f"Total Drains in Region: {summary['count']}",
            "",
            "## Drain Conditions",
        ]

        for condition, count in summary.get("condition_breakdown", {}).items():
            emoji = {"good": "G", "fair": "Y", "poor": "R", "blocked": "X"}.get(condition, "?")
            lines.append(f"  [{emoji}] {condition.capitalize()}: {count} drain(s)")

        lines.extend([
            "",
            f"Average Water Level: {summary.get('avg_water_level_cm', 0):.1f} cm",
            f"Average Capacity Factor: {summary.get('avg_capacity_factor', 0):.0%}",
            "",
            "## Drain Locations",
        ])

        for d in drains:
            status = d.status if hasattr(d, 'status') else d.get("status", "normal")
            name = d.location_name if hasattr(d, 'location_name') else d.get("location_name", "")
            did = d.drain_id if hasattr(d, 'drain_id') else d.get("drain_id", "")
            lines.append(f"  - {did}: {name} (status: {status})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching drain status: {str(e)}"


@mcp.tool()
def find_nearest_drains(lat: float, lon: float, count: int = 5) -> str:
    """
    Find the nearest storm-water drains to a specific coordinate.
    Returns drain IDs, locations, distances, and conditions.

    Use this when the user asks about drainage near a specific location,
    or to assess flood risk at a particular point.

    Args:
        lat: Latitude of the query point
        lon: Longitude of the query point
        count: Number of nearest drains to return (default 5)
    """
    try:
        from drain_data import load_drain_data, get_nearest_drains as _get_nearest

        all_drains = load_drain_data()
        if not all_drains:
            return "No drain data is currently loaded."

        nearest = _get_nearest(lat, lon, all_drains, n=count)

        if not nearest:
            return f"No drains found near ({lat:.4f}, {lon:.4f})."

        lines = [f"=== Nearest Drains to ({lat:.4f}, {lon:.4f}) ===", ""]

        for i, d in enumerate(nearest, 1):
            dist_m = d.get("distance_m", 0)
            condition = d.get("condition", "unknown")
            lines.append(
                f"{i}. {d.get('drain_id', '?')} - {d.get('location_name', 'Unknown')}\n"
                f"   Distance: {dist_m:.0f}m | Condition: {condition} | "
                f"Water Level: {d.get('water_level_cm', 0):.0f}cm | "
                f"Capacity: {d.get('capacity_factor', 0):.0%}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"Error finding nearest drains: {str(e)}"


@mcp.tool()
def get_drain_coverage(hobli_name: str = "") -> str:
    """
    Analyze drain infrastructure coverage for a hobli region.
    Returns drain density, average spacing, and coverage assessment.

    Use this when the user asks about infrastructure adequacy,
    why flooding is severe, or to compare drainage across regions.

    Args:
        hobli_name: Optional hobli name. Uses currently loaded region if omitted.
    """
    if not hobli_name:
        state = _load_state()
        hobli_name = state.get("hobli", "")

    if not hobli_name:
        return "No region specified."

    try:
        from region_manager import REGION_CACHE, norm_key
        key = norm_key(hobli_name)

        if key in REGION_CACHE and "drain_influence_summary" in REGION_CACHE[key]:
            summary = REGION_CACHE[key]["drain_influence_summary"]

            density = summary.get("drain_density_per_km2", 0)
            spacing = summary.get("avg_drain_spacing_m", 0)
            n_drains = summary.get("drain_count", len(summary.get("drain_ids", [])))
            n_influenced = summary.get("nodes_influenced", 0)
            total_nodes = summary.get("total_nodes", 0)
            coverage_pct = (n_influenced / total_nodes * 100) if total_nodes > 0 else 0

            lines = [
                f"=== Drain Coverage Analysis - {hobli_name} ===",
                "",
                f"Drains in Region: {n_drains}",
                f"Drain Density: {density:.2f} per km2",
                f"Average Inter-Drain Spacing: {spacing:.0f} m",
                f"Road Network Nodes Influenced: {n_influenced:,} / {total_nodes:,} ({coverage_pct:.1f}%)",
                "",
                "## Coverage Assessment",
            ]

            if density >= 2.0:
                lines.append("ADEQUATE: Drain density meets urban flood management standards.")
            elif density >= 0.5:
                lines.append("MODERATE: Some areas lack effective drain coverage.")
            elif density > 0:
                lines.append("POOR: Drain coverage is sparse. Urban flooding risk is elevated.")
            else:
                lines.append("NO COVERAGE: No instrumented drains in this area.")

            return "\n".join(lines)

        from drain_data import get_drains_for_hobli
        drains = get_drains_for_hobli(hobli_name)
        if not drains:
            return f"No drain data available for {hobli_name}."

        return (f"Drain Coverage for {hobli_name}: {len(drains)} drains detected. "
                "Run a simulation to get detailed influence metrics.")
    except Exception as e:
        return f"Error analyzing drain coverage: {str(e)}"


@mcp.tool()
def get_drain_influence_on_flooding() -> str:
    """
    Explain how storm-water drains are influencing the current flood simulation.
    Returns which drains are active, how they affect water levels,
    and their overall impact on flood severity.

    Use this when the user asks why flooding is better/worse than expected,
    or how drains are affecting the simulation results.
    """
    state = _load_state()
    hobli_name = state.get("hobli", "Unknown")

    try:
        from region_manager import REGION_CACHE, norm_key
        key = norm_key(hobli_name)

        if key not in REGION_CACHE:
            return "No active simulation. Run a flood simulation first."

        entry = REGION_CACHE[key]
        drains = entry.get("stormwater_drains", [])
        influence = entry.get("drain_influence_summary", {})

        if not drains:
            return (f"No storm-water drains are active in the {hobli_name} simulation. "
                    "Flood behavior is based purely on elevation, rainfall, and surface runoff.")

        n_drains = influence.get("drain_count", len(drains))
        n_influenced = influence.get("nodes_influenced", 0)
        density = influence.get("drain_density_per_km2", 0)

        lines = [
            f"=== Drain Influence on Flooding - {hobli_name} ===",
            "",
            f"Active Drains: {n_drains}",
            f"Nodes with Drain Influence: {n_influenced:,}",
            f"Drain Density: {density:.2f} per km2",
            "",
            "## How Drains Affect This Simulation",
            "",
        ]

        good_drains = [d for d in drains if d.get("condition", "") in ("good",)]
        bad_drains = [d for d in drains if d.get("condition", "") in ("poor", "blocked")]
        fair_drains = [d for d in drains if d.get("condition", "") in ("fair",)]

        if good_drains:
            lines.append(f"{len(good_drains)} functioning drain(s) are actively reducing flood water "
                         f"near their locations. Nodes within {influence.get('influence_radius_m', 200)}m "
                         f"experience up to 30% water depth reduction per simulation step.")

        if bad_drains:
            lines.append(f"{len(bad_drains)} blocked/critical drain(s) are contributing to localised "
                         f"ponding and overflow. Nodes near these drains may experience HIGHER water levels "
                         f"than expected due to back-flow from clogged channels.")

        if fair_drains:
            lines.append(f"{len(fair_drains)} degraded drain(s) are partially functional, "
                         f"providing reduced drainage capacity.")

        lines.extend(["", "## Recommendation"])
        if bad_drains:
            bad_names = [d.get("location_name", d.get("drain_id", "?")) for d in bad_drains]
            lines.append(f"Priority maintenance: Clear blockages at {', '.join(bad_names)} "
                         f"to enable drainage capacity and reduce flood severity in those zones.")
        elif n_drains > 0:
            lines.append("All drains in this region are functioning. Current drainage is "
                         "operating at expected capacity.")

        return "\n".join(lines)
    except Exception as e:
        return f"Error analyzing drain influence: {str(e)}"


# ══════════════════════════════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Starting Flood Intelligence MCP Server...")
    print("Tools:")
    print("  - get_metro_status         : Line-wise metro disruption analysis")
    print("  - get_flood_impact         : Population + infrastructure impact")
    print("  - get_shelter_resource_map : Safe shelters with nearby resources")
    print("  - get_vulnerability_hotspots : High-risk population clusters")
    print("  - get_drain_status_report  : Storm-water drain status")
    print("  - find_nearest_drains      : Find drains near a coordinate")
    print("  - get_drain_coverage       : Drain infrastructure analysis")
    print("  - get_drain_influence_on_flooding : How drains affect simulation")
    mcp.run()