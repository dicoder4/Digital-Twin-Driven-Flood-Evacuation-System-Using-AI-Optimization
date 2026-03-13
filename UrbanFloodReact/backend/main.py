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

from genai.param_resolver import resolve_hobli
from genai.weather_client import WeatherClient


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

class ExpertAdviceRequest(BaseModel):
    persona: str
    summary_data: dict

@app.post("/expert-advice-stream")
async def expert_advice_stream(req: ExpertAdviceRequest):
    import sys, os
    sys.path.append(os.path.join(os.path.dirname(__file__), "genai"))
    from expert_panel import stream_advice
    
    return StreamingResponse(
        stream_advice(req.persona, req.summary_data),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

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
    evacuation_mode: bool = Query(False),
    use_traffic: bool = Query(False),
    algorithm:   str  = Query("ga", description="Optimisation algorithm: 'ga', 'aco', or 'pso'"),
):
    """SSE stream of flood simulation steps."""
    return StreamingResponse(
        service.run_simulation_generator(
            hobli, rainfall_mm, steps, decay_factor,
            evacuation_mode, use_traffic, algorithm
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/simulate-compare")
async def simulate_compare(
    hobli:           str   = Query(...),
    rainfall_mm:     float = Query(150.0),
    steps:           int   = Query(20),
    decay_factor:    float = Query(0.5),
    evacuation_mode: bool  = Query(False),
    use_traffic:     bool  = Query(False),
):
    """
    SSE stream for algorithm comparison mode.
    Runs the flood simulation exactly once, then executes GA, ACO and PSO
    in parallel threads. Emits normal flood-step frames during the flood phase,
    then a single 'compare_done' frame with all three algorithm results.
    """
    return StreamingResponse(
        service.run_compare_generator(
            hobli, rainfall_mm, steps, decay_factor,
            evacuation_mode, use_traffic,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/shelters/{hobli_name}")
async def get_shelters(hobli_name: str):
    """
    Return raw shelter candidates for a hobli (OSM-extracted, disk-cached).
    Flood safety is evaluated on the frontend from live simulation state.
    """
    return await service.fetch_shelters(hobli_name)


@app.get("/weather/current")
async def get_current_weather(hobli: str = Query(..., description="Hobli name to fetch weather for")):
    """
    Fetch current real-time rainfall data for the specified hobli using Open-Meteo.
    """
    hobli_info = resolve_hobli(hobli)
    if not hobli_info:
        return {"error": f"Could not resolve hobli name: {hobli}"}
        
    client = WeatherClient.from_hobli_info(hobli_info)
    weather_data = client.get_current()
    if weather_data.get("source") == "error":
        return {"error": weather_data.get("description", "Unknown error fetching weather.")}
        
    return {
        "hobli": hobli_info.get("display", hobli),
        "rainfall_mm": weather_data.get("precipitation_mm", 0),
        "condition": weather_data.get("description", "Unknown"),
        "temp_c": weather_data.get("temp_c"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
