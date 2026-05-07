"""
Builds a NetworkX DiGraph from MongoDB edge/node documents.
Adds derived fields (speed_kph) that are not stored in MongoDB.
"""
import networkx as nx


HIGHWAY_SPEED_KPH = {
    "motorway": 100, "trunk": 80, "primary": 60,
    "secondary": 50, "tertiary": 40, "residential": 30,
    "service": 20, "unclassified": 25, "path": 10,
    "footway": 5,
}


def _edge_speed(edge: dict) -> float:
    """Derives speed for an edge from maxspeed or highway type."""
    if edge.get("maxspeed"):
        try:
            return float(edge["maxspeed"])
        except (ValueError, TypeError):
            pass
    return HIGHWAY_SPEED_KPH.get(edge.get("highway", ""), 30.0)


def build_graph(edges: list, nodes: list) -> nx.DiGraph:
    """
    Constructs corridor DiGraph from MongoDB edge/node lists.
    Nodes keyed by OSM integer ID.
    Edges annotated with: length, speed_kph, highway, flow_efficiency,
                          water_depth (0.0 init), flood_risk ('low' init),
                          geometry (coordinate list).
    """
    G = nx.DiGraph()

    node_set = {n["_id"] for n in nodes}

    for n in nodes:
        G.add_node(
            n["_id"],
            lon=n["x"],
            lat=n["y"],
            elevation=float(n.get("elevation", 0)),
            is_drain=bool(n.get("is_drain", False)),
            is_lake=bool(n.get("is_lake", False)),
        )

    for e in edges:
        if e["u"] not in node_set or e["v"] not in node_set:
            continue

        length = float(e["length"])
        speed_kph = _edge_speed(e)
        # Weight = length / speed (time to traverse, in minutes)
        weight = (length / 1000.0) / speed_kph * 60.0 if speed_kph > 0 else float('inf')

        G.add_edge(
            e["u"], e["v"],
            length=length,
            speed_kph=speed_kph,
            weight=weight,
            highway=e.get("highway", "residential"),
            flow_efficiency=float(e.get("flow_efficiency", 1.0)),
            water_depth=0.0,
            flood_risk="low",
            geometry=e["location"]["coordinates"],
        )

    return G


def snap_to_node(G: nx.DiGraph, lat: float, lon: float) -> int | None:
    """
    Finds nearest graph node to a GPS coordinate using haversine distance.
    Returns OSM node ID or None if graph is empty.
    """
    from math import radians, cos, sin, sqrt, atan2

    def haversine(n):
        nd = G.nodes[n]
        dlat = radians(lat - nd["lat"])
        dlon = radians(lon - nd["lon"])
        a = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(nd["lat"])) * sin(dlon / 2) ** 2
        return 6371000 * 2 * atan2(sqrt(a), sqrt(1 - a))

    if G is None or len(G.nodes) == 0:
        return None
    return min(G.nodes, key=haversine)
