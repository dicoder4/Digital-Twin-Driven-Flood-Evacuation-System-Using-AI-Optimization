"""
context_builder.py — Enriches raw simulation data into structured LLM context
─────────────────────────────────────────────────────────────────────────────
Takes the final_report from service.py and builds a richer dict that gives
the LLM concrete numbers, shelter severity tags, per-route details, etc.

Route-level context now exposes:
  • route_details  — one entry per route: shelter name, evacuees, distance, fallback flag
  • route_overview — aggregated stats (total, largest group, fallback count, etc.)
  • top_routes_by_evacuees   — top 5 routes sorted by group size
  • shelters_by_inflow       — shelters ranked by total evacuees received

What is NOT available (require graph-level data not in mcp_state.json):
  • Street names per path segment  (only lon/lat coords are stored in the plan)
  • Per-junction flood depth        (flood GeoJSON is not persisted to state)
  • Per-segment TomTom delay        (only binary: traffic on/off per run)
"""

import math


def build_expert_context(summary_data: dict, evacuation_plan: list = None) -> dict:
    """
    Build an enriched context dict from the raw simulation summary.

    Args:
        summary_data:    The 'summary' sub-dict from the final_report
                         (total_evacuated, shelter_reports, success_rate_pct, etc.)
        evacuation_plan: Optional list of route dicts from the planner output.
                         Each route: {from_node, to_shelter, pop, path, fallback, distance?}

    Returns:
        A structured dict ready for LLM consumption.
    """
    shelter_reports = summary_data.get("shelter_reports", [])

    # ── Build shelter ID → name lookup for route resolution ──────────────────
    shelter_id_to_name: dict = {}
    shelter_id_to_type: dict = {}
    for s in shelter_reports:
        sid = s.get("id", "")
        shelter_id_to_name[sid] = s.get("name", sid)
        shelter_id_to_type[sid] = s.get("type", "unknown")

    # ── Classify shelter severity ─────────────────────────────────────────────
    enriched_shelters = []
    critical_shelters = []
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

        enriched_shelters.append({
            "name": s.get("name", s.get("id", "Unknown")),
            "type": s.get("type", "unknown"),
            "occupancy": occ,
            "capacity": cap,
            "occupancy_pct": pct,
            "remaining_capacity": max(0, cap - occ),
            "status": status,
        })

    # Sort by occupancy descending — most critical first
    enriched_shelters.sort(key=lambda x: x["occupancy_pct"], reverse=True)

    # ── Per-route details (the key enrichment for route-level Q&A) ───────────
    route_details = []
    shelter_inflow: dict = {}   # shelter_name → total evacuees received
    fallback_count = 0
    route_summary = None

    if evacuation_plan:
        distances = []
        pops = []

        for r in evacuation_plan:
            sid       = r.get("to_shelter", "")
            s_name    = shelter_id_to_name.get(sid, sid)
            s_type    = shelter_id_to_type.get(sid, "unknown")
            pop       = r.get("pop", 0)
            is_fb     = r.get("fallback", False)
            path      = r.get("path", [])

            # Distance: stored directly if planner added it, otherwise estimate
            # from path coordinate count (rough proxy: each coord pair ≈ 20-50m avg)
            dist = r.get("distance", None)
            if dist is None and len(path) >= 2:
                # Haversine sum over path coords [lon, lat]
                dist = _path_distance_m(path)
            if dist is None:
                dist = 0.0

            if is_fb:
                fallback_count += 1

            pops.append(pop)
            distances.append(dist)

            shelter_inflow[s_name] = shelter_inflow.get(s_name, 0) + pop

            route_details.append({
                "origin_node":     r.get("from_node", "unknown"),
                "to_shelter":      s_name,
                "shelter_type":    s_type,
                "evacuees":        pop,
                "distance_m":      round(dist, 1),
                "path_points":     len(path),   # number of coordinate waypoints
                "fallback_route":  is_fb,        # True = disconnected, straight-line used
            })

        # Sort route_details by evacuees descending for easy "top routes" queries
        route_details.sort(key=lambda x: x["evacuees"], reverse=True)

        # Critical-shelter set for route tagging
        critical_set = set(critical_shelters)
        routes_to_critical = [r for r in route_details if r["to_shelter"] in critical_set]

        route_summary = {
            "total_routes":               len(evacuation_plan),
            "total_people_routed":        sum(pops),
            "routes_to_critical_shelters": len(routes_to_critical),
            "avg_distance_m":             round(sum(distances) / max(len(distances), 1), 1),
            "max_distance_m":             round(max(distances), 1) if distances else 0,
            "min_distance_m":             round(min(distances), 1) if distances else 0,
            "largest_group_size":         max(pops) if pops else 0,
            "fallback_routes":            fallback_count,  # routes using straight-line (no road path)
        }

    # ── Shelters ranked by inflow (evacuees received) ────────────────────────
    shelters_by_inflow = [
        {"shelter": name, "total_evacuees_received": count}
        for name, count in sorted(shelter_inflow.items(), key=lambda x: x[1], reverse=True)
    ]

    # ── Build final context ───────────────────────────────────────────────────
    context = {
        "simulation": {
            "algorithm":                summary_data.get("algorithm", "UNKNOWN"),
            "success_rate_pct":         summary_data.get("success_rate_pct", 0),
            "total_evacuated":          summary_data.get("total_evacuated", 0),
            "total_at_risk_remaining":  summary_data.get("total_at_risk_remaining", 0),
            "total_at_risk_initial":    summary_data.get("total_at_risk_initial", 0),
            "simulation_population":    summary_data.get("simulation_population", 0),
            "best_fitness":             summary_data.get("best_fitness", 0),
            "avg_distance_per_person_m": summary_data.get("avg_distance_per_person", 0),
            "execution_time_s":         summary_data.get("ga_execution_time", 0),
        },
        "shelters":          enriched_shelters,
        "shelter_overview": {
            "total_shelters":         len(enriched_shelters),
            "critical_shelters":      critical_shelters,
            "shelters_with_space":    available_shelters,
            "total_remaining_capacity": sum(s["remaining_capacity"] for s in enriched_shelters),
        },
        "pressure_junctures": summary_data.get("pressure_points", []),
    }

    if route_summary:
        context["route_overview"] = route_summary

    # Include top 25 routes by evacuees for detailed tactical awareness
    if route_details:
        context["route_details"]         = route_details[:25]   # top 25 by evacuees
        context["shelters_by_inflow"]    = shelters_by_inflow   # all shelters ranked

    # ── Data availability note for the LLM ───────────────────────────────────
    context["_data_notes"] = (
        "route_details contains one entry per evacuation route (group of people from one "
        "at-risk cluster to one shelter). 'distance_m' is the road-network distance. "
        "'path_points' is the number of coordinate waypoints along the road path. "
        "Street names are NOT available — only shelter names and distances are known. "
        "Flood depth per junction and per-segment TomTom delays are not stored in this state."
    )

    return context


# ── Helpers ───────────────────────────────────────────────────────────────────

def _shelter_name_for_route(route: dict, shelter_reports: list) -> str:
    """Map a route's to_shelter ID to its human-readable name."""
    sid = route.get("to_shelter", "")
    for s in shelter_reports:
        if s.get("id") == sid:
            return s.get("name", sid)
    return sid


def _path_distance_m(path: list) -> float:
    """
    Estimate total route distance in metres using Haversine sum over
    a list of [lon, lat] coordinate pairs.
    """
    total = 0.0
    for i in range(len(path) - 1):
        lon1, lat1 = path[i][0], path[i][1]
        lon2, lat2 = path[i + 1][0], path[i + 1][1]
        total += _haversine(lat1, lon1, lat2, lon2)
    return total


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lon points."""
    R = 6_371_000  # Earth radius in metres
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
