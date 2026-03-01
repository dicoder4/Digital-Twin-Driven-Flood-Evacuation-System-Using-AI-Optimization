import math
import numpy as np
import networkx as nx

class SetupMixin:
    def _add_flood_edge_weights(self):
        """
        Annotate every edge with 'flood_weight':
            flood_weight = length × (1 + FLOOD_PENALTY_FACTOR × avg_water_depth)
        This makes evacuees prefer dry roads automatically when we run Dijkstra
        with weight='flood_weight'.
        """
        for u, v, data in self.G.edges(data=True):
            base = data.get('length', 1.0)
            depth_u = self.G.nodes[u].get('water_depth', 0.0)
            depth_v = self.G.nodes[v].get('water_depth', 0.0)
            avg_depth = (depth_u + depth_v) / 2.0
            # nx multigraph stores parallel edges; handle both Graph and MultiGraph
            flood_w = base * (1.0 + self.FLOOD_PENALTY_FACTOR * avg_depth)
            data['flood_weight'] = flood_w

    def _compute_matrices(self):
        """
        For each shelter, run a single-source Dijkstra to all nodes using
        flood_weight. This gives O(S × E log V) precomputation — fast because
        we only do it once before the GA starts.
        """
        for j, shelter in enumerate(self.safe_shelters):
            s_node = shelter.get('node_id')

            if s_node is None or not self.G.has_node(s_node):
                # Fallback: Euclidean in degrees → approximate metres
                for i, node in enumerate(self.at_risk_nodes):
                    d = math.sqrt(
                        (node['lat'] - shelter['lat']) ** 2 +
                        (node['lon'] - shelter['lon']) ** 2
                    ) * 111_000
                    self.dist_matrix[i, j] = d
                    self.time_matrix[i, j] = d / self.WALKING_SPEED_MS
                continue

            try:
                # flood-weighted cost (for fitness)
                flood_lengths = nx.single_source_dijkstra_path_length(
                    self.G, s_node, weight='flood_weight'
                )
                # raw length (for time estimate — we don't slow evacuees by depth,
                # we just make flooded paths more costly to choose)
                raw_lengths = nx.single_source_dijkstra_path_length(
                    self.G, s_node, weight='length'
                )
            except Exception:
                continue

            for i, node in enumerate(self.at_risk_nodes):
                r_node = node['id']
                if r_node in flood_lengths:
                    self.dist_matrix[i, j] = flood_lengths[r_node]
                if r_node in raw_lengths:
                    self.time_matrix[i, j] = raw_lengths[r_node] / self.WALKING_SPEED_MS

    def _compute_greedy_chromosome(self):
        """
        Greedy assignment: each at-risk node gets the nearest reachable shelter
        (by flood-weighted distance). Respects capacity — once a shelter is full,
        the next-nearest is tried or overflow distributed to lowest fill ratio.
        """
        n_shelters = len(self.safe_shelters)
        capacities = [s['capacity'] for s in self.safe_shelters]
        assigned_counts = [0] * n_shelters
        chromosome = []

        for i in range(len(self.at_risk_nodes)):
            pop = self.at_risk_nodes[i]['pop']
            # Sort shelters by flood-weighted distance
            order = np.argsort(self.dist_matrix[i])
            
            chosen = int(order[0])
            best_overflow_j = chosen
            min_ratio = float('inf')

            for j in order:
                j = int(j)
                ratio = (assigned_counts[j] + pop) / max(1.0, capacities[j])
                
                # If there's physical space, take it immediately
                if ratio <= 1.0:
                    chosen = j
                    break
                
                # Otherwise, track the shelter with the least proportional overflow
                if ratio < min_ratio:
                    min_ratio = ratio
                    best_overflow_j = j
            else:
                # Loop exhausted: all shelters are over capacity. 
                # Pick the one with the smallest overflow ratio instead of the absolute nearest.
                chosen = best_overflow_j

            assigned_counts[chosen] += pop
            chromosome.append(chosen)

        return chromosome
