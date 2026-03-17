"""
context_builder.py — Enriches raw simulation data into structured LLM context
─────────────────────────────────────────────────────────────────────────────
Takes the final_report from service.py and builds a richer dict that gives
the LLM concrete numbers, shelter severity tags, route summaries, etc.
"""


def build_expert_context(summary_data: dict, evacuation_plan: list = None) -> dict:
    """
    Build an enriched context dict from the raw simulation summary.
    
    Args:
        summary_data:    The 'summary' sub-dict from the final_report
                         (total_evacuated, shelter_reports, success_rate_pct, etc.)
        evacuation_plan: Optional list of route dicts from the planner output
                         (each has: from_node, to_shelter, pop, path, distance)
    
    Returns:
        A structured dict ready for LLM consumption.
    """
    shelter_reports = summary_data.get("shelter_reports", [])

    # ── Classify shelter severity ─────────────────────────────────
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

    # ── Route summary (if plan is available) ──────────────────────
    route_summary = None
    if evacuation_plan:
        distances = [r.get("distance", 0) for r in evacuation_plan if r.get("distance")]
        pops = [r.get("pop", 0) for r in evacuation_plan]

        # Routes feeding critical shelters
        critical_set = set(critical_shelters)
        routes_to_critical = [
            r for r in evacuation_plan
            if _shelter_name_for_route(r, shelter_reports) in critical_set
        ]

        route_summary = {
            "total_routes": len(evacuation_plan),
            "total_people_routed": sum(pops),
            "routes_to_critical_shelters": len(routes_to_critical),
            "avg_distance_m": round(sum(distances) / max(len(distances), 1), 1) if distances else 0,
            "max_distance_m": round(max(distances), 1) if distances else 0,
            "min_distance_m": round(min(distances), 1) if distances else 0,
            "largest_group_size": max(pops) if pops else 0,
        }

    # ── Build final context ───────────────────────────────────────
    context = {
        "simulation": {
            "algorithm": summary_data.get("algorithm", "UNKNOWN"),
            "success_rate_pct": summary_data.get("success_rate_pct", 0),
            "total_evacuated": summary_data.get("total_evacuated", 0),
            "total_at_risk_remaining": summary_data.get("total_at_risk_remaining", 0),
            "total_at_risk_initial": summary_data.get("total_at_risk_initial", 0),
            "simulation_population": summary_data.get("simulation_population", 0),
            "best_fitness": summary_data.get("best_fitness", 0),
            "avg_distance_per_person_m": summary_data.get("avg_distance_per_person", 0),
            "execution_time_s": summary_data.get("ga_execution_time", 0),
        },
        "shelters": enriched_shelters,
        "shelter_overview": {
            "total_shelters": len(enriched_shelters),
            "critical_shelters": critical_shelters,
            "shelters_with_space": available_shelters,
            "total_remaining_capacity": sum(s["remaining_capacity"] for s in enriched_shelters),
        },
    }

    if route_summary:
        context["routes"] = route_summary

    return context


def _shelter_name_for_route(route: dict, shelter_reports: list) -> str:
    """Map a route's to_shelter ID to its human-readable name."""
    sid = route.get("to_shelter", "")
    for s in shelter_reports:
        if s.get("id") == sid:
            return s.get("name", sid)
    return sid

