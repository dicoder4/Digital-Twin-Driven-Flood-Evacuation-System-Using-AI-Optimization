from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import osmnx as ox
import networkx as nx
import geopandas as gpd
import json
import asyncio
import uvicorn
from contextlib import asynccontextmanager
import os
import pickle
import numpy as np
import shapely.geometry
import hashlib

# Simple in-memory cache for simulation results
SIMULATION_CACHE = {}



# Import simulation logic (ensure flood_simulator.py is in same folder)
from flood_simulator import UrbanFloodSimulator

# Global variables
# Global variables
G_urban = None
drain_nodes = []
lake_nodes = []

# Cache Setup
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
GRAPH_FILE = os.path.join(CACHE_DIR, "btm_graph.graphml")
FEATURES_FILE = os.path.join(CACHE_DIR, "features.pkl")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load graph on startup
    global G_urban, drain_nodes, lake_nodes
    print("Initializing Urban Flood Backend...")

    # 1. Load Graph
    if os.path.exists(GRAPH_FILE):
        print(f"Loading cached graph from {GRAPH_FILE}...")
        G_urban = ox.load_graphml(GRAPH_FILE)
    else:
        print("Downloading BTM Layout Graph via OSMnx (this may take time)...")
        try:
            # BTM Layout Center
            btm_center = (12.9166, 77.6101)
            G_urban = ox.graph_from_point(btm_center, dist=2000, dist_type='bbox', network_type="drive")
            # Save to cache
            print("Caching graph...")
            ox.save_graphml(G_urban, GRAPH_FILE)
        except Exception as e:
            print(f"Error loading graph: {e}")
            yield
            return

    # 2. Load Features (Drains & Lakes)
    if os.path.exists(FEATURES_FILE):
        print(f"Loading cached features from {FEATURES_FILE}...")
        try:
            with open(FEATURES_FILE, 'rb') as f:
                data = pickle.load(f)
                drain_nodes = data['drains']
                lake_nodes = data['lakes']
        except Exception as e:
            print(f"Error reading feature cache: {e}. Re-downloading.")
            drain_nodes = []
            lake_nodes = []
    
    if not drain_nodes and not lake_nodes:
        # Download features if not cached or cache failed
        btm_center = (12.9166, 77.6101)
        
        # --- Drains ---
        print("Downloading Waterways/Drains...")
        try:
            waterways = ox.features_from_point(btm_center, tags={'waterway': ['drain', 'stream', 'ditch', 'canal']}, dist=2000)
            if not waterways.empty:
                centroids = waterways.geometry.centroid
                drain_xs = centroids.x.to_list()
                drain_ys = centroids.y.to_list()
                drain_nodes = ox.nearest_nodes(G_urban, drain_xs, drain_ys)
                # Ensure list
                if not isinstance(drain_nodes, list):
                    drain_nodes = list(drain_nodes) if hasattr(drain_nodes, '__iter__') else [drain_nodes]
                print(f"Identified {len(drain_nodes)} drain nodes.")
            else:
                drain_nodes = []
        except Exception as e:
            print(f"Could not load waterways: {e}")
            drain_nodes = []

        # --- Lakes ---
        print("Downloading Lakes/Water Bodies...")
        try:
            # Broader tags for lakes
            lake_tags = {
                'natural': 'water',
                'water': ['lake', 'pond', 'reservoir'],
                'landuse': ['reservoir', 'basin']
            }
            lakes = ox.features_from_point(btm_center, tags=lake_tags, dist=2000)
            
            lake_points = []
            if not lakes.empty:
                print(f"Found {len(lakes)} water bodies.")
                for idx, row in lakes.iterrows():
                    geom = row.geometry
                    # We want points along the boundary to act as flood sources
                    if geom.geom_type in ['Polygon', 'MultiPolygon']:
                        # Get exterior coords
                        if geom.geom_type == 'Polygon':
                            polys = [geom]
                        else:
                            polys = geom.geoms
                        
                        for poly in polys:
                            # Sample points along the exterior ring every ~20 meters
                            exterior = poly.exterior
                            length = exterior.length # decimal degrees, approx
                            # 1 degree lat ~ 111km. 0.0002 ~ 20m
                            # Simple sampling: interpolate
                            num_samples = int(length / 0.0002) 
                            if num_samples < 5: num_samples = 5 # ensure at least corners
                            
                            for i in range(num_samples):
                                pt = exterior.interpolate(i/num_samples, normalized=True)
                                lake_points.append((pt.x, pt.y))
                    else:
                        lake_points.append((geom.centroid.x, geom.centroid.y))
                
                # Unique
                lake_points = list(set(lake_points))
                
                if lake_points:
                    l_xs = [p[0] for p in lake_points]
                    l_ys = [p[1] for p in lake_points]
                    lake_nodes = ox.nearest_nodes(G_urban, l_xs, l_ys)
                     # Ensure list
                    if not isinstance(lake_nodes, list):
                        lake_nodes = list(lake_nodes) if hasattr(lake_nodes, '__iter__') else [lake_nodes]
                    print(f"Mapped lakes to {len(lake_nodes)} graph nodes.")
                else:
                    lake_nodes = []
            else:
                lake_nodes = []
        except Exception as e:
            print(f"Could not load lakes: {e}")
            lake_nodes = []

        # Save to cache
        print("Caching features...")
        with open(FEATURES_FILE, 'wb') as f:
            pickle.dump({'drains': drain_nodes, 'lakes': lake_nodes}, f)

    print("Backend Ready.")
    yield
    # Cleanup if needed

