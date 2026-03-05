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
        Returns a single scalar so all three planners are ranked on the
        exact same objective.
        """
        total_dist    = 0.0
        total_time    = 0.0
        shelter_counts = defaultdict(int)

        for i, j in enumerate(chromosome):
            pop  = self.at_risk_nodes[i]['pop']
            dist = self.dist_matrix[i, j]
            t    = self.time_matrix[i, j]

            if not math.isfinite(dist): dist = 1_000_000
            if not math.isfinite(t):    t    = 1_000_000

            total_dist      += dist * pop
            total_time      += t    * pop
            shelter_counts[j] += pop

        penalty = 0.0
        for j, count in shelter_counts.items():
            cap = self.safe_shelters[j]['capacity']
            if count > cap:
                penalty += ((count - cap) ** 2) * self.CAPACITY_PENALTY

        return total_dist + 0.5 * total_time + penalty

    # ─────────────────────────────────────────────────────────────────────────
    # run() must be implemented by each concrete planner
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        raise NotImplementedError("Subclass must implement run()")
