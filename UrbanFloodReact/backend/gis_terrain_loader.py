import os
import requests
import rasterio
import numpy as np
import networkx as nx
from pathlib import Path

# Fix: cache dir is in backend/cache, not backend/data, to match region_manager
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def download_srtm_dem(min_lon: float, min_lat: float, max_lon: float, max_lat: float, filename: str) -> Path:
    """
    Download a DEM (GeoTIFF) from OpenTopography SRTM GL3 (90m, free tier) API for a bounding box.
    SRTM GL3 is used because it has less strict API limits for unauthenticated users
    Returns the path to the cached file.
    """
    dem_path = CACHE_DIR / filename
    if dem_path.exists():
        return dem_path

    # Public OpenTopography API for SRTM GL3 (90m)
    # The API takes bounds in: west, south, east, north
    url = f"https://portal.opentopography.org/API/globaldem?demtype=SRTMGL3&south={min_lat}&north={max_lat}&west={min_lon}&east={max_lon}&outputFormat=GTiff"
    
    # OpenTopography now highly recommends or requires API keys for REST endpoints
    api_key = os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if api_key:
        url += f"&API_Key={api_key}"
        
    print(f"  [gis] Downloading DEM from OpenTopography (this may take 5-10s)...")
    r = requests.get(url, timeout=60)
    
    if r.status_code == 401 or r.status_code == 403:
         raise Exception("OpenTopography API authentication required or rate limit reached. Get a free key at portal.opentopography.org and set OPENTOPOGRAPHY_API_KEY.")
         
    r.raise_for_status()
    
    with open(dem_path, "wb") as f:
        f.write(r.content)
        
    return dem_path

def enrich_graph_elevation(G: nx.MultiDiGraph, center_lat: float, center_lon: float, radius_m: float = 2000):
    """
    Downloads SRTM DEM for the graph's bounding box and samples elevation for every node.
    Adds an 'elevation' attribute to each node in the graph.
    """
    if not G.nodes:
        return G
        
    # Calculate rough bounding box (using 1 degree approx 111km)
    buffer_deg = (radius_m / 111000.0) * 1.5 # add 50% buffer to be safe
    min_lon = center_lon - buffer_deg
    max_lon = center_lon + buffer_deg
    min_lat = center_lat - buffer_deg
    max_lat = center_lat + buffer_deg

    # Create a stable filename based on center coords
    filename = f"dem_{center_lat:.3f}_{center_lon:.3f}.tif"
    
    try:
        dem_path = download_srtm_dem(min_lon, min_lat, max_lon, max_lat, filename)
        
        # Sample elevations
        with rasterio.open(dem_path) as src:
            node_coords = []
            node_ids = []
            
            for n, data in G.nodes(data=True):
                # We assume nodes are in EPSG:4326 (lat/lon)
                lon, lat = data['x'], data['y']
                node_coords.append((lon, lat))
                node_ids.append(n)
                
            # Sample all points at once
            elevations = list(src.sample(node_coords))
            
            # Update graph
            for i, n in enumerate(node_ids):
                # elevations[i] is an array of band values, grab the first band
                val = float(elevations[i][0])
                if val < -1000: # Handle nodata values (often -32768)
                    val = 0.0
                G.nodes[n]['elevation'] = val
                
        print(f"  [gis] Applied DEM elevation to {len(node_ids)} nodes.")
                
    except Exception as e:
        print(f"  [gis/warning] Failed to fetch or apply DEM: {e}. Falling back to 0.0 elevation.")
        for n in G.nodes():
            if 'elevation' not in G.nodes[n]:
                G.nodes[n]['elevation'] = 0.0
                
    return G

def enrich_graph_roughness(G: nx.MultiDiGraph):
    """
    Assign a Manning's n roughness coefficient to each edge based on its OSM highway tag.
    Converts 'n' into a flow_efficiency multiplier (1.0 = baseline residential, >1.0 = faster, <1.0 = slower).
    """
    if not G.edges:
        return G
        
    MANNINGS_N = {
        'motorway': 0.013,
        'trunk': 0.014,
        'primary': 0.015,
        'secondary': 0.018,
        'tertiary': 0.020,
        'residential': 0.030, # baseline
        'living_street': 0.035,
        'pedestrian': 0.040,
        'path': 0.050,
        'footway': 0.050,
        'service': 0.060,
    }
    
    baseline_n = MANNINGS_N['residential']
    count = 0
    
    for u, v, k, data in G.edges(data=True, keys=True):
        hw = data.get('highway', 'residential')
        if isinstance(hw, list):
            hw = hw[0]
            
        n_val = MANNINGS_N.get(hw, baseline_n)
        # Flow efficiency is inversely proportional to roughness
        efficiency = round(baseline_n / max(n_val, 0.001), 3)
        G[u][v][k]['flow_efficiency'] = efficiency
        count += 1
        
    print(f"  [gis] Applied Manning's roughness to {count} edges.")
    return G

def get_gis_hydrology_nodes(G: nx.MultiDiGraph, center_lat: float, center_lon: float, radius_m: float = 2000):
    """
    Directly query Overpass API for rigorous drain/lake polygons and map them to G's nearest nodes.
    This bypasses osmnx's features wrapper which can sometimes miss waterway relations.
    Returns (drain_nodes, lake_nodes).
    """
    import osmnx as ox
    
    drain_nodes = []
    lake_nodes = []
    
    print(f"  [gis] Querying OpenStreetMap via Overpass for hydrology (radius {radius_m}m)...")
    
    # We will use OSMnx built-in features_from_point but heavily expand the tags to be sure we catch everything
    lake_tags = {
        "natural": ["water"],
        "water": ["lake", "reservoir", "pond"],
        "landuse": ["reservoir", "basin"]
    }
    drain_tags = {
        "waterway": ["drain", "canal", "ditch", "stream", "river"]
    }
    
    try:
        lakes_gdf = ox.features_from_point((center_lat, center_lon), tags=lake_tags, dist=radius_m)
        if not lakes_gdf.empty:
            for _, row in lakes_gdf.iterrows():
                geom = row.geometry
                pt = geom.centroid if geom.geom_type != "Point" else geom
                try:
                    node = ox.nearest_nodes(G, pt.x, pt.y)
                    lake_nodes.append(node)
                except Exception:
                    pass
    except Exception as e:
        print(f"  [gis/warning] Lake query failed: {e}")
        
    try:
        drains_gdf = ox.features_from_point((center_lat, center_lon), tags=drain_tags, dist=radius_m)
        if not drains_gdf.empty:
            for _, row in drains_gdf.iterrows():
                geom = row.geometry
                pt = geom.centroid if geom.geom_type != "Point" else geom
                try:
                    node = ox.nearest_nodes(G, pt.x, pt.y)
                    drain_nodes.append(node)
                except Exception:
                    pass
    except Exception as e:
        print(f"  [gis/warning] Drain query failed: {e}")
        
    drain_nodes = list(set(drain_nodes))
    lake_nodes = list(set(lake_nodes))
    
    print(f"  [gis] Extracted {len(drain_nodes)} drain nodes and {len(lake_nodes)} lake nodes.")
    return drain_nodes, lake_nodes

