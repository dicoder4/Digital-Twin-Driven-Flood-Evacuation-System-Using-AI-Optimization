"""
service.py — Business logic for Urban Flood Digital Twin
────────────────────────────────────────────────────────
Following MVC architecture: This is the Service layer handling logic
between the API (Controller) and the Data/Simulators (Model).
"""

import asyncio
import json
import pandas as pd
import osmnx as ox
from fastapi import HTTPException

# Relative imports from the backend package
from region_manager import (
    get_region, norm_key,
    HOBLI_COORDS, RAINFALL_DATA, REGIONS_TREE, REGION_CACHE,
)
from flood_simulator import UrbanFloodSimulator
from generate_people import get_population
from shelter_generator import extract_shelter_candidates, filter_safe_shelters

async def get_all_regions():
    """Return the hierarchy tree of regions."""
    return REGIONS_TREE

async def get_hobli_population(hobli_name: str):
    """Business logic to fetch and format population data."""
    key = norm_key(hobli_name)
    data = get_population(key)
    if data:
        return {
            "hobli":            hobli_name,
            "total_population": data["total"],
            "male":             data["male"],
            "female":           data["female"],
            "matched_wards":    data["matched_wards"],
            "taluk":            data.get("taluk", ""),
            "source":           "csv",
        }
    return {
        "hobli":            hobli_name,
        "total_population": 0,
        "male":             0,
        "female":           0,
        "matched_wards":    [],
        "taluk":            "",
        "source":           "none",
    }

async def process_load_region(hobli_name: str):
    """Handle coordinate retrieval and graph lazy-loading."""
    key = norm_key(hobli_name)
    coords = HOBLI_COORDS.get(key)
    if not coords:
        raise HTTPException(status_code=404, detail=f"Hobli '{hobli_name}' not in coordinate map.")

    try:
        # Offload CPU-bound graph loading to executor
        await asyncio.get_event_loop().run_in_executor(None, get_region, key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load graph: {e}")

    return {
        "status":   "loaded",
        "hobli":    hobli_name,
        "lat":      coords["lat"],
        "lon":      coords["lon"],
        "district": coords["district"],
    }

async def fetch_rainfall_records(hobli_name: str):
    """Retrieve and sort rainfall records."""
    key = norm_key(hobli_name)
    entries = RAINFALL_DATA.get(key)
    if not entries:
        raise HTTPException(status_code=404, detail=f"No rainfall data for '{hobli_name}'.")

    try:
        sorted_entries = sorted(
            entries,
            key=lambda e: pd.to_datetime(e["date"], dayfirst=True),
        )
    except Exception:
        sorted_entries = entries

    return {"hobli": hobli_name, "count": len(sorted_entries), "records": sorted_entries}

async def fetch_map_geojson(hobli_name: str):
    """Retrieve graph and convert to GeoJSON."""
    key = norm_key(hobli_name)
    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli_name}' not loaded.")
    
    G = REGION_CACHE[key]["G"]
    # ox.graph_to_gdfs returns (nodes, edges)
    _, edges = ox.graph_to_gdfs(G)
    return json.loads(edges.to_json())

async def run_simulation_generator(hobli: str, rainfall_mm: float, steps: int, decay_factor: float):
    """Generator for SSE simulation stream."""
    key = norm_key(hobli)
    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli}' not loaded.")

    entry  = REGION_CACHE[key]
    G_ref  = entry["G"]
    drains = entry["drain_nodes"]
    lakes  = entry["lake_nodes"]

    sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)
    sim.initialize_from_drains(rainfall_mm)
    loop = asyncio.get_event_loop()

    for i in range(steps):
        # Step simulation
        await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
        # Calculate impact
        impact = await loop.run_in_executor(None, sim.calculate_flood_impact)
        
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


async def fetch_shelters(hobli_name: str) -> dict:
    """
    Extract shelter candidates for the hobli (OSM-queried, disk-cached).
    Safety evaluation happens on the frontend using live simulation state.
    """
    key = norm_key(hobli_name)

    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli_name}' not loaded.")

    entry  = REGION_CACHE[key]
    G      = entry["G"]
    coords = HOBLI_COORDS.get(key, {})
    lat    = coords.get("lat", G.nodes[list(G.nodes())[0]]["y"])
    lon    = coords.get("lon", G.nodes[list(G.nodes())[0]]["x"])

    loop = asyncio.get_event_loop()
    candidates = await loop.run_in_executor(
        None, extract_shelter_candidates, G, lat, lon, key
    )

    return {
        "hobli":    hobli_name,
        "total":    len(candidates),
        "shelters": candidates,
    }
