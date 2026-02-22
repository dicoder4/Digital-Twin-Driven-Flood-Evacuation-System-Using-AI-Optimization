"""
main.py — Urban Flood Digital Twin API
─────────────────────────────────────
Thin FastAPI layer. All business logic lives in:
  coord_loader.py    — coordinate JSON loading
  rainfall_loader.py — Excel rainfall loading
  region_manager.py  — state store + OSMnx graph loading
  flood_simulator.py — physics simulation
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel

from region_manager import initialise, norm_key, REGIONS_TREE
from generate_people import load_population, POPULATION_CSV

# Import service layer
import service


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("━━ Urban Flood Backend starting ━━")
    initialise()
    load_population(POPULATION_CSV, REGIONS_TREE, norm_key)
    print("━━ Backend ready — regions lazy-loaded on demand ━━")
    yield
    print("━━ Backend shutting down ━━")


app = FastAPI(lifespan=lifespan, title="Urban Flood Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://127.0.0.1:5174",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ─────────────────────────────────────────────────────────────
class LoadRegionRequest(BaseModel):
    hobli: str


# ══════════════════════════════════════════════════════
#  ENDPOINTS (Controller Layer)
# ══════════════════════════════════════════════════════

@app.get("/regions")
async def get_regions():
    """District → Taluk → [Hobli] cascade tree for the UI."""
    return await service.get_all_regions()


@app.get("/population/{hobli_name}")
async def population(hobli_name: str):
    """Return population data for a hobli."""
    return await service.get_hobli_population(hobli_name)


@app.post("/load-region")
async def load_region(req: LoadRegionRequest):
    """Lazy-load OSMnx graph for a hobli."""
    return await service.process_load_region(req.hobli)


@app.get("/rainfall-data/{hobli_name}")
async def get_rainfall_data(hobli_name: str):
    """Historical rainfall records for a hobli, sorted chronologically."""
    return await service.fetch_rainfall_records(hobli_name)


@app.get("/map-data")
async def get_map_data(hobli: str = Query(...)):
    """Road network GeoJSON for a loaded hobli."""
    return await service.fetch_map_geojson(hobli)


@app.get("/simulate-stream")
async def simulate_stream(
    hobli:        str   = Query(...),
    rainfall_mm:  float = Query(150.0),
    steps:        int   = Query(20),
    decay_factor: float = Query(0.5),
):
    """SSE stream of flood simulation steps."""
    return StreamingResponse(
        service.run_simulation_generator(hobli, rainfall_mm, steps, decay_factor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
