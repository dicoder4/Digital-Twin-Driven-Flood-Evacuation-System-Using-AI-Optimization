"""
Location & Network Routes
Handles station loading from CSV, road network loading, and infrastructure queries.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import os
import json
import pickle
import osmnx as ox
import networkx as nx
import geopandas as gpd
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

from osm_features import get_osm_features, load_road_network_with_filtering

router = APIRouter(prefix="/locations", tags=["Locations & Network"])

# ---------- Cache ----------
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# In-memory store for loaded data (per-session, survives across requests)
STORE = {
    "graph": None,
    "nodes": None,
    "edges": None,
    "hospitals_gdf": None,
    "police_gdf": None,
    "location_name": None,
    "lat": None,
    "lon": None,
    "station_name": None,
    "peak_flood_level": None,
}

# Geocoder (rate-limited)
_geolocator = Nominatim(user_agent="flood_sim_react_backend")
_geocode = RateLimiter(_geolocator.geocode, min_delay_seconds=1)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ---------- Pydantic Models ----------

class StationInfo(BaseModel):
    station: str
    district: str
    lat: float
    lon: float
    peak_flood_level: float

class NetworkLoadRequest(BaseModel):
    location_name: str
    lat: float
    lon: float
    station_name: str
    peak_flood_level: float = 5.0
    network_dist: int = 2000
    filter_minor: bool = True

class InfrastructureRequest(BaseModel):
    location_name: str


# ---------- Routes ----------

@router.get("/states")
async def get_states():
    """Return available states and their CSV files."""
    return {
        "states": [
            {"name": "Maharashtra", "file": "floods_with_districts_mh.csv"},
            {"name": "Karnataka", "file": "floods_with_districts_ka.csv"},
        ]
    }


@router.get("/stations")
async def get_stations(state: str = Query(...)):
    """Load CSV for a state — instant, NO geocoding. Returns station+district+peak_flood_level."""
    file_map = {
        "Maharashtra": "floods_with_districts_mh.csv",
        "Karnataka": "floods_with_districts_ka.csv",
    }

    if state not in file_map:
        raise HTTPException(status_code=400, detail=f"Unknown state: {state}")

    file_path = os.path.join(DATA_DIR, file_map[state])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"CSV file not found: {file_path}")

    df = pd.read_csv(file_path)
    if "Station" not in df.columns or "District" not in df.columns:
        raise HTTPException(status_code=400, detail="CSV must have 'Station' and 'District' columns")

    unique_stations = (
        df[["Station", "District"]].drop_duplicates().dropna().sort_values("Station").values.tolist()
    )

    station_list = []
    for station, district in unique_stations:
        flood_data = df[df["Station"] == station]["Peak Flood Level (m)"]
        peak = float(flood_data.max()) if not flood_data.empty else 5.0
        station_list.append({
            "station": station,
            "district": district,
            "peak_flood_level": peak,
        })

    return {"stations": station_list}


@router.get("/geocode")
def geocode_station(station: str = Query(...), district: str = Query(...), state: str = Query(...)):
    """Geocode a station with fallbacks: Station -> District -> State center."""
    # Sanitize inputs
    station = station.strip()
    district = district.strip()
    state = state.strip()
    
    # 1. Check Cache
    cache_key = f"geo_{station}_{district}_{state}".replace(" ", "_").replace("/", "_")
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            print(f"[CACHE] Geocode found for {station}")
            return json.load(f)

    # 2. Try Exact Match
    queries = [
        f"{station}, {district}, {state}, India",
        f"{station}, {state}, India",
        f"{district}, {state}, India",  # Fallback 1: District center
        f"{state}, India"               # Fallback 2: State center
    ]

    for q in queries:
        try:
            print(f"[GEO] Trying: {q}")
            loc = _geolocator.geocode(q, timeout=5)
            if loc:
                result = {
                    "lat": loc.latitude, 
                    "lon": loc.longitude, 
                    "location_name": q,
                    "display_name": loc.address
                }
                # Cache success
                with open(cache_path, "w") as f:
                    json.dump(result, f)
                print(f"[GEO] Success: {q} -> {loc.latitude}, {loc.longitude}")
                return result
        except Exception as e:
            print(f"[GEO] Error on {q}: {e}")
            continue

    # 3. If all fail, return hardcoded fallback (e.g. Bangalore) to prevent UI lockup
    print("[GEO] All strategies failed, using backup default")
    return {"lat": 12.9716, "lon": 77.5946, "location_name": "Bangalore (Fallback)", "warning": "Location not found, using default"}


@router.post("/network")
def load_network(req: NetworkLoadRequest):
    """Load road network via OSMnx — uses graph_from_point directly (fast) + aggressive caching."""
    import traceback
    global STORE

    try:
        cache_key = f"{req.lat:.4f}_{req.lon:.4f}_{req.network_dist}"
        graph_cache = os.path.join(CACHE_DIR, f"graph_{cache_key}.graphml")
        response_cache = os.path.join(CACHE_DIR, f"resp_{cache_key}.json")

        # Fast path: if we have a cached response, return it immediately
        if os.path.exists(response_cache) and os.path.exists(graph_cache):
            print(f"[CACHE] Using cached response for {cache_key}")
            G = ox.load_graphml(graph_cache)
            walking_speed_mpm = 5 * 1000 / 60
            for u, v, k, data in G.edges(keys=True, data=True):
                if "length" in data:
                    data["travel_time"] = data["length"] / walking_speed_mpm
                    data["weight"] = data["length"]
                    data["base_cost"] = data["length"]
                    data["penalty"] = 0
            nodes, edges = ox.graph_to_gdfs(G)
            STORE.update({
                "graph": G, "nodes": nodes, "edges": edges,
                "location_name": req.location_name, "lat": req.lat, "lon": req.lon,
                "station_name": req.station_name, "peak_flood_level": req.peak_flood_level,
            })
            with open(response_cache, "r") as f:
                return json.load(f)

        # Load from OSM
        print(f"[OSM] Loading network: ({req.lat}, {req.lon}), dist={req.network_dist}m ...")
        if os.path.exists(graph_cache):
            G = ox.load_graphml(graph_cache)
        else:
            G = ox.graph_from_point(
                (req.lat, req.lon), dist=req.network_dist, network_type='drive'
            )

            if G is None:
                raise HTTPException(status_code=500, detail="Failed to load road network")

            # Filter minor roads
            if req.filter_minor:
                minor_types = {'service', 'track', 'path', 'footway', 'bridleway'}
                edges_to_remove = []
                for u, v, k, d in G.edges(keys=True, data=True):
                    highway = d.get('highway')
                    if highway:
                        if isinstance(highway, str) and highway in minor_types:
                            edges_to_remove.append((u, v, k))
                        elif isinstance(highway, list) and any(hw in minor_types for hw in highway):
                            edges_to_remove.append((u, v, k))
                G.remove_edges_from(edges_to_remove)
                print(f"[FILTER] Removed {len(edges_to_remove)} minor road segments")

            ox.save_graphml(G, graph_cache)

        # Add travel-time attributes
        walking_speed_mpm = 5 * 1000 / 60
        for u, v, k, data in G.edges(keys=True, data=True):
            if "length" in data:
                data["travel_time"] = data["length"] / walking_speed_mpm
                data["weight"] = data["length"]
                data["base_cost"] = data["length"]
                data["penalty"] = 0

        nodes, edges = ox.graph_to_gdfs(G)

        STORE.update({
            "graph": G, "nodes": nodes, "edges": edges,
            "location_name": req.location_name, "lat": req.lat, "lon": req.lon,
            "station_name": req.station_name, "peak_flood_level": req.peak_flood_level,
        })

        edges_geojson = json.loads(edges.to_json())

        response = {
            "success": True,
            "num_nodes": len(nodes),
            "num_edges": len(edges),
            "edges_geojson": edges_geojson,
            "center": {"lat": req.lat, "lon": req.lon},
        }

        # Cache the serialized response for instant loads next time
        with open(response_cache, "w") as f:
            json.dump(response, f)

        print(f"[OK] Network loaded: {len(nodes)} nodes, {len(edges)} edges")
        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Network loading error: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Network loading failed: {type(e).__name__}: {str(e)}")


@router.post("/infrastructure")
def load_infrastructure(req: InfrastructureRequest):
    """Load hospitals and police stations from OSM — cached to disk."""
    global STORE

    if STORE["graph"] is None:
        raise HTTPException(status_code=400, detail="Load road network first")

    # Cache key based on location
    import hashlib
    cache_key = hashlib.md5(req.location_name.encode()).hexdigest()[:12]
    infra_cache = os.path.join(CACHE_DIR, f"infra_{cache_key}.json")

    # Fast path: cached response
    if os.path.exists(infra_cache):
        print(f"[CACHE] Using cached infrastructure for {req.location_name}")
        with open(infra_cache, "r") as f:
            return json.load(f)

    print(f"[OSM] Loading infrastructure for {req.location_name}...")
    hospitals_gdf = get_osm_features(req.location_name, {"amenity": "hospital"}, "hospital")
    police_gdf = get_osm_features(req.location_name, {"amenity": "police"}, "police station")

    STORE["hospitals_gdf"] = hospitals_gdf
    STORE["police_gdf"] = police_gdf

    result = {"hospitals": 0, "police": 0, "hospitals_geojson": None, "police_geojson": None}

    if hospitals_gdf is not None and not hospitals_gdf.empty:
        h_points = []
        for _, row in hospitals_gdf.iterrows():
            pt = row.geometry.centroid if hasattr(row.geometry, "centroid") else row.geometry
            h_points.append({
                "name": row.get("name", "Unnamed Hospital"),
                "type": "hospital",
                "lat": pt.y,
                "lon": pt.x,
            })
        result["hospitals"] = len(h_points)
        result["hospitals_geojson"] = h_points

    if police_gdf is not None and not police_gdf.empty:
        p_points = []
        for _, row in police_gdf.iterrows():
            pt = row.geometry.centroid if hasattr(row.geometry, "centroid") else row.geometry
            p_points.append({
                "name": row.get("name", "Unnamed Police Station"),
                "type": "police",
                "lat": pt.y,
                "lon": pt.x,
            })
        result["police"] = len(p_points)
        result["police_geojson"] = p_points

    # Cache to disk
    with open(infra_cache, "w") as f:
        json.dump(result, f)
    print(f"[OK] Infrastructure cached: {result['hospitals']} hospitals, {result['police']} police")

    return result


@router.get("/store-status")
async def store_status():
    """Return what's currently loaded in the backend store."""
    return {
        "graph_loaded": STORE["graph"] is not None,
        "infrastructure_loaded": STORE["hospitals_gdf"] is not None,
        "location_name": STORE.get("location_name"),
        "station_name": STORE.get("station_name"),
        "num_nodes": len(STORE["nodes"]) if STORE["nodes"] is not None else 0,
        "num_edges": len(STORE["edges"]) if STORE["edges"] is not None else 0,
    }
