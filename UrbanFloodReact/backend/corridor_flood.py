"""
Instant flood physics on a corridor NetworkX graph.
Steady-state hydraulic depth estimation per edge.
Uses: rainfall_mm, elevation gradient, drain/lake node flags.
No full simulation — runs in < 50ms on corridor-scale graphs.
"""
import networkx as nx


def compute_flood(
    G: nx.DiGraph,
    rainfall_mm: dict,
    ward_for_node: dict,
) -> nx.DiGraph:
    """
    Annotates every edge (u→v) with:
      water_depth : float  (metres, capped at 3.0)
      flood_risk  : str    ("low" | "medium" | "high")
    Returns the same graph (mutated in place).
    """
    for u, v, data in G.edges(data=True):
        rain_u = rainfall_mm.get(ward_for_node.get(u, "unknown"), 0.0)
        rain_v = rainfall_mm.get(ward_for_node.get(v, "unknown"), 0.0)
        avg_rain = (rain_u + rain_v) / 2.0

        elev_u = G.nodes[u].get("elevation", 0.0)
        elev_v = G.nodes[v].get("elevation", 0.0)
        length = max(data["length"], 1.0)
        downhill_factor = 1.0 + max(0.0, elev_u - elev_v) / length

        lake_factor = 3.0 if G.nodes[u].get("is_lake") else 1.0
        drain_factor = 0.2 if G.nodes[v].get("is_drain") else 1.0

        depth = (avg_rain / 1000.0) * downhill_factor * lake_factor * drain_factor
        depth = round(min(depth, 3.0), 3)

        if depth < 0.1:
            risk = "low"
        elif depth < 0.5:
            risk = "medium"
        else:
            risk = "high"

        G[u][v]["water_depth"] = depth
        G[u][v]["flood_risk"] = risk

    return G
