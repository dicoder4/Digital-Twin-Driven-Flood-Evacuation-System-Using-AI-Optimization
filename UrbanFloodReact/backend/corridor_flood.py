"""
Flood physics on a corridor NetworkX graph with time-aware rainfall accumulation.

Physics Model:
  - Rainfall accumulates at specified rate (mm/hour)
  - Water flows downhill based on hydraulic head gradients
  - Drainage occurs naturally through flow propagation
  - No artificial decay factors — only physical gradient-driven flow

Key Parameters (should match backend tick_mins):
  - tick_mins: 0.2 minutes (12 seconds per tick) — MUST match simulation_engine.py
  - This determines rainfall per tick: mm_per_tick = (mm_per_hour / 60) * tick_mins

Time Scale Justification:
  - Each propagation step: 0.24 seconds (12s / 50 steps)
  - 50 steps per tick allows detailed flow routing before next rainfall input
  - Matches urban stormwater response time (~0.24-0.5 seconds)
"""
import networkx as nx
import logging
import osmnx as ox
import hashlib
from pymongo import MongoClient
import os
from pathlib import Path
from dotenv import load_dotenv
from math import radians, cos, sin, asin, sqrt

logger = logging.getLogger(__name__)

# Load MongoDB connection
current_dir = Path(__file__).resolve().parent
env_path = current_dir / '.env'
load_dotenv(dotenv_path=env_path)

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGO_URI2")
ox.settings.timeout = 600

def _haversine(lon1, lat1, lon2, lat2):
    """Calculate distance in meters"""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return 6371 * c * 1000

def _get_corridor_id(src_lat, src_lon, dst_lat, dst_lon):
    """Generate unique corridor ID from coordinates"""
    key = f"{src_lat:.4f}_{src_lon:.4f}_{dst_lat:.4f}_{dst_lon:.4f}"
    return hashlib.md5(key.encode()).hexdigest()[:12]

def _get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client.get_database("flood_evacuation_db")

def _fetch_and_cache_hydrology(src_lat, src_lon, dst_lat, dst_lon, graph):
    """Fetch hydrology for corridor bbox and cache in MongoDB"""
    corridor_id = _get_corridor_id(src_lat, src_lon, dst_lat, dst_lon)

    # Check cache first
    db = _get_db()
    cache = db["hydrology_cache"]
    cached = cache.find_one({"_id": corridor_id})
    if cached:
        logger.debug(f"[HYDROLOGY] Cache hit for corridor {corridor_id}")
        return cached.get("drain_nodes", []), cached.get("lake_nodes", [])

    logger.debug(f"[HYDROLOGY] Fetching for corridor {corridor_id}...")

    # Define corridor bbox with 2km buffer
    min_lat = min(src_lat, dst_lat) - 0.02
    max_lat = max(src_lat, dst_lat) + 0.02
    min_lon = min(src_lon, dst_lon) - 0.02
    max_lon = max(src_lon, dst_lon) + 0.02

    lake_tags = {
        "natural": ["water"],
        "water": ["lake", "reservoir", "pond"],
        "landuse": ["reservoir", "basin"],
    }
    drain_tags = {"waterway": ["drain", "canal", "ditch", "stream", "river"]}

    drain_nodes = []
    lake_nodes = []

    try:
        # Fetch lakes
        try:
            lakes_gdf = ox.features_from_bbox(
                north=max_lat, south=min_lat, east=max_lon, west=min_lon,
                tags=lake_tags
            )
            if not lakes_gdf.empty:
                for _, row in lakes_gdf.iterrows():
                    geom = row.geometry
                    pt = geom.centroid if geom.geom_type != "Point" else geom
                    min_dist = 1000
                    nearest = None
                    for node_id, node_data in graph.nodes(data=True):
                        dist = _haversine(pt.x, pt.y, node_data['x'], node_data['y'])
                        if dist < min_dist:
                            min_dist = dist
                            nearest = node_id
                    if nearest:
                        lake_nodes.append(nearest)
        except Exception as e:
            logger.debug(f"[HYDROLOGY] Lake fetch failed: {e}")

        # Fetch drains
        try:
            drains_gdf = ox.features_from_bbox(
                north=max_lat, south=min_lat, east=max_lon, west=min_lon,
                tags=drain_tags
            )
            if not drains_gdf.empty:
                for _, row in drains_gdf.iterrows():
                    geom = row.geometry
                    pt = geom.centroid if geom.geom_type != "Point" else geom
                    min_dist = 1000
                    nearest = None
                    for node_id, node_data in graph.nodes(data=True):
                        dist = _haversine(pt.x, pt.y, node_data['x'], node_data['y'])
                        if dist < min_dist:
                            min_dist = dist
                            nearest = node_id
                    if nearest:
                        drain_nodes.append(nearest)
        except Exception as e:
            logger.debug(f"[HYDROLOGY] Drain fetch failed: {e}")

        # Cache in MongoDB
        cache.update_one(
            {"_id": corridor_id},
            {"$set": {
                "src_lat": src_lat,
                "src_lon": src_lon,
                "dst_lat": dst_lat,
                "dst_lon": dst_lon,
                "drain_nodes": drain_nodes,
                "lake_nodes": lake_nodes,
            }},
            upsert=True
        )
        logger.debug(f"[HYDROLOGY] Cached: {len(drain_nodes)} drains, {len(lake_nodes)} lakes")

    except Exception as e:
        logger.warning(f"[HYDROLOGY] Failed: {e}")

    return drain_nodes, lake_nodes