app = FastAPI(lifespan=lifespan)

# CORS — list all likely dev ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{p}" for p in range(5173, 5181)
    ] + [
        f"http://127.0.0.1:{p}" for p in range(5173, 5181)
    ] + ["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register new route modules
from auth_routes import router as auth_router
from location_routes import router as location_router
from simulation_routes import router as simulation_router
from evacuation_routes import router as evacuation_router

app.include_router(auth_router)
app.include_router(location_router)
app.include_router(simulation_router)
app.include_router(evacuation_router)

class SimulationParams(BaseModel):
    rainfall_mm: float = 150.0
    steps: int = 20
    decay_factor: float = 0.5

@app.get("/map-data")
async def get_map_data():
    """Return the road network as GeoJSON"""
    global G_urban
    if not G_urban:
        raise HTTPException(status_code=503, detail="Graph not loaded yet")
    
    nodes, edges = ox.graph_to_gdfs(G_urban)
    return json.loads(edges.to_json())


@app.post("/simulate")
async def run_simulation(params: SimulationParams):
    """Run simulation and return all steps at once (cached)"""
    global G_urban, drain_nodes, lake_nodes, SIMULATION_CACHE
    if not G_urban:
        raise HTTPException(status_code=503, detail="Graph not loaded yet")

    param_key = f"{params.rainfall_mm}_{params.steps}_{params.decay_factor}"
    if param_key in SIMULATION_CACHE:
        print(f"Returning cached simulation for {param_key}")
        return SIMULATION_CACHE[param_key]

    print(f"Running new simulation for {param_key}...")
    sim = UrbanFloodSimulator(G_urban.copy(), drain_nodes=drain_nodes, lake_nodes=lake_nodes)
    sim.initialize_from_drains(params.rainfall_mm)

    simulation_steps = []
    for i in range(params.steps):
        sim.propagate_flood_step(decay_factor=params.decay_factor)
        impact = sim.calculate_flood_impact()
        flood_gdf = impact['flood_gdf']
        roads_gdf = impact['roads_gdf']
        simulation_steps.append({
            "step": i + 1,
            "flood_geojson": json.loads(flood_gdf.to_json()) if not flood_gdf.empty else {"type": "FeatureCollection", "features": []},
            "roads_geojson": json.loads(roads_gdf.to_json()) if not roads_gdf.empty else {"type": "FeatureCollection", "features": []}
        })

    result = {"steps": simulation_steps}
    SIMULATION_CACHE[param_key] = result
    return result


@app.get("/simulate-stream")
async def simulate_stream(
    rainfall_mm: float = Query(150.0),
    steps: int = Query(20),
    decay_factor: float = Query(0.5)
):
    """Stream simulation steps as Server-Sent Events — one event per step, sent immediately after computation."""
    global G_urban, drain_nodes, lake_nodes
    if not G_urban:
        raise HTTPException(status_code=503, detail="Graph not loaded yet")

    async def event_generator():
        sim = UrbanFloodSimulator(G_urban.copy(), drain_nodes=drain_nodes, lake_nodes=lake_nodes)
        sim.initialize_from_drains(rainfall_mm)

        for i in range(steps):
            # Run one physics step (CPU-bound — run in thread to avoid blocking event loop)
            await asyncio.get_event_loop().run_in_executor(
                None, sim.propagate_flood_step, decay_factor
            )

            # Compute impact in thread too
            impact = await asyncio.get_event_loop().run_in_executor(
                None, sim.calculate_flood_impact
            )

            flood_gdf = impact['flood_gdf']
            roads_gdf = impact['roads_gdf']

            step_data = {
                "step": i + 1,
                "total": steps,
                "flood_geojson": json.loads(flood_gdf.to_json()) if not flood_gdf.empty else {"type": "FeatureCollection", "features": []},
                "roads_geojson": json.loads(roads_gdf.to_json()) if not roads_gdf.empty else {"type": "FeatureCollection", "features": []}
            }

            # SSE format: "data: <json>\n\n"
            yield f"data: {json.dumps(step_data)}\n\n"

        # Signal completion
        yield f"data: {json.dumps({'done': True, 'total': steps})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if behind proxy
        }
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
