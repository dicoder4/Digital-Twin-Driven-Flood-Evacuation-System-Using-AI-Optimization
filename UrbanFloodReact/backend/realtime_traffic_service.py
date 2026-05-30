"""
Real-time traffic integration for live citizen navigation.
Fetches live TomTom traffic data for the citizen's route and updates ETA dynamically.
"""
import asyncio
import time
import os
import logging
from typing import List, Dict, Tuple, Optional
import httpx
import networkx as nx

logger = logging.getLogger(__name__)

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")
TOMTOM_FLOW_API_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
TRAFFIC_CACHE_TTL = 60  # Cache for 60 seconds to avoid hammering API


_traffic_cache = {}
_cache_timestamps = {}


async def fetch_live_traffic_for_segment(coord: Tuple[float, float]) -> Optional[Dict]:
    """
    Fetches real-time traffic flow data for a single coordinate from TomTom.

    Args:
        coord: (lat, lon) tuple

    Returns:
        Dict with current_speed, free_flow_speed, current_time, free_flow_time
        or None if fetch fails
    """
    if not TOMTOM_API_KEY:
        logger.warning("TomTom API key not configured for real-time traffic")
        return None

    lat, lon = coord
    cache_key = f"{lat:.4f},{lon:.4f}"

    # Check cache
    if cache_key in _traffic_cache:
        if time.time() - _cache_timestamps.get(cache_key, 0) < TRAFFIC_CACHE_TTL:
            return _traffic_cache[cache_key]

    params = {
        "point": f"{lat},{lon}",
        "unit": "KMPH",
        "thickness": 10,
        "openLr": "false",
        "key": TOMTOM_API_KEY
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(TOMTOM_FLOW_API_URL, params=params)

            if response.status_code == 200:
                data = response.json()
                flow_data = data.get("flowSegmentData", {})

                current_speed = flow_data.get("currentSpeed")
                free_flow_speed = flow_data.get("freeFlowSpeed")
                current_time = flow_data.get("currentTravelTime")
                free_flow_time = flow_data.get("freeFlowTravelTime")

                if current_time and free_flow_time:
                    result = {
                        "current_speed": current_speed,
                        "free_flow_speed": free_flow_speed,
                        "current_time": current_time,
                        "free_flow_time": free_flow_time,
                        "lat": lat,
                        "lon": lon,
                        "congestion_ratio": current_time / free_flow_time if free_flow_time > 0 else 1.0
                    }
                    # Cache it
                    _traffic_cache[cache_key] = result
                    _cache_timestamps[cache_key] = time.time()
                    return result
            elif response.status_code == 403:
                logger.error(f"TomTom API forbidden - check API key")
            elif response.status_code == 429:
                logger.warning(f"TomTom API rate limited")

    except asyncio.TimeoutError:
        logger.warning(f"TomTom traffic fetch timeout for {lat},{lon}")
    except Exception as e:
        logger.debug(f"TomTom traffic fetch error for {lat},{lon}: {e}")

    return None


async def get_route_traffic_eta(
    G: nx.DiGraph,
    path: List[int],
    speed_mode: str = "car"
) -> Dict:
    """
    Calculates ETA considering real-time traffic for a given route.

    Args:
        G: NetworkX graph with lat/lon in nodes
        path: List of node IDs representing the route
        speed_mode: 'car', 'bike', or 'walk'

    Returns:
        Dict with:
        - eta_minutes: Estimated time with traffic
        - distance_m: Total route distance
        - segments: List of segment data with traffic info
        - avg_speed_kmh: Weighted average speed
    """
    SPEED_MAP = {
        "car": 40,
        "bike": 30,
        "walk": 4,
    }
    base_speed = SPEED_MAP.get(speed_mode, 40)

    # For walk/bike, don't fetch traffic (not affected by car traffic)
    if speed_mode in ["walk", "bike"]:
        total_dist = 0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = G[u][v]
            length = edge_data.get("length", 0)
            total_dist += length
        eta_min = (total_dist / 1000) / base_speed * 60
        return {
            "eta_minutes": int(eta_min),
            "distance_m": total_dist,
            "segments": [],
            "avg_speed_kmh": base_speed,
            "mode": speed_mode,
            "has_traffic": False
        }

    # For cars, fetch live traffic
    segments = []
    total_distance = 0
    total_travel_time = 0

    # Get midpoints of segments for traffic queries
    segment_coords = []
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        node_u = G.nodes[u]
        node_v = G.nodes[v]
        mid_lat = (node_u["lat"] + node_v["lat"]) / 2
        mid_lon = (node_u["lon"] + node_v["lon"]) / 2
        segment_coords.append((mid_lat, mid_lon, u, v))

    # Fetch traffic data concurrently
    traffic_tasks = [fetch_live_traffic_for_segment(coord[:2]) for coord in segment_coords]
    traffic_results = await asyncio.gather(*traffic_tasks)

    # Process results
    for i, (coord_lat, coord_lon, u, v) in enumerate(segment_coords):
        edge_data = G[u][v]
        segment_len = edge_data.get("length", 0)
        total_distance += segment_len

        traffic_data = traffic_results[i]

        if traffic_data:
            # Use live traffic speed to calculate travel time for this segment
            current_speed = traffic_data.get("current_speed", base_speed)
            # Calculate travel time from speed and distance (not from TomTom's per-point time)
            travel_time = (segment_len / 1000) / current_speed * 3600 if current_speed > 0 else 0  # seconds
            segments.append({
                "u": u,
                "v": v,
                "length_m": segment_len,
                "current_speed_kmh": current_speed,
                "free_flow_speed_kmh": traffic_data.get("free_flow_speed", base_speed),
                "travel_time_sec": travel_time,
                "congestion_ratio": traffic_data.get("congestion_ratio", 1.0)
            })
            total_travel_time += travel_time
        else:
            # Fallback to base speed if traffic fetch fails
            travel_time = (segment_len / 1000) / base_speed * 3600  # seconds
            segments.append({
                "u": u,
                "v": v,
                "length_m": segment_len,
                "current_speed_kmh": base_speed,
                "free_flow_speed_kmh": base_speed,
                "travel_time_sec": travel_time,
                "congestion_ratio": 1.0
            })
            total_travel_time += travel_time

    # Convert seconds to minutes
    eta_minutes = int(total_travel_time / 60)
    avg_speed = (total_distance / 1000) / (total_travel_time / 3600) if total_travel_time > 0 else base_speed

    return {
        "eta_minutes": eta_minutes,
        "distance_m": total_distance,
        "segments": segments,
        "avg_speed_kmh": round(avg_speed, 1),
        "mode": speed_mode,
        "has_traffic": len(segments) > 0
    }


async def embed_live_traffic_in_path(G: nx.DiGraph, path: List[int]) -> int:
    """
    Fetches live traffic ONLY for edges in the given path (not entire graph).
    Much faster than fetching for all edges - typical route is 100-200 edges,
    corridor has 10,000+ edges.

    Args:
        G: NetworkX DiGraph with road segments
        path: List of node IDs representing the route

    Returns:
        Number of edges successfully updated with traffic data
    """
    segment_coords = []
    edge_map = {}

    # Collect midpoints ONLY for edges in the path
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        node_u = G.nodes[u]
        node_v = G.nodes[v]
        mid_lat = (node_u["lat"] + node_v["lat"]) / 2
        mid_lon = (node_u["lon"] + node_v["lon"]) / 2
        segment_coords.append((mid_lat, mid_lon))
        edge_map[len(segment_coords) - 1] = (u, v)

    if not segment_coords:
        logger.warning("No edges found in path for traffic embedding")
        return 0

    logger.info(f"Fetching live traffic for {len(segment_coords)} edges in path (vs corridor size)...")

    # Fetch traffic data concurrently
    traffic_tasks = [fetch_live_traffic_for_segment(coord) for coord in segment_coords]
    traffic_results = await asyncio.gather(*traffic_tasks)

    # Embed into graph
    updated_count = 0
    for idx, traffic_data in enumerate(traffic_results):
        if traffic_data is None:
            continue

        u, v = edge_map[idx]
        current_speed = traffic_data.get("current_speed")
        if current_speed and current_speed > 0:
            G[u][v]["live_speed_kmh"] = current_speed
            updated_count += 1

    logger.info(f"Traffic embedded into {updated_count} edges in path")
    return updated_count


def clear_traffic_cache():
    """Clear all cached traffic data."""
    global _traffic_cache, _cache_timestamps
    _traffic_cache.clear()
    _cache_timestamps.clear()
    logger.info("Traffic cache cleared")
