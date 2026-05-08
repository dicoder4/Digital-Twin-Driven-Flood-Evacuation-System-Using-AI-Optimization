import os
import tempfile
import requests
import rasterio
import numpy as np
import networkx as nx

import db


def _get_dem_bytes(min_lon: float, min_lat: float, max_lon: float, max_lat: float, dem_key: str) -> bytes:
    """
    Return raw GeoTIFF bytes for the given bounding box.
    Checks MongoDB first; downloads from OpenTopography on cache miss and stores result.
    """
    cached = db.get_dem_cache(dem_key)
    if cached is not None:
        print(f"  [gis] DEM cache hit from MongoDB for '{dem_key}'")
        return cached

    url = (
        f"https://portal.opentopography.org/API/globaldem"
        f"?demtype=SRTMGL3&south={min_lat}&north={max_lat}"
        f"&west={min_lon}&east={max_lon}&outputFormat=GTiff"
    )
    api_key = os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if api_key:
        url += f"&API_Key={api_key}"

    print("  [gis] Downloading DEM from OpenTopography (this may take 5-10s)...")
    r = requests.get(url, timeout=60)

    if r.status_code in (401, 403):
        raise RuntimeError(
            "OpenTopography API authentication required or rate limit reached. "
            "Get a free key at portal.opentopography.org and set OPENTOPOGRAPHY_API_KEY."
        )
    r.raise_for_status()

    tif_bytes = r.content
    db.set_dem_cache(dem_key, tif_bytes)
    return tif_bytes


def enrich_graph_elevation(G: nx.MultiDiGraph, center_lat: float, center_lon: float, radius_m: float = 2000):
    """
    Downloads SRTM DEM for the graph's bounding box and samples elevation for every node.
    Adds an 'elevation' attribute to each node in the graph.
    DEM bytes are cached in MongoDB so subsequent calls (any device) skip the download.
    """
    if not G.nodes:
        return G

    buffer_deg = (radius_m / 111000.0) * 1.5
    min_lon = center_lon - buffer_deg
    max_lon = center_lon + buffer_deg
    min_lat = center_lat - buffer_deg
    max_lat = center_lat + buffer_deg

    dem_key = f"dem_{center_lat:.3f}_{center_lon:.3f}"

    try:
        tif_bytes = _get_dem_bytes(min_lon, min_lat, max_lon, max_lat, dem_key)

        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
            tmp.write(tif_bytes)
            tmp_path = tmp.name

        try:
            with rasterio.open(tmp_path) as src:
                node_coords = []
                node_ids = []
                for n, data in G.nodes(data=True):
                    node_coords.append((data["x"], data["y"]))
                    node_ids.append(n)

                elevations = list(src.sample(node_coords))
                for i, n in enumerate(node_ids):
                    val = float(elevations[i][0])
                    if val < -1000:
                        val = 0.0
                    G.nodes[n]["elevation"] = val
        finally:
            os.unlink(tmp_path)

        print(f"  [gis] Applied DEM elevation to {len(node_ids)} nodes.")

    except Exception as e:
        print(f"  [gis/warning] Failed to fetch or apply DEM: {e}. Falling back to 0.0 elevation.")
        for n in G.nodes():
            if "elevation" not in G.nodes[n]:
                G.nodes[n]["elevation"] = 0.0

    return G


def enrich_graph_roughness(G: nx.MultiDiGraph):
    """
    Assign a Manning's n roughness coefficient to each edge based on its OSM highway tag.
    Converts 'n' into a flow_efficiency multiplier (1.0 = baseline residential).
    """
    if not G.edges:
        return G

    MANNINGS_N = {
        "motorway": 0.013,
        "trunk": 0.014,
        "primary": 0.015,
        "secondary": 0.018,
        "tertiary": 0.020,
        "residential": 0.030,
        "living_street": 0.035,
        "pedestrian": 0.040,
        "path": 0.050,
        "footway": 0.050,
        "service": 0.060,
    }

    baseline_n = MANNINGS_N["residential"]
    count = 0

    for u, v, k, data in G.edges(data=True, keys=True):
        hw = data.get("highway", "residential")
        if isinstance(hw, list):
            hw = hw[0]
        n_val = MANNINGS_N.get(hw, baseline_n)
        G[u][v][k]["flow_efficiency"] = round(baseline_n / max(n_val, 0.001), 3)
        count += 1

    print(f"  [gis] Applied Manning's roughness to {count} edges.")
    return G


def get_gis_hydrology_nodes(G: nx.MultiDiGraph, center_lat: float, center_lon: float, radius_m: float = 2000):
    """
    Query OpenStreetMap via Overpass for drain/lake polygons and map them to G's nearest nodes.
    Returns (drain_nodes, lake_nodes).
    """
    import osmnx as ox

    drain_nodes = []
    lake_nodes = []

    print(f"  [gis] Querying OpenStreetMap via Overpass for hydrology (radius {radius_m}m)...")

    lake_tags = {
        "natural": ["water"],
        "water": ["lake", "reservoir", "pond"],
        "landuse": ["reservoir", "basin"],
    }
    drain_tags = {"waterway": ["drain", "canal", "ditch", "stream", "river"]}

    try:
        lakes_gdf = ox.features_from_point((center_lat, center_lon), tags=lake_tags, dist=radius_m)
        if not lakes_gdf.empty:
            for _, row in lakes_gdf.iterrows():
                geom = row.geometry
                pt = geom.centroid if geom.geom_type != "Point" else geom
                try:
                    lake_nodes.append(ox.nearest_nodes(G, pt.x, pt.y))
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
                    drain_nodes.append(ox.nearest_nodes(G, pt.x, pt.y))
                except Exception:
                    pass
    except Exception as e:
        print(f"  [gis/warning] Drain query failed: {e}")

    drain_nodes = list(set(drain_nodes))
    lake_nodes = list(set(lake_nodes))

    print(f"  [gis] Extracted {len(drain_nodes)} drain nodes and {len(lake_nodes)} lake nodes.")
    return drain_nodes, lake_nodes