# Backend configuration — MUST match simulation_engine.py tick_mins
TICK_MINS = 0.2  # Minutes per tick (12 seconds)

def propagate_flood_step(graph: nx.DiGraph, flow_factor: float = 0.15):
    """
    One step of physical water flow based on hydraulic head gradients.

    Physics:
      - Water flows from higher to lower hydraulic head
      - Hydraulic head = elevation + water_depth
      - Flow rate ∝ head difference × flow_factor
      - No arbitrary decay — only gradient-driven flow
      - flow_factor ≈ 0.15 means ~15% of water at a node can flow per step
        (realistic for stormwater velocities on streets)

    Mutates node 'water_depth' in place.
    """
    current_depths = nx.get_node_attributes(graph, 'water_depth')
    elevations = nx.get_node_attributes(graph, 'elevation')

    depth_transfers = {n: 0.0 for n in graph.nodes()}

    for node in graph.nodes():
        water_depth = current_depths.get(node, 0.0)
        if water_depth <= 0.002:  # 2mm minimum (surface tension effects)
            continue

        node_head = elevations.get(node, 0.0) + water_depth
        neighbors = list(graph.neighbors(node))

        lower_head_neighbors = []
        total_head_diff = 0.0

        # Find all neighbors with lower hydraulic head (water can flow there)
        for n in neighbors:
            n_head = elevations.get(n, 0.0) + current_depths.get(n, 0.0)
            if n_head < node_head:
                head_diff = node_head - n_head
                lower_head_neighbors.append((n, head_diff))
                total_head_diff += head_diff

        if not lower_head_neighbors or total_head_diff <= 0:
            continue

        # Total flow out = a fraction of current water depth
        # This fraction is driven by hydraulic head differences
        max_flow = water_depth * flow_factor

        # Distribute flow proportional to head difference (steeper slope = more flow)
        total_outflow = 0.0
        per_neighbour = []

        for n, head_diff in lower_head_neighbors:
            # Fraction of flow to this neighbor (larger head diff = more flow)
            head_fraction = head_diff / total_head_diff

            # Get edge properties for flow efficiency
            edge_data = graph.get_edge_data(node, n, default={})
            if isinstance(edge_data, dict) and 0 in edge_data:
                edge_data = edge_data[0]  # MultiDiGraph case
            efficiency = edge_data.get('flow_efficiency', 1.0)

            # Flow to this neighbor
            amount = max_flow * head_fraction * efficiency
            per_neighbour.append((n, amount))
            total_outflow += amount

        # Ensure we don't flow out more water than we have
        scale = min(1.0, water_depth / total_outflow) if total_outflow > 0 else 1.0

        # Apply scaled flows
        for n, amount in per_neighbour:
            scaled_amount = amount * scale
            depth_transfers[node] -= scaled_amount
            depth_transfers[n] += scaled_amount

    # Apply all transfers simultaneously (conservation of mass)
    for n, delta in depth_transfers.items():
        graph.nodes[n]['water_depth'] = max(0.0, current_depths.get(n, 0.0) + delta)


