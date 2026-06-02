"""
A* routing on flood-weighted corridor graph.
Cost function: travel time (minutes) + flood penalty.
Turn-by-turn instruction generator using bearing + highway type.
"""
import networkx as nx
import math


def astar_route(G: nx.DiGraph, src: int, dst: int, impassable_depth: float = 0.25, strict: bool = True) -> list[int] | None:
    """
    Returns ordered list of node IDs from src to dst,
    or None if no passable path exists.
    Cost includes travel time (accounting for live traffic) + flood penalty.

    Uses live_speed_kmh if available on edges (from traffic data), falls back to speed_kph.
    """
    def cost(u, v, data):
        depth = data.get("water_depth", 0.0)
        # Prefer live traffic speed if available, otherwise use base speed
        speed_kmh = data.get("live_speed_kmh", data.get("speed_kph", 40))
        travel_min = (data["length"] / 1000.0) / speed_kmh * 60.0

        if depth >= impassable_depth:
            if strict:
                return float("inf")
            # If not strict, apply massive penalty but allow passage as last resort
            flood_penalty = 10000.0 + (depth * 1000.0)
        else:
            # Flood penalty: prefer less flooded routes
            flood_penalty = (depth ** 2) * 5.0

        return travel_min + flood_penalty

    def heuristic(u, v):
        nu, nv = G.nodes[u], G.nodes[v]
        dlat = nu["lat"] - nv["lat"]
        dlon = nu["lon"] - nv["lon"]
        dist_km = math.sqrt(dlat**2 + dlon**2) * 111.0
        # Use walking speed (5 km/h) for conservative heuristic in flood scenarios
        return (dist_km / 5.0) * 60.0

    try:
        return nx.astar_path(G, src, dst, heuristic=heuristic, weight=cost)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def build_route_geojson(G: nx.DiGraph, path: list[int]) -> dict:
    """
    Builds a GeoJSON FeatureCollection where each feature is one
    road segment with flood_risk and water_depth as properties.
    """
    features = []
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        data = G[u][v]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": data.get("geometry", [
                    [G.nodes[u]["lon"], G.nodes[u]["lat"]],
                    [G.nodes[v]["lon"], G.nodes[v]["lat"]],
                ])
            },
            "properties": {
                "flood_risk": data.get("flood_risk", "low"),
                "water_depth": data.get("water_depth", 0.0),
                "highway": data.get("highway", ""),
                "length_m": round(data["length"]),
            }
        })
    return {"type": "FeatureCollection", "features": features}


def generate_steps(G: nx.DiGraph, path: list[int], street_names: dict = None) -> list[dict]:
    """
    Turn-by-turn instructions derived from bearing + street name (if available).

    Args:
        G: NetworkX DiGraph with edge data (with 'name' attribute for street names)
        path: List of node IDs
        street_names: Optional dict mapping (u, v, k) to street name (for backward compatibility)
    """
    if street_names is None:
        street_names = {}

    import logging
    logger = logging.getLogger(__name__)

    # Debug: count how many edges have names
    edges_with_names = sum(1 for u, v, data in G.edges(data=True) if data.get("name"))
    edges_total = G.number_of_edges()
    logger.info(f"[STEPS] Graph has {edges_with_names}/{edges_total} edges with names ({100*edges_with_names/edges_total:.1f}%)")

    steps = []
    prev_road_name = None

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        data = G[u][v]
        bearing = _bearing(G.nodes[u], G.nodes[v])
        prev_bearing = _bearing(G.nodes[path[i - 1]], G.nodes[u]) if i > 0 else bearing
        turn = _turn_instruction(prev_bearing, bearing)

        # Try to get street name from edge data (priority: name > prev name > highway type)
        road_label = None

        # First check edge 'name' attribute (from MongoDB)
        if data.get("name"):
            road_label = data["name"]
            prev_road_name = road_label
        # If no name, try to use previous road name (street might continue)
        elif prev_road_name:
            road_label = prev_road_name
        # Fallback to highway type formatted nicely
        else:
            highway = data.get("highway", "road")
            # Map highway types to readable names
            highway_names = {
                "motorway": "Motorway",
                "trunk": "Trunk Road",
                "primary": "Primary Road",
                "secondary": "Secondary Road",
                "tertiary": "Tertiary Road",
                "residential": "Residential Road",
                "service": "Service Road",
                "unclassified": "Unclassified Road",
                "path": "Path",
                "footway": "Footway",
            }
            road_label = highway_names.get(highway, highway.replace("_", " ").title())

        steps.append({
            "instruction": f"{turn} on {road_label}",
            "distance_m": round(data["length"]),
            "flood_risk": data.get("flood_risk", "low"),
            "flood_depth_m": data.get("water_depth", 0.0),
        })
    return _merge_steps(steps)


def route_summary(G: nx.DiGraph, path: list[int], impassable_depth: float = 0.25) -> dict:
    """Computes total distance, time (accounting for live traffic), and max flood depth for route."""
    total_dist = sum(G[path[i]][path[i + 1]]["length"] for i in range(len(path) - 1))
    total_time = sum(
        (G[path[i]][path[i + 1]]["length"] / 1000) / (G[path[i]][path[i + 1]].get("live_speed_kmh", G[path[i]][path[i + 1]].get("speed_kph", 40))) * 60
        for i in range(len(path) - 1)
    )
    max_depth = max(
        (G[path[i]][path[i + 1]].get("water_depth", 0) for i in range(len(path) - 1)),
        default=0.0
    )
    flooded_segments = sum(
        1 for i in range(len(path) - 1)
        if G[path[i]][path[i + 1]].get("water_depth", 0) > 0.1
    )
    return {
        "total_distance_m": round(total_dist),
        "eta_minutes": round(total_time),
        "max_flood_depth_m": round(max_depth, 2),
        "flooded_segments": flooded_segments,
        "safe": max_depth < impassable_depth,
    }


def _bearing(n1: dict, n2: dict) -> float:
    """Computes compass bearing from n1 to n2 in degrees (0-360)."""
    dlon = math.radians(n2["lon"] - n1["lon"])
    lat1 = math.radians(n1["lat"])
    lat2 = math.radians(n2["lat"])
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _turn_instruction(prev_b: float, curr_b: float) -> str:
    """Converts bearing change to turn instruction."""
    delta = (curr_b - prev_b + 360) % 360
    if delta < 20 or delta > 340:
        return "Continue"
    elif delta < 70:
        return "Bear right"
    elif delta < 110:
        return "Turn right"
    elif delta < 170:
        return "Sharp right"
    elif delta < 190:
        return "U-turn"
    elif delta < 250:
        return "Sharp left"
    elif delta < 290:
        return "Turn left"
    else:
        return "Bear left"


def _merge_steps(steps: list) -> list:
    """Merges consecutive steps on same direction."""
    if not steps:
        return []
    merged = [dict(steps[0])]
    for s in steps[1:]:
        if s["instruction"] == merged[-1]["instruction"]:
            merged[-1]["distance_m"] += s["distance_m"]
            merged[-1]["flood_depth_m"] = max(merged[-1]["flood_depth_m"], s["flood_depth_m"])
            if s["flood_risk"] in ("high", "medium") and merged[-1]["flood_risk"] == "low":
                merged[-1]["flood_risk"] = s["flood_risk"]
        else:
            merged.append(dict(s))
    return merged
