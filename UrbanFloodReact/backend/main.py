"""
main.py — Urban Flood Digital Twin API
─────────────────────────────────────
Thin FastAPI layer. All business logic lives in:
  coord_loader.py    — coordinate JSON loading
  rainfall_loader.py — Excel rainfall loading
  region_manager.py  — state store + OSMnx graph loading
  flood_simulator.py — physics simulation
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
import asyncio
import json
import pandas as pd
import uvicorn
import osmnx as ox

from region_manager import (
    initialise, get_region, norm_key,
    HOBLI_COORDS, RAINFALL_DATA, REGIONS_TREE, REGION_CACHE,
)
from flood_simulator import UrbanFloodSimulator


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("━━ Urban Flood Backend starting ━━")
    initialise()
    print("━━ Backend ready — regions lazy-loaded on demand ━━")
    yield
    print("━━ Backend shutting down ━━")


app = FastAPI(lifespan=lifespan, title="Urban Flood Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────────────────────
class LoadRegionRequest(BaseModel):
    hobli: str


# ══════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════

@app.get("/regions")
async def get_regions():
    """District → Taluk → [Hobli] cascade tree for the UI."""
    return REGIONS_TREE


@app.post("/load-region")
async def load_region(req: LoadRegionRequest):
    """
    Lazy-load OSMnx graph for a hobli.
    Returns centre coords so the frontend can pan the map.
    """
    key    = norm_key(req.hobli)
    coords = HOBLI_COORDS.get(key)
    if not coords:
        raise HTTPException(
            404,
            detail=f"Hobli '{req.hobli}' not in coordinate map.",
        )

    try:
        await asyncio.get_event_loop().run_in_executor(None, get_region, key)
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to load graph: {e}")

    return {
        "status":   "loaded",
        "hobli":    req.hobli,
        "lat":      coords["lat"],
        "lon":      coords["lon"],
        "district": coords["district"],
    }


@app.get("/rainfall-data/{hobli_name}")
async def get_rainfall_data(hobli_name: str):
    """Historical rainfall records for a hobli, sorted chronologically."""
    key     = norm_key(hobli_name)
    entries = RAINFALL_DATA.get(key)
    if not entries:
        raise HTTPException(404, detail=f"No rainfall data for '{hobli_name}'.")

    try:
        sorted_entries = sorted(
            entries,
            key=lambda e: pd.to_datetime(e["date"], dayfirst=True),
        )
    except Exception:
        sorted_entries = entries

    return {"hobli": hobli_name, "count": len(sorted_entries), "records": sorted_entries}


@app.get("/map-data")
async def get_map_data(hobli: str = Query(...)):
    """Road network GeoJSON for a loaded hobli."""
    key = norm_key(hobli)
    if key not in REGION_CACHE:
        raise HTTPException(400, detail=f"Region '{hobli}' not loaded. Call /load-region first.")
    G = REGION_CACHE[key]["G"]
    _, edges = ox.graph_to_gdfs(G)
    return json.loads(edges.to_json())


@app.get("/simulate-stream")
async def simulate_stream(
    hobli:        str   = Query(...),
    rainfall_mm:  float = Query(150.0),
    steps:        int   = Query(20),
    decay_factor: float = Query(0.5),
):
    """SSE stream of flood simulation steps."""
    key = norm_key(hobli)
    if key not in REGION_CACHE:
        raise HTTPException(400, detail=f"Region '{hobli}' not loaded. Call /load-region first.")

    entry  = REGION_CACHE[key]
    G_ref  = entry["G"]
    drains = entry["drain_nodes"]
    lakes  = entry["lake_nodes"]

    async def event_generator():
        sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)
        sim.initialize_from_drains(rainfall_mm)
        loop = asyncio.get_event_loop()

        for i in range(steps):
            await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
            impact    = await loop.run_in_executor(None, sim.calculate_flood_impact)
            flood_gdf = impact["flood_gdf"]
            roads_gdf = impact["roads_gdf"]

            step_data = {
                "step":          i + 1,
                "total":         steps,
                "flood_geojson": json.loads(flood_gdf.to_json()) if not flood_gdf.empty
                                 else {"type": "FeatureCollection", "features": []},
                "roads_geojson": json.loads(roads_gdf.to_json()) if not roads_gdf.empty
                                 else {"type": "FeatureCollection", "features": []},
            }
            yield f"data: {json.dumps(step_data)}\n\n"

        yield f"data: {json.dumps({'done': True, 'total': steps})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
