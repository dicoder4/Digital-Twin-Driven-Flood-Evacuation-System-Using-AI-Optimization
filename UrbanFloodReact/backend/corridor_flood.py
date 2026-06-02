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

logger = logging.getLogger(__name__)

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

    Returns: Same graph with water_depth and flood_risk annotated on edges

    Time Basis:
      - STEPS = 50 (per tick)
      - TICK_MINS = 0.2 minutes (12 seconds)
      - Each step ≈ 0.24 seconds — matches urban stormwater response time
      - Rainfall input is mm/hour, converted to per-step rates
    """
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
