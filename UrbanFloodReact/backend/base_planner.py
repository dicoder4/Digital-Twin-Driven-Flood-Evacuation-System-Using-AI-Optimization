"""
base_planner.py
───────────────
Shared base class for all evacuation optimisation planners.

Provides:
  - Common constants (walk speed, flood penalty, capacity penalty)
  - Graph pre-processing    : _add_flood_edge_weights()
  - Matrix precomputation   : dist_matrix, time_matrix  (Dijkstra, once)
  - Greedy seed chromosome  : _compute_greedy_chromosome()
  - Shared fitness function : _fitness(chromosome)
  - Route decode + geometry : _decode(), _path_to_coords()
  - Nearest-node fallback   : _find_nearest_node_robust()

Each concrete planner (GA, ACO, PSO) inherits this class and only needs
to implement:
    def run(self) -> list[dict]
        Returns the decoded route list (same format as GA).

The __init__ accepts the same signature as GeneticEvacuationPlanner so
service.py can swap planners transparently.
"""

import os
import math
import copy
import numpy as np
import networkx as nx
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Reuse the existing setup_mixin & geometry_mixin from the GA package
from genetic_algorithm.setup_mixin import SetupMixin
from genetic_algorithm.geometry_mixin import GeometryMixin


class BaseEvacuationPlanner(SetupMixin, GeometryMixin):
    """
    Abstract base – do NOT instantiate directly.
    Concrete planners must implement `run()`.
    """

    # ── Shared constants (can be overridden per-planner if needed) ──────────
    WALKING_SPEED_MS     = 1.2       # m/s  (~4.3 km/h evacuee pace)
    FLOOD_PENALTY_FACTOR = 5.0       # each metre of water depth × this factor
    CAPACITY_PENALTY     = 100_000   # per-person quadratic overflow penalty
    TRAFFIC_PENALTY_FACTOR = 3.0
    TOMTOM_API_KEY       = os.getenv("TOMTOM_API_KEY")

    def __init__(self, at_risk_nodes, safe_shelters, G,
                 use_tomtom_traffic: bool = False, shared_setup=None):
        """
        at_risk_nodes : list[dict]  – {'id', 'pop', 'lat', 'lon'}
        safe_shelters : list[dict]  – {'id', 'node_id', 'capacity', 'lat', 'lon', ...}
        G             : NetworkX MultiDiGraph  (OSMnx road graph)
        use_tomtom_traffic : bool  – fetch real-time traffic if True
        shared_setup  : BaseEvacuationPlanner – another instance to copy matrices from
        """
        self.at_risk_nodes      = at_risk_nodes
        self.safe_shelters      = safe_shelters
        self.G                  = G
        self.use_tomtom_traffic = use_tomtom_traffic

        n_risk     = len(at_risk_nodes)
        n_shelters = len(safe_shelters)

        if shared_setup:
            # Skip heavy initialization
            self.dist_matrix = copy.deepcopy(shared_setup.dist_matrix)
            self.time_matrix = copy.deepcopy(shared_setup.time_matrix)
            self._greedy_chromosome = copy.deepcopy(shared_setup._greedy_chromosome)
            self.G = shared_setup.G  # share graph (which has flood/traffic weights)
        else:
            # Step 0 – optional live traffic layer
            if self.use_tomtom_traffic:
                self._update_graph_with_tomtom_traffic()

            # Step 1 – annotate edges with flood_weight (+ traffic if available)
            self._add_flood_edge_weights()

            # Step 2 – precompute cost matrices with a single Dijkstra per shelter
            self.dist_matrix = np.full((n_risk, n_shelters), np.inf)
            self.time_matrix = np.full((n_risk, n_shelters), np.inf)
            self._compute_matrices()

            # Step 3 – greedy assignment (used as seed / heuristic by all planners)
            self._greedy_chromosome = self._compute_greedy_chromosome()

    # ─────────────────────────────────────────────────────────────────────────
    # Shared fitness (identical formula for fair comparison across algorithms)
    # ─────────────────────────────────────────────────────────────────────────

    def _fitness(self, chromosome: list) -> float:
        """
        Multi-factor fitness (lower = better):
          total_dist  — flood-weighted network distance per person
          total_time  — raw travel time per person
          penalty     — quadratic capacity overflow penalty
          terrain_penalty — penalize shelters at lower elevation than source
        Returns a single scalar so all three planners are ranked on the
        exact same objective.
        """
        total_dist      = 0.0
        total_time      = 0.0
        terrain_penalty = 0.0
        shelter_counts  = defaultdict(int)

        for i, j in enumerate(chromosome):
            pop = self.at_risk_nodes[i]['pop']

            if j < 0:
                # Penalise unassigned nodes — equivalent to 1000 km of walking per person
                total_dist += 1_000_000 * pop
                total_time += 1_000_000 * pop
                continue

            dist = self.dist_matrix[i, j]
            t    = self.time_matrix[i, j]

            if not math.isfinite(dist):
                # Penalty for assigning to an unreachable shelter
                # MUST be much worse than unassigned (-1) to prevent the solvers
                # from making fake assignments that fail DECODE.
                dist = 10_000_000
            if not math.isfinite(t):
                t = 10_000_000

            # GIS Physics Enhancement: Terrain-Aware Selection
            # We want to penalize moving "downhill" into a potential trap
            source_elev = self.at_risk_nodes[i].get('elevation', 900.0) # default if missing
            dest_elev   = self.safe_shelters[j].get('elevation', 900.0)
            
            # If shelter is lower than source, apply penalty proportional to the drop
            # This encourages "uphill" evacuation
            if dest_elev < source_elev:
                drop = source_elev - dest_elev
                penalty_val = drop * 50.0 * pop
                terrain_penalty += penalty_val
            
            # Absolute low-ground penalty: Shelters in deep valleys are risky
            if dest_elev < 880.0: # threshold for "low-ground" in Bangalore context
                terrain_penalty += 500.0 * pop

            total_dist        += dist * pop
            total_time        += t    * pop
            shelter_counts[j] += pop

        penalty = 0.0
        for j, count in shelter_counts.items():
            cap = self.safe_shelters[j]['capacity']
            if count > cap:
                penalty += ((count - cap) ** 2) * self.CAPACITY_PENALTY

        return total_dist + 0.5 * total_time + penalty + terrain_penalty

    def _fitness_breakdown(self, chromosome: list) -> dict:
        """
        Calculates separate fitness components for analysis.
        """
        total_dist      = 0.0
        total_time      = 0.0
        terrain_penalty = 0.0
        shelter_counts  = defaultdict(int)

        for i, j in enumerate(chromosome):
            if j < 0:
                continue

            pop  = self.at_risk_nodes[i]['pop']
            dist = self.dist_matrix[i, j]
            t    = self.time_matrix[i, j]

            if not math.isfinite(dist): dist = 1_000_000
            if not math.isfinite(t):    t    = 1_000_000

            source_elev = self.at_risk_nodes[i].get('elevation', 900.0)
            dest_elev   = self.safe_shelters[j].get('elevation', 900.0)
            
            if dest_elev < source_elev:
                terrain_penalty += (source_elev - dest_elev) * 50.0 * pop
            if dest_elev < 880.0:
                terrain_penalty += 500.0 * pop

            total_dist        += dist * pop
            total_time        += t    * pop
            shelter_counts[j] += pop

        penalty = 0.0
        for j, count in shelter_counts.items():
            cap = self.safe_shelters[j]['capacity']
            if count > cap:
                penalty += ((count - cap) ** 2) * self.CAPACITY_PENALTY

        return {
            "distance_score": round(total_dist, 1),
            "time_score": round(0.5 * total_time, 1),
            "capacity_penalty": round(penalty, 1),
            "terrain_penalty": round(terrain_penalty, 1),
            "total_fitness": round(total_dist + 0.5 * total_time + penalty + terrain_penalty, 1)
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Capacity repair — shared by GA, ACO, and PSO
    # ─────────────────────────────────────────────────────────────────────────

    def _capacity_repair(self, chromosome: list) -> list:
        """
        Post-process a chromosome (list of ints) to guarantee no shelter exceeds
        its capacity.

        For each over-capacity shelter:
          1. Sort its assigned nodes worst-first (farthest from shelter).
          2. Move excess nodes to the nearest shelter with remaining capacity.
          3. If no shelter has remaining capacity, mark the node as -1 (unassigned).

        Returns the (modified-in-place) chromosome.
        """
        n_shelters    = len(self.safe_shelters)
        capacities    = [s['capacity'] for s in self.safe_shelters]
        assigned_load = defaultdict(int)

        for i, j in enumerate(chromosome):
            if j >= 0:
                assigned_load[j] += self.at_risk_nodes[i]['pop']

        remaining = [capacities[j] - assigned_load[j] for j in range(n_shelters)]

        for j in range(n_shelters):
            if remaining[j] >= 0:
                continue

            overflow_nodes = [i for i, s in enumerate(chromosome) if s == j]
            overflow_nodes.sort(key=lambda i, _j=j: self.dist_matrix[i, _j], reverse=True)

            for i in overflow_nodes:
                if remaining[j] >= 0:
                    break

                pop_i     = self.at_risk_nodes[i]['pop']
                alt_order = np.argsort(self.dist_matrix[i])
                moved     = False
                for alt_j in alt_order:
                    alt_j = int(alt_j)
                    if alt_j == j:
                        continue
                    if remaining[alt_j] >= pop_i:
                        chromosome[i]    = alt_j
                        remaining[alt_j] -= pop_i
                        remaining[j]     += pop_i
                        moved = True
                        break

                if not moved:
                    chromosome[i]  = -1
                    remaining[j]  += pop_i

        return chromosome

    # ─────────────────────────────────────────────────────────────────────────
    # run() must be implemented by each concrete planner
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_pressure_points(self, results: list, top_n: int = 5):
        """
        Post-process the evacuation plan to find critical junctions (pressure points)
        where many evacuees converge.
        """
        node_loads = defaultdict(int)
        node_routes = defaultdict(int)
        
        for route in results:
            pop = route.get('pop', 0)
            path_nodes = route.get('path_nodes', [])
            for node in path_nodes:
                node_loads[node] += pop
                node_routes[node] += 1
        
        # Filter for "junctions": nodes where more than one route cluster passes through
        # OR extremely high load nodes.
        junctures = []
        for node, load in node_loads.items():
            if node_routes[node] > 1 or load > 500: # Thresholds for significance
                data = self.G.nodes[node]
                junctures.append({
                    "node_id": node,
                    "location_name": self._resolve_node_name(node),
                    "lat": data.get('y'),
                    "lon": data.get('x'),
                    "total_evacuees": load,
                    "route_count": node_routes[node],
                    "flood_depth": data.get('water_depth', 0)
                })
        
        # Sort by load descending
        junctures.sort(key=lambda x: x['total_evacuees'], reverse=True)
        return junctures[:top_n]

    def _resolve_node_name(self, node_id):
        """
        Resolve a readable junction name using the centralized BFS resolver.
        """
        from service import _resolve_road_name
        name = _resolve_road_name(node_id, self.G, max_depth=3)
        if name:
            return name
        
        # Fallback to coordinate name
        return f"Junction near ({round(self.G.nodes[node_id].get('y',0), 4)}, {round(self.G.nodes[node_id].get('x',0), 4)})"

    def run(self):
        raise NotImplementedError("Subclass must implement run()")