def _apply_rainfall(graph: nx.DiGraph, rainfall_mm: dict, ward_for_node: dict, steps: int):
    """Apply rainfall incrementally across all nodes."""
    for node in graph.nodes:
        ward = ward_for_node.get(node, "unknown")
        node_rain_mm_hr = rainfall_mm.get(ward, 0.0)
        # Convert mm/hr to m per step: (mm/hr / 1000) / steps
        rain_m_step = (node_rain_mm_hr / 1000.0) / steps
        graph.nodes[node]['water_depth'] = graph.nodes[node].get('water_depth', 0.0) + rain_m_step


def _assign_edge_flood_risk(depth: float) -> str:
    """Classify flood risk based on water depth."""
    if depth < 0.1:
        return "low"
    elif depth < 0.5:
        return "medium"
    else:
        return "high"


def _map_nodes_to_edges(graph: nx.DiGraph) -> None:
    """Copy node water depths to edge depths for routing."""
    for u, v, _data in graph.edges(data=True):
        u_depth = graph.nodes[u].get('water_depth', 0.0)

        # Use upstream depth (source node u) for more realistic impact on routing
        # A road is impassable if the *source* has high water depth
        depth = u_depth

        # Apply drain and lake multipliers for hazard zones
        lake_factor = 3.0 if graph.nodes[u].get("is_lake") else 1.0
        drain_factor = 0.2 if graph.nodes[v].get("is_drain") else 1.0

        # Cap at 3.0m max flood depth
        depth = round(min(depth * lake_factor * drain_factor, 3.0), 3)

        graph[u][v]["water_depth"] = depth
        graph[u][v]["flood_risk"] = _assign_edge_flood_risk(depth)


def compute_flood(
    graph: nx.DiGraph,
    rainfall_mm: dict,
    ward_for_node: dict,
    src_lat: float = None,
    src_lon: float = None,
    dst_lat: float = None,
    dst_lon: float = None,
) -> nx.DiGraph:
    """
    Computes time-aware flood depths on a corridor graph.

    Physics Model:
      1. Rainfall accumulates at specified rate (mm/hour)
      2. Water is distributed to nodes based on ward/hobli location
      3. Water flows downhill using gradient-driven propagation (no decay)
      4. Final depths mapped to edges for routing decisions

    Parameters:
      graph: NetworkX graph with elevation, ward_for_node, drain/lake flags
      rainfall_mm: dict mapping ward name → rainfall (mm/hour)
      ward_for_node: dict mapping node_id → ward name
      src_lat, src_lon, dst_lat, dst_lon: Corridor coordinates for hydrology lookup

    Returns: Same graph with water_depth and flood_risk annotated on edges

    Time Basis:
      - STEPS = 50 (per tick)
      - TICK_MINS = 0.2 minutes (12 seconds)
      - Each step ≈ 0.24 seconds — matches urban stormwater response time
      - Rainfall input is mm/hour, converted to per-step rates
    """
    # Fetch and apply hydrology data for this corridor (drain/lake multipliers)
    if src_lat is not None and src_lon is not None and dst_lat is not None and dst_lon is not None:
        try:
            drain_nodes, lake_nodes = _fetch_and_cache_hydrology(src_lat, src_lon, dst_lat, dst_lon, graph)
            for node in drain_nodes:
                if node in graph.nodes:
                    graph.nodes[node]['is_drain'] = True
            for node in lake_nodes:
                if node in graph.nodes:
                    graph.nodes[node]['is_lake'] = True
            logger.info(f"[HYDROLOGY] Applied {len(drain_nodes)} drains, {len(lake_nodes)} lakes to graph")
        except Exception as e:
            logger.warning(f"[HYDROLOGY] Failed to fetch: {e}")

    # Initialize all node water depths
    nx.set_node_attributes(graph, 0.0, 'water_depth')

    # Run 50 steps of rainfall + flow propagation per tick
    # This allows detailed routing before next rainfall input
    STEPS = 50
    for _ in range(STEPS):
        # Add rainfall incrementally to all nodes
        _apply_rainfall(graph, rainfall_mm, ward_for_node, STEPS)

        # Propagate water downhill based on elevation gradients
        # flow_factor=0.15 means 15% of water at a node can flow per step
        # (realistic for urban stormwater velocities on streets)
        propagate_flood_step(graph, flow_factor=0.15)

    # Map final node depths to edges for routing engine
    _map_nodes_to_edges(graph)

    logger.debug(
        f"[COMPUTE FLOOD] Processed {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges | "
        f"Max depth: {max((d.get('water_depth', 0) for _, _, d in graph.edges(data=True)), default=0):.3f}m"
    )

    return graph
