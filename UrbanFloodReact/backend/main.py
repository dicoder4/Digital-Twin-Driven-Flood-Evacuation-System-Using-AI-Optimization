"""
main.py — Urban Flood Digital Twin API
─────────────────────────────────────
Thin FastAPI layer. All business logic lives in:
  coord_loader.py    — coordinate JSON loading
  rainfall_loader.py — Excel rainfall loading
  region_manager.py  — state store + OSMnx graph loading
  flood_simulator.py — physics simulation
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional

try:
    from region_manager import initialise, norm_key, REGIONS_TREE
    from generate_people import load_population, POPULATION_CSV
except ImportError:
    # Try importing as package if top-level script
    from UrbanFloodReact.backend.region_manager import initialise, norm_key, REGIONS_TREE
    from UrbanFloodReact.backend.generate_people import load_population, POPULATION_CSV

# Import service layer
import service

from genai.param_resolver import resolve_hobli
from genai.weather_client import WeatherClient
import asyncio
from weather_watcher import router as automation_router, weather_watcher_loop


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("━━ Urban Flood Backend starting ━━")
    
    # Force load .env from project root
    env_path = Path(__file__).resolve().parents[2] / ".env"
    print(f"Loading .env from: {env_path}")
    load_dotenv(dotenv_path=env_path, override=True)
    
    print(f"DEBUG: GEMINI_API_KEY loaded: {os.getenv('GEMINI_API_KEY')}")
    print(f"DEBUG: GROQ_API_KEY loaded: {os.getenv('GROQ_API_KEY')}")
    initialise()
    load_population(POPULATION_CSV, REGIONS_TREE, norm_key)
    asyncio.create_task(weather_watcher_loop())
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

app.include_router(automation_router)


# ── Request models ─────────────────────────────────────────────────────────────
class LoadRegionRequest(BaseModel):
    hobli: str


# ══════════════════════════════════════════════════════
#  ENDPOINTS (Controller Layer)
# ══════════════════════════════════════════════════════

class ExpertAdviceRequest(BaseModel):
    persona: str
    summary_data: dict
    evacuation_plan: list = []

@app.post("/expert-advice-stream")
async def expert_advice_stream(req: ExpertAdviceRequest):
    from genai.context_builder import build_expert_context
    from genai.expert_panel import stream_advice
    
    # Enrich the raw summary data with severity tags, route stats, etc.
    enriched_context = await build_expert_context(req.summary_data, req.evacuation_plan)
    
    return StreamingResponse(
        stream_advice(req.persona, enriched_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


class ChatRequest(BaseModel):
    question: str
    context: dict
    evacuation_plan: list = []

@app.post("/evacuation-chat")
async def evacuation_chat(req: ChatRequest):
    from genai.evacuation_chat import stream_chat
    try:
        from genai.context_builder import build_expert_context
    except ImportError:
        from context_builder import build_expert_context
    
    # If it is a compare mode context, it's already structured for the LLM.
    if req.context.get("mode") == "compare":
        enriched_context = req.context
    else:
        # Build the full enriched context (with route details) for standard queries.
        enriched_context = await build_expert_context(req.context, req.evacuation_plan)
    
    return StreamingResponse(
        stream_chat(req.question, enriched_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


class MCPStateUpdate(BaseModel):
    summary_data: dict
    evacuation_plan: list = []
    hobli: str = ""

@app.post("/mcp-update-state")
async def mcp_update_state(req: MCPStateUpdate):
    """Push latest simulation state to the MCP evacuation server's in-memory store."""
    from genai.mcp_evacuation_server import update_state
    update_state(req.summary_data, req.evacuation_plan, req.hobli)
    return {"status": "ok", "message": "MCP state updated"}


class CopilotRequest(BaseModel):
    messages: list
    available_hoblis: list = []
    regions_tree: dict = {}
    map_pin: Optional[dict] = None

@app.post("/app-copilot")
async def app_copilot_endpoint(req: CopilotRequest):
    from genai.app_copilot import ask_copilot
    return await ask_copilot(req.messages, req.available_hoblis, req.regions_tree, req.map_pin)


@app.get("/regions")
async def get_regions():
    """District → Taluk → [Hobli] cascade tree for the UI."""
    return await service.get_all_regions()

class TransportPlanRequest(BaseModel):
    evacuation_plan: list

@app.post("/public-transport-plan")
async def public_transport_plan(req: TransportPlanRequest):
    """Generate an on-demand bus fleet manifest based on GTFS data and ACO routes."""
    from genai.transport_agent import compute_bus_evacuation_plan
    
    plan_result = compute_bus_evacuation_plan(req.evacuation_plan)
    return plan_result

@app.get("/population/{hobli_name}")
async def population(hobli_name: str):
    """Return population data for a hobli."""
    return await service.get_hobli_population(hobli_name)


@app.get("/resources/{location_name}")
async def get_resources(location_name: str):
    """Fetch available resources for a location."""
    print(f"[DEBUG] API HIT: /resources/{location_name}", flush=True)
    results = await service.fetch_resources(location_name)
    print(f"[DEBUG] API RESULT COUNT: {len(results)}", flush=True)
    return results


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
    population:  int | None = Query(None, description="Override population count"),
):
    """SSE stream of flood simulation steps."""
    return StreamingResponse(
        service.run_simulation_generator(
            hobli, rainfall_mm, steps, decay_factor,
            evacuation_mode, use_traffic, algorithm, population
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
    population:      int | None = Query(None),
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
            evacuation_mode, use_traffic, population
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
