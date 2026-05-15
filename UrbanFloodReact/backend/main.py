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
import logging
import warnings

# Suppress MongoDB boolean check warning at all levels
warnings.filterwarnings("ignore", message=".*Database objects do not implement truth value testing.*")
warnings.simplefilter("ignore", DeprecationWarning)

class MongoWarningFilter(logging.Filter):
    def filter(self, record):
        return "Database objects do not implement truth value testing" not in record.getMessage()

# Configure logging EARLY so all module loggers are captured
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s',
    handlers=[logging.StreamHandler()]
)

# Add filter to all handlers
for handler in logging.root.handlers:
    handler.addFilter(MongoWarningFilter())

# Set uvicorn loggers to INFO to capture MongoDB logs
for logger_name in ['db', 'region_manager', 'shelter_generator', 'gis_terrain_loader', 'service']:
    logger_obj = logging.getLogger(logger_name)
    logger_obj.setLevel(logging.INFO)
    logger_obj.addFilter(MongoWarningFilter())

# Ensure backend directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional

try:
    from region_manager import initialise, norm_key, REGIONS_TREE, REGION_CACHE, HOBLI_COORDS
    from generate_people import load_population, POPULATION_CSV
except ImportError:
    # Try importing as package if top-level script
    from UrbanFloodReact.backend.region_manager import initialise, norm_key, REGIONS_TREE, REGION_CACHE, HOBLI_COORDS
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
    print("== Urban Flood Backend starting ==")

    # Force load .env from project root
    env_path = Path(__file__).resolve().parents[2] / ".env"
    print(f"Loading .env from: {env_path}")
    load_dotenv(dotenv_path=env_path, override=True)

    print(f"DEBUG: GEMINI_API_KEY loaded: {os.getenv('GEMINI_API_KEY')}")
    print(f"DEBUG: GROQ_API_KEY loaded: {os.getenv('GROQ_API_KEY')}")

    # Bootstrap MongoDB
    try:
        from db import bootstrap_mongo_data
        bootstrap_mongo_data()
    except Exception as e:
        print(f"[MONGO DEBUG] Bootstrap failed: {e}")

    # Clear any old simulation sessions from previous server run
    from simulate_routes import SIMULATE_SESSIONS
    SIMULATE_SESSIONS.clear()
    print("== Cleared old simulation sessions ==")

    initialise()
    load_population(POPULATION_CSV, REGIONS_TREE, norm_key)
    asyncio.create_task(weather_watcher_loop())
    print("== Backend ready — regions lazy-loaded on demand ==")
    yield
    print("== Backend shutting down ==")




class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/automation/status" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

