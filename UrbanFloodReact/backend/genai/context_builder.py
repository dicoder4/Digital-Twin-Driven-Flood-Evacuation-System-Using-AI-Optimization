"""
context_builder.py — Enriches raw simulation data into structured LLM context
─────────────────────────────────────────────────────────────────────────────

PATCH LOG:
  Bug 4 — Removed the inventory[:25] hard cap. Only 25 of up to 338 real
           resources were being passed to the LLM, causing "only one item
           per shelter" because the LLM had almost nothing to allocate.
           Now passes up to 200 items (all within 15km, plus distant fallback).

  Bug 5 — enriched_shelters now includes 'lat' and 'lon' from shelter_reports.
           Without coordinates, the LLM had no way to reason about which
           resource source is closest to which shelter, and had no alternative
           destination addresses — so it reused fire station addresses as
           shelter destinations. The new _format_shelters_context() in
           expert_panel.py consumes these coordinates.
"""

import math
from service import fetch_resources


async def build_expert_context(summary_data: dict, evacuation_plan: list = None, algorithm_analysis: dict = None) -> dict:
    """
    Build an enriched context dict from the raw simulation summary.

    Args:
        summary_data:    The 'summary' sub-dict from the final_report.
        evacuation_plan: Optional list of route dicts from the planner output.

    Returns:
        A structured dict ready for LLM consumption.
    """
    shelter_reports = summary_data.get("shelter_reports", [])
    location_name   = summary_data.get("simulation_location", "Unknown")

    # ── Fetch Live Inventory ──────────────────────────────────────────────────
    # BUG 4 FIX: The original code capped inventory at [:25], silently
    # discarding up to 313 resources for Yashavantapura-1 alone.
    # We now pass up to 200 items so the LLM sees the full nearby inventory.
    # Items are already sorted by distance from get_available_resources().
    try:
        inventory      = await fetch_resources(location_name)
        inventory_context = inventory[:200]   # was [:25] — BUG 4 FIX
    except Exception as e:
        print(f"[ContextBuilder] Error fetching resources: {e}")
        inventory_context = []

    # ── Shelter ID → name / type lookup ──────────────────────────────────────
    shelter_id_to_name: dict = {}
    shelter_id_to_type: dict = {}
    for s in shelter_reports:
        sid = s.get("id", "")
        shelter_id_to_name[sid] = s.get("name", sid)
        shelter_id_to_type[sid] = s.get("type", "unknown")

    # ── Classify shelter severity & preserve coordinates ─────────────────────
    enriched_shelters  = []
    critical_shelters  = []
    available_shelters = []

    for s in shelter_reports:
        pct = s.get("occupancy_pct", 0)
        occ = s.get("occupancy", 0)
        cap = s.get("capacity", 1)

        if pct >= 90:
            status = "CRITICAL"
            critical_shelters.append(s.get("name", s.get("id", "Unknown")))
        elif pct >= 60:
            status = "HIGH"
        elif occ > 0:
            status = "MODERATE"
        else:
            status = "EMPTY"
            available_shelters.append(s.get("name", s.get("id", "Unknown")))

        # BUG 5 FIX: Preserve lat/lon from shelter_reports so the LLM
        # and _format_shelters_context() can display real coordinates.
        # The original code dropped these fields entirely.
        enriched_shelters.append({
            "name":               s.get("name", s.get("id", "Unknown")),
            "type":               s.get("type", "unknown"),
            "occupancy":          occ,
            "capacity":           cap,
            "occupancy_pct":      pct,
            "remaining_capacity": max(0, cap - occ),
            "status":             status,
            "lat":                s.get("lat"),    # BUG 5 FIX
            "lon":                s.get("lon"),    # BUG 5 FIX
        })

    # Sort by occupancy descending — most critical first
    enriched_shelters.sort(key=lambda x: x["occupancy_pct"], reverse=True)

    # ── Per-route details ─────────────────────────────────────────────────────
    route_details = []
    shelter_inflow: dict = {}
    fallback_count = 0
    route_summary  = None

    if evacuation_plan:
        distances = []
        pops      = []

        for r in evacuation_plan:
            sid    = r.get("to_shelter", "")
            s_name = shelter_id_to_name.get(sid, sid)
            s_type = shelter_id_to_type.get(sid, "unknown")
            pop    = r.get("pop", 0)
            is_fb  = r.get("fallback", False)
            path   = r.get("path", [])

            dist = r.get("distance", None)
            if dist is None and len(path) >= 2:
                dist = _path_distance_m(path)
            if dist is None:
                dist = 0.0

            if is_fb:
                fallback_count += 1

            pops.append(pop)
            distances.append(dist)
            shelter_inflow[s_name] = shelter_inflow.get(s_name, 0) + pop

            route_details.append({
                "origin_node":    r.get("from_node", "unknown"),
                "to_shelter":     s_name,
                "shelter_type":   s_type,
                "evacuees":       pop,
                "distance_m":     round(dist, 1),
                "path_points":    len(path),
                "fallback_route": is_fb,
            })

        route_details.sort(key=lambda x: x["evacuees"], reverse=True)

        critical_set          = set(critical_shelters)
        routes_to_critical    = [r for r in route_details if r["to_shelter"] in critical_set]

        route_summary = {
            "total_routes":                len(evacuation_plan),
            "total_people_routed":         sum(pops),
            "routes_to_critical_shelters": len(routes_to_critical),
            "avg_distance_m":              round(sum(distances) / max(len(distances), 1), 1),
            "max_distance_m":              round(max(distances), 1) if distances else 0,
            "min_distance_m":              round(min(distances), 1) if distances else 0,
            "largest_group_size":          max(pops) if pops else 0,
            "fallback_routes":             fallback_count,
        }

    shelters_by_inflow = [
        {"shelter": name, "total_evacuees_received": count}
        for name, count in sorted(
            shelter_inflow.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # ── Build final context ───────────────────────────────────────────────────
    context = {
        "simulation": {
            "location":                  location_name,
            "algorithm":                 summary_data.get("algorithm", "UNKNOWN"),
            "success_rate_pct":          summary_data.get("success_rate_pct", 0),
            "total_evacuated":           summary_data.get("total_evacuated", 0),
            "total_at_risk_remaining":   summary_data.get("total_at_risk_remaining", 0),
            "total_at_risk_initial":     summary_data.get("total_at_risk_initial", 0),
            "simulation_population":     summary_data.get("simulation_population", 0),
            "best_fitness":              summary_data.get("best_fitness", 0),
            "avg_distance_per_person_m": summary_data.get("avg_distance_per_person", 0),
            "execution_time_s":          summary_data.get("ga_execution_time", 0),
        },
        "local_inventory":  inventory_context,   # BUG 4 FIX: up to 200 items
        "shelters":         enriched_shelters,   # BUG 5 FIX: includes lat/lon
        "shelter_overview": {
            "total_shelters":           len(enriched_shelters),
            "critical_shelters":        critical_shelters,
            "shelters_with_space":      available_shelters,
            "total_remaining_capacity": sum(s["remaining_capacity"] for s in enriched_shelters),
        },
        "pressure_junctures": summary_data.get("pressure_points", []),
        "algorithm_analysis": algorithm_analysis,
    }

    # ── Add Metro Context if available ─────────────────────────────────────
    metro_reports = summary_data.get("metro_reports", [])
    if metro_reports:
        context["metro_reports"] = metro_reports
        context["metro_summary"] = {
            "total_stations": len(metro_reports),
            "unsafe_stations": sum(1 for s in metro_reports if s.get("status") == "unsafe"),
            "caution_stations": sum(1 for s in metro_reports if s.get("status") == "caution"),
            "safe_stations": sum(1 for s in metro_reports if s.get("status") == "safe"),
        }

    if route_summary:
        context["route_overview"] = route_summary

    if route_details:
        context["route_details"]      = route_details[:25]
        context["shelters_by_inflow"] = shelters_by_inflow

    context["_data_notes"] = (
        "local_inventory contains resource SOURCES (fire stations, hospitals, depots) "
        "sorted by distance from the disaster zone. "
        "shelters contains evacuation DESTINATIONS with occupancy and coordinates. "
        "These two lists are entirely separate — do not mix source addresses with shelter names."
    )

    return context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _path_distance_m(path: list) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        lon1, lat1 = path[i][0],   path[i][1]
        lon2, lat2 = path[i+1][0], path[i+1][1]
        total += _haversine(lat1, lon1, lat2, lon2)
    return total


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R   = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a  = math.sin(dφ/2)**2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))