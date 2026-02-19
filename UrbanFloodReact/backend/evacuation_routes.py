"""
Evacuation Routes
Handles safe-center preparation, evacuation algorithm execution,
algorithm comparison, and emergency notification triggers.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import json
import numpy as np

from evacuation_algorithms import (
    dijkstra_evacuation,
    astar_evacuation,
    quanta_adaptive_routing_evacuation,
    bidirectional_evacuation,
    generate_evacuation_summary,
    generate_detailed_evacuation_log,
)
from network_utils import prepare_safe_centers
from risk_assessment import calculate_risk_level
from location_routes import STORE
from simulation_routes import SIM_STORE

router = APIRouter(prefix="/evacuation", tags=["Evacuation"])

# In-memory evacuation state
EVAC_STORE = {
    "safe_centers_gdf": None,
    "evacuation_result": None,
    "detailed_log": None,
    "center_stats": None,
}

ALGORITHMS = {
    "Dijkstra": dijkstra_evacuation,
    "A*": astar_evacuation,
    "Quanta Adaptive Routing": quanta_adaptive_routing_evacuation,
    "Bidirectional": bidirectional_evacuation,
}


class EvacRunRequest(BaseModel):
    algorithm: str = "Dijkstra"
    walking_speed: float = 5.0

class CompareRequest(BaseModel):
    walking_speed: float = 5.0

class EmailRequest(BaseModel):
    algorithm: str
    avg_time: float
    evacuated_count: int
    total_at_risk: int


@router.post("/safe-centers")
async def prepare_centers():
    """Identify safe evacuation centers outside the flood zone."""
    global EVAC_STORE

    if STORE["graph"] is None:
        raise HTTPException(status_code=400, detail="Load network first")

    impact = SIM_STORE.get("current_impact")
    if impact is None:
        raise HTTPException(status_code=400, detail="Run simulation first")

    hospitals_gdf = STORE.get("hospitals_gdf")
    police_gdf = STORE.get("police_gdf")
    edges = STORE.get("edges")

    try:
        safe_centers_gdf = prepare_safe_centers(
            hospitals_gdf, police_gdf, edges, impact["flood_poly"]
        )
        EVAC_STORE["safe_centers_gdf"] = safe_centers_gdf

        if safe_centers_gdf.empty:
            return {"success": True, "count": 0, "centers": []}

        centers = []
        for _, row in safe_centers_gdf.iterrows():
            centers.append({
                "center_id": row.get("center_id", ""),
                "type": row.get("type", "unknown"),
                "lat": row.geometry.y,
                "lon": row.geometry.x,
            })

        return {"success": True, "count": len(centers), "centers": centers}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare safe centers: {e}")


@router.post("/run")
async def run_evacuation(req: EvacRunRequest):
    """Run a specific evacuation algorithm."""
    global EVAC_STORE

    if req.algorithm not in ALGORITHMS:
        raise HTTPException(status_code=400, detail=f"Unknown algorithm: {req.algorithm}. Options: {list(ALGORITHMS.keys())}")

    G = STORE.get("graph")
    impact = SIM_STORE.get("current_impact")
    safe_centers_gdf = EVAC_STORE.get("safe_centers_gdf")

    if G is None:
        raise HTTPException(status_code=400, detail="Load network first")
    if impact is None:
        raise HTTPException(status_code=400, detail="Run simulation first")
    if safe_centers_gdf is None or safe_centers_gdf.empty:
        raise HTTPException(status_code=400, detail="Prepare safe centers first")

    flooded_people = impact["flooded_people"]
    if flooded_people.empty:
        return {"success": True, "message": "No people in flood zone — nothing to evacuate"}

    try:
        algo_fn = ALGORITHMS[req.algorithm]
        result = algo_fn(G, flooded_people, safe_centers_gdf, req.walking_speed)
        result["algorithm"] = req.algorithm

        EVAC_STORE["evacuation_result"] = result

        # Generate detailed log
        location_name = STORE.get("location_name", "Unknown")
        detailed_log, center_stats = generate_detailed_evacuation_log(
            result, safe_centers_gdf, location_name, req.algorithm
        )
        EVAC_STORE["detailed_log"] = detailed_log
        EVAC_STORE["center_stats"] = center_stats

        # Build response
        evacuated_count = len(result["evacuated"])
        unreachable_count = len(result["unreachable"])
        total_flooded = len(flooded_people)

        times = result.get("times", [])
        avg_time = float(np.mean(times)) if times else 0
        max_time = float(max(times)) if times else 0

        # Routes as GeoJSON
        routes_geojson = _routes_to_geojson(result, G)

        # Center assignments
        center_summary = generate_evacuation_summary(result, safe_centers_gdf)

        return {
            "success": True,
            "algorithm": req.algorithm,
            "stats": {
                "total_flooded": total_flooded,
                "evacuated": evacuated_count,
                "unreachable": unreachable_count,
                "success_rate": round(evacuated_count / total_flooded * 100, 1) if total_flooded > 0 else 0,
                "avg_time": round(avg_time, 1),
                "max_time": round(max_time, 1),
                "execution_time": round(result.get("execution_time", 0), 2),
            },
            "routes_geojson": routes_geojson,
            "center_summary": _serialize_center_summary(center_summary),
            "log": result.get("log", [])[:50],  # Send first 50 log entries
            "detailed_log_text": detailed_log,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evacuation failed: {e}")


@router.post("/compare")
async def compare_algorithms(req: CompareRequest):
    """Run all 4 algorithms and return comparison data."""
    G = STORE.get("graph")
    impact = SIM_STORE.get("current_impact")
    safe_centers_gdf = EVAC_STORE.get("safe_centers_gdf")

    if G is None or impact is None or safe_centers_gdf is None:
        raise HTTPException(status_code=400, detail="Complete setup, simulation, and safe centers first")

    flooded_people = impact["flooded_people"]
    if flooded_people.empty:
        return {"success": True, "message": "No people in flood zone", "results": []}

    results = []
    for algo_name, algo_fn in ALGORITHMS.items():
        try:
            result = algo_fn(G, flooded_people, safe_centers_gdf, req.walking_speed)
            evac_count = len(result["evacuated"])
            times = result.get("times", [])

            results.append({
                "algorithm": algo_name,
                "success_rate": round(evac_count / len(flooded_people) * 100, 1) if len(flooded_people) > 0 else 0,
                "avg_time": round(float(np.mean(times)), 1) if times else 0,
                "max_time": round(float(max(times)), 1) if times else 0,
                "execution_time": round(result.get("execution_time", 0), 3),
                "evacuated": evac_count,
                "unreachable": len(result["unreachable"]),
            })
        except Exception as e:
            results.append({
                "algorithm": algo_name,
                "success_rate": 0,
                "avg_time": 0,
                "max_time": 0,
                "execution_time": 0,
                "evacuated": 0,
                "unreachable": len(flooded_people),
                "error": str(e),
            })

    # Determine best algorithm
    best = max(results, key=lambda r: r["success_rate"])

    return {"success": True, "results": results, "best_algorithm": best["algorithm"]}


@router.post("/email-authorities")
async def email_evacuation_plan(req: EmailRequest):
    """Send evacuation plan to all registered authorities."""
    try:
        from emergency_notifications import send_evacuation_plan_to_authorities

        researcher_data = {"name": "React User", "email": "", "phone": ""}
        evacuation_data = {
            "algorithm": req.algorithm,
            "evacuation_time": req.avg_time,
            "evacuated_count": req.evacuated_count,
            "total_at_risk": req.total_at_risk,
        }
        location_data = {
            "lat": STORE.get("lat", 0),
            "lon": STORE.get("lon", 0),
            "location_name": STORE.get("location_name", "Unknown"),
            "station_name": STORE.get("station_name", "Unknown"),
        }

        results = send_evacuation_plan_to_authorities(researcher_data, evacuation_data, location_data)
        return {"success": True, "total_sent": results.get("total_sent", 0)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email failed: {e}")


@router.get("/status")
async def evac_status():
    return {
        "safe_centers_loaded": EVAC_STORE.get("safe_centers_gdf") is not None,
        "evacuation_done": EVAC_STORE.get("evacuation_result") is not None,
    }


# ---------- Helpers ----------

def _routes_to_geojson(evacuation_result, G):
    """Convert evacuation routes to GeoJSON LineStrings."""
    features = []
    colors = ["#9C27B0", "#FF9800", "#2E7D32", "#E91E63", "#1565C0", "#5F9EA0", "#F44336"]

    for i, route in enumerate(evacuation_result.get("routes", [])):
        path = route.get("path", [])
        if len(path) < 2:
            continue

        coords = []
        for node in path:
            if node in G.nodes:
                nd = G.nodes[node]
                coords.append([nd["x"], nd["y"]])

        if len(coords) > 1:
            route_time = route.get("time", route.get("time_min", 0))
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "route_id": i + 1,
                    "time_min": round(route_time, 1),
                    "color": colors[i % len(colors)],
                    "person_id": str(route.get("person_id", route.get("person_idx", i + 1))),
                },
            })

    return {"type": "FeatureCollection", "features": features}


def _serialize_center_summary(summary):
    """Make center summary JSON-serializable."""
    result = {}
    for center_id, data in summary.items():
        result[center_id] = {
            "count": data.get("count", 0),
            "center_type": data.get("center_type", "unknown"),
            "avg_time": round(data.get("avg_time", 0), 1),
        }
    return result