app = FastAPI(lifespan=lifespan, title="Urban Flood Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5174", "http://127.0.0.1:5174",
                   "http://localhost:5175", "http://127.0.0.1:5175",
                   "http://localhost:5176", "http://127.0.0.1:5176",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from auth_routes import router as auth_router
from notification_routes import router as notification_router
from citizen_routes import citizen_router
from simulate_routes import simulate_router

app.include_router(automation_router)
app.include_router(auth_router)
app.include_router(notification_router)
app.include_router(citizen_router)
app.include_router(simulate_router)


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
    
    # Direct handling for Compare and Analysis modes
    import json as _json
    # Debug log incoming chat request context for troubleshooting AlgoAnalysis
    try:
        print(f"[DEBUG] /evacuation-chat hit. mode={req.context.get('mode')}", flush=True)
        print(f"[DEBUG] /evacuation-chat context keys: {list(req.context.keys())}", flush=True)
        if 'algorithm_analysis' in req.context:
            print("[DEBUG] /evacuation-chat algorithm_analysis payload:", _json.dumps(req.context.get('algorithm_analysis'), default=str)[:2000], flush=True)
    except Exception as _e:
        print(f"[DEBUG] Failed to print evac-chat debug payload: {_e}", flush=True)

    if req.context.get("mode") == "compare":
        enriched_context = req.context
    elif req.context.get("mode") == "analysis":
        # Pass the metrics through as the algorithm analysis part of the context
        mock_summary = {"simulation_location": req.context.get("location", "Unknown"), "algorithm": "Multi-Algo Analysis"}
        enriched_context = await build_expert_context(mock_summary, algorithm_analysis=req.context.get("metrics"))
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


# ── Research: MCP vs Non-MCP A/B comparison ───────────────────────────────────
class MCPComparisonRequest(BaseModel):
    questions: list = []        # if empty, uses DEFAULT_QUESTIONS
    summary_data: Optional[dict] = None      # if None, reads from MongoDB mcp_state
    evacuation_plan: list = []
    run_judge: bool = True

@app.post("/research/mcp-comparison")
async def research_mcp_comparison(req: MCPComparisonRequest):
    """
    Run MCP vs non-MCP A/B comparison over one or more questions against the
    current simulation state. Returns per-question side-by-side responses
    plus auto metrics and (optional) LLM-judge scores.
    """
    from genai.mcp_evaluator import compare_many, DEFAULT_QUESTIONS
    try:
        from genai.context_builder import build_expert_context
    except ImportError:
        from context_builder import build_expert_context
    from genai.mcp_evacuation_server import _load_state

    summary_data    = req.summary_data
    evacuation_plan = req.evacuation_plan or []

    if not summary_data:
        state = _load_state()
        summary_data    = state.get("summary_data") or {}
        evacuation_plan = state.get("evacuation_plan") or []
        if not summary_data:
            raise HTTPException(
                status_code=400,
                detail="No simulation state available. Run a simulation first or supply summary_data."
            )

    enriched = await build_expert_context(summary_data, evacuation_plan)
    questions = req.questions or DEFAULT_QUESTIONS

    try:
        results = await asyncio.wait_for(
            compare_many(questions, enriched, run_judge=req.run_judge),
            timeout=290.0,  # 290s hard cap — just under browser's 5-min timeout
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Comparison timed out. Both Gemini and Groq API quotas are likely exhausted. Try again after midnight PST (~12:30 PM IST) when quotas reset."
        )

    return {"count": len(results), "results": results}


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
    mode:        str  = Query("progressive", description="Rainfall mode: 'progressive' or 'instant'"),
    extra_shelters_json: str | None = Query(None, description="JSON array of suggested shelter objects"),
):
    """SSE stream of flood simulation steps."""
    import json as _json
    extra = None
    if extra_shelters_json:
        try:
            extra = _json.loads(extra_shelters_json)
        except Exception:
            extra = None
    return StreamingResponse(
        service.run_simulation_generator(
            hobli, rainfall_mm, steps, decay_factor,
            evacuation_mode, use_traffic, algorithm, population,
            extra_shelters=extra, mode=mode,
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
    mode:            str  = Query("progressive", description="Rainfall mode: 'progressive' or 'instant'"),
    extra_shelters_json: str | None = Query(None, description="JSON array of suggested shelter objects"),
):
    """
    SSE stream for algorithm comparison mode.
    Runs the flood simulation exactly once, then executes GA, ACO and PSO
    in parallel threads. Emits normal flood-step frames during the flood phase,
    then a single 'compare_done' frame with all three algorithm results.
    """
    import json as _json
    extra = None
    if extra_shelters_json:
        try:
            extra = _json.loads(extra_shelters_json)
        except Exception:
            extra = None
    return StreamingResponse(
        service.run_compare_generator(
            hobli, rainfall_mm, steps, decay_factor,
            evacuation_mode, use_traffic, population,
            extra_shelters=extra, mode=mode,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@app.get("/simulate-analysis")
async def simulate_analysis(
    hobli:           str   = Query(...),
    rainfall_mm:     float = Query(150.0),
    steps:           int   = Query(20),
    decay_factor:    float = Query(0.5),
    population:      int | None = Query(None),
    use_traffic:     bool  = Query(False),
    iterations:      int | None = Query(None, description="Override iteration count for all algorithms (e.g. 100 for deep analysis)"),
):
    """
    SSE stream for advanced algorithm performance analysis.
    Runs each algorithm 3 times to compute stability, convergence, and diversity.
    Pass iterations=100 for deep analysis with better ACO pheromone convergence.
    """
    return StreamingResponse(
        service.run_advanced_analysis_generator(
            hobli, rainfall_mm, steps, decay_factor,
            population=population, use_traffic=use_traffic,
            iterations_override=iterations,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@app.get("/simulate-scenario-analysis")
async def simulate_scenario_analysis(
    hobli:           str   = Query(...),
    steps:           int   = Query(20),
    decay_factor:    float = Query(0.5),
    population:      int | None = Query(None),
    use_traffic:     bool  = Query(False),
):
    """
    SSE stream for scenario algorithm performance analysis.
    Runs each algorithm across Low(50mm), Medium(150mm), and High(250mm) scenarios.
    """
    return StreamingResponse(
        service.run_scenario_analysis_generator(
            hobli, steps, decay_factor,
            population=population, use_traffic=use_traffic,
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
        "source": weather_data.get("source", "unknown"),
        "humidity": weather_data.get("humidity"),
        "cloud_cover": weather_data.get("cloud_cover"),
    }


@app.get("/metro-stations/{hobli_name}")
async def get_metro_stations(hobli_name: str):
    """Return cached metro stations for a hobli."""
    return await service.fetch_metro_stations(hobli_name)


class ResolvePinRequest(BaseModel):
    lat: float
    lon: float

@app.post("/resolve-pin")
async def resolve_pin(req: ResolvePinRequest):
    """Find the nearest hobli to a given lat/lon coordinate using haversine distance.
    Only considers hoblis present in REGIONS_TREE (i.e. those with rainfall data and
    full simulation support), so the returned hobli is always fully functional.
    """
    import math

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Build set of norm_keys that are valid (present in REGIONS_TREE with rainfall data)
    valid_keys: set[str] = set()
    for district_data in REGIONS_TREE.values():
        for hobli_list in district_data.values():
            for display_name in hobli_list:
                valid_keys.add(norm_key(display_name))

    # Search candidates: prefer REGIONS_TREE hoblis; fall back to all HOBLI_COORDS if tree is empty
    candidate_keys = valid_keys if valid_keys else set(HOBLI_COORDS.keys())

    best_key, best_dist, best_name = None, float('inf'), None
    for key in candidate_keys:
        info = HOBLI_COORDS.get(key)
        if not info:
            continue
        hlat = info.get("lat") or info.get("latitude")
        hlon = info.get("lon") or info.get("lng") or info.get("longitude")
        if hlat is None or hlon is None:
            continue
        d = haversine(req.lat, req.lon, float(hlat), float(hlon))
        if d < best_dist:
            best_dist = d
            best_key = key
            best_name = info.get("original_name") or info.get("display") or key

    if best_key is None:
        raise HTTPException(status_code=404, detail="No hobli coordinates found in registry")

    return {
        "hobli_name": best_name,
        "hobli_key": best_key,
        "distance_km": round(best_dist, 2),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

class AlgorithmAnalysisRequest(BaseModel):
    metrics: dict   # the output from run_advanced_analysis_generator
    location: str

@app.post("/algorithm-analysis-stream")
async def algorithm_analysis_stream(req: AlgorithmAnalysisRequest):
    from genai.expert_panel import stream_algorithm_analysis
    return StreamingResponse(
        stream_algorithm_analysis(req.metrics, req.location),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

class ScenarioAnalysisRequest(BaseModel):
    metrics: dict
    location: str

@app.post("/scenario-analysis-stream")
async def scenario_analysis_stream(req: ScenarioAnalysisRequest):
    from genai.expert_panel import stream_scenario_analysis
    return StreamingResponse(
        stream_scenario_analysis(req.metrics, req.location),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
