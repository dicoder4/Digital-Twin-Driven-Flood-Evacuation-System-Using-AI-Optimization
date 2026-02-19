"""
Simulation Routes
Wraps the DynamicFloodSimulator for the React frontend.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import geopandas as gpd
from shapely.geometry import Point

from dynamic_flood_simulator import DynamicFloodSimulator, create_elevation_grid
from risk_assessment import calculate_risk_level, generate_risk_recommendations
from location_routes import STORE

router = APIRouter(prefix="/simulation", tags=["Flood Simulation"])

# In-memory simulator instance
SIM_STORE = {
    "simulator": None,
    "elev_gdf": None,
    "current_impact": None,
    "flood_level": 0,
    "num_people": 50,
}


class SimInitRequest(BaseModel):
    initial_people: int = 50

class SimUpdateRequest(BaseModel):
    flood_level: float = 0.2   # 0.0 – 1.0
    num_people: int = 50


@router.post("/init")
def init_simulator(req: SimInitRequest):
    """Initialize the DynamicFloodSimulator using the loaded road network."""
    global SIM_STORE

    if STORE["graph"] is None or STORE["edges"] is None:
        raise HTTPException(status_code=400, detail="Load road network first via /locations/network")

    try:
        elev_gdf = create_elevation_grid(STORE["edges"])

        simulator = DynamicFloodSimulator(
            elev_gdf=elev_gdf,
            edges=STORE["edges"],
            nodes=STORE["nodes"],
            station=STORE.get("station_name", "Unknown"),
            lat=STORE["lat"],
            lon=STORE["lon"],
            peak_flood_level=STORE.get("peak_flood_level", 11.0), # Default if missing
            initial_people=req.initial_people,
        )

        SIM_STORE.update({
            "simulator": simulator,
            "elev_gdf": elev_gdf,
            "current_impact": None,
            "flood_level": 0,
            "num_people": req.initial_people,
        })

        return {"success": True, "message": "Simulator initialized", "people_count": req.initial_people}

    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to initialize simulator: {e}")


@router.post("/update")
def update_simulation(req: SimUpdateRequest):
    """Run one simulation snapshot at a given flood level and people count."""
    global SIM_STORE

    sim = SIM_STORE.get("simulator")
    if sim is None:
        raise HTTPException(status_code=400, detail="Initialize simulator first via /simulation/init")

    try:
        sim.update_people_count(req.num_people)
        impact = sim._calculate_flood_impact(req.flood_level)

        SIM_STORE["current_impact"] = impact
        SIM_STORE["flood_level"] = req.flood_level
        SIM_STORE["num_people"] = req.num_people

        # Build response
        total_people = len(sim.people_gdf)
        flooded_count = len(impact["flooded_people"])
        safe_count = len(impact["safe_people"])

        risk_level, risk_pct = calculate_risk_level(flooded_count, total_people)
        recommendations = generate_risk_recommendations(risk_level, risk_pct)

        # Convert GeoDataFrames to GeoJSON for the frontend
        flood_geojson = _gdf_to_geojson(impact["flood_gdf"])
        blocked_roads_geojson = _gdf_to_geojson(impact["blocked_edges"])

        # People points
        people_geojson = _people_to_geojson(sim.people_gdf, impact["flooded_people"], impact["safe_people"])

        return {
            "success": True,
            "flood_level": req.flood_level,
            "stats": {
                "total_people": total_people,
                "flooded_people": flooded_count,
                "safe_people": safe_count,
                "risk_level": risk_level,
                "risk_pct": round(risk_pct, 1),
                "recommendations": recommendations,
            },
            "flood_geojson": flood_geojson,
            "blocked_roads_geojson": blocked_roads_geojson,
            "people_geojson": people_geojson,
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}")


@router.get("/status")
async def sim_status():
    """Check if simulator is initialized and what state it's in."""
    sim = SIM_STORE.get("simulator")
    return {
        "initialized": sim is not None,
        "flood_level": SIM_STORE.get("flood_level", 0),
        "num_people": SIM_STORE.get("num_people", 0),
        "has_impact": SIM_STORE.get("current_impact") is not None,
    }


# ---------- Helpers ----------

def _gdf_to_geojson(gdf):
    """Safely convert a GeoDataFrame to a GeoJSON dict."""
    if gdf is None or gdf.empty:
        return {"type": "FeatureCollection", "features": []}
    return json.loads(gdf.to_json())


def _people_to_geojson(all_people_gdf, flooded_gdf, safe_gdf):
    """Build a combined GeoJSON of people with a 'status' property."""
    features = []

    flooded_ids = set()
    if not flooded_gdf.empty and "person_id" in flooded_gdf.columns:
        flooded_ids = set(flooded_gdf["person_id"].tolist())

    for _, row in all_people_gdf.iterrows():
        pid = row.get("person_id", "")
        status = "danger" if pid in flooded_ids else "safe"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row.geometry.x, row.geometry.y]},
            "properties": {"person_id": str(pid), "status": status},
        })

    return {"type": "FeatureCollection", "features": features}
