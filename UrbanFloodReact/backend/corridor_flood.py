"""
Instant flood physics on a corridor NetworkX graph.
Steady-state hydraulic depth estimation per edge.
Uses: rainfall_mm, elevation gradient, drain/lake node flags.
No full simulation — runs in < 50ms on corridor-scale graphs.
"""
import networkx as nx

def propagate_flood_step(G: nx.DiGraph, decay_factor: float = 0.5):
    """
    Performs one step of physical water flow across the graph based on hydraulic head.
    Mutates node 'water_depth' in place.
    """
    current_depths = nx.get_node_attributes(G, 'water_depth')
    elevations = nx.get_node_attributes(G, 'elevation')
    
    depth_transfers = {n: 0.0 for n in G.nodes()}
    
    for node in G.nodes():
        water_depth = current_depths.get(node, 0.0)
        if water_depth <= 0.005:  # 5mm surface retention
            continue
            
        node_head = elevations.get(node, 0.0) + water_depth
        neighbors = list(G.neighbors(node))
        
        lower_head_neighbors = []
        total_head_diff = 0.0
        
        for n in neighbors:
            n_head = elevations.get(n, 0.0) + current_depths.get(n, 0.0)
            if n_head < node_head:
                head_diff = node_head - n_head
                lower_head_neighbors.append((n, head_diff))
                total_head_diff += head_diff
                
        if not lower_head_neighbors:
            continue
            
        flow_out = water_depth * decay_factor
        total_outflow = 0.0
        per_neighbour = []
        
        for n, diff in lower_head_neighbors:
            fraction = diff / total_head_diff
            n_elev = elevations.get(n, 0.0)
            node_elev = elevations.get(node, 0.0)
            slope_factor = 1.0 + min(abs(node_elev - n_elev) / 10.0, 2.0)
            
            # Get flow efficiency
            edge_data = G.get_edge_data(node, n, default={})
            if isinstance(edge_data, dict) and 0 in edge_data:
                edge_data = edge_data[0] # MultiDiGraph case
            efficiency = edge_data.get('flow_efficiency', 1.0)
            
            amount = flow_out * fraction * slope_factor * efficiency
            per_neighbour.append((n, amount))
            total_outflow += amount
            
        # Ensure we don't flow out more than we have
        scale = min(1.0, water_depth / total_outflow) if total_outflow > 0 else 1.0
        
        for n, amount in per_neighbour:
            scaled_amount = amount * scale
            depth_transfers[node] -= scaled_amount
            depth_transfers[n] += scaled_amount
            
    # Apply transfers
    for n, delta in depth_transfers.items():
        G.nodes[n]['water_depth'] = max(0.0, current_depths.get(n, 0.0) + delta)


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
    # 1. Initialize node water depths
    nx.set_node_attributes(G, 0.0, 'water_depth')

    # 2. Run progressive loop for 50 steps
    STEPS = 50
    for step in range(STEPS):
        # Apply node-specific incremental rainfall
        for node in G.nodes:
            ward = ward_for_node.get(node, "unknown")
            node_rain_mm_hr = rainfall_mm.get(ward, 0.0)
            
            # Rainfall to add in this step (convert mm to m, divide by steps)
            rain_m_step = (node_rain_mm_hr / 1000.0) / STEPS
            
            G.nodes[node]['water_depth'] = G.nodes[node].get('water_depth', 0.0) + rain_m_step
            
        # Propagate flow based on hydraulic head gradients
        propagate_flood_step(G, decay_factor=0.5)

    # 3. Map final node depths back to edge depths for the routing engine
    for u, v, data in G.edges(data=True):
        u_depth = G.nodes[u].get('water_depth', 0.0)
        v_depth = G.nodes[v].get('water_depth', 0.0)
        
        # Average depth across the edge, capped at 3.0m
        avg_depth = (u_depth + v_depth) / 2.0
        
        # Apply drain and lake multipliers just to the *edge visualization/risk* 
        # to ensure extreme hazards are still flagged if propagation is slow
        lake_factor = 3.0 if G.nodes[u].get("is_lake") else 1.0
        drain_factor = 0.2 if G.nodes[v].get("is_drain") else 1.0
        
        # Note: the actual physical propagation already happened above, 
        # these factors just boost the final risk assessment near hazards
        depth = round(min(avg_depth * lake_factor * drain_factor, 3.0), 3)

        if depth < 0.1:
            risk = "low"
        elif depth < 0.5:
            risk = "medium"
        else:
            risk = "high"

        G[u][v]["water_depth"] = depth
        G[u][v]["flood_risk"] = risk

    return G
