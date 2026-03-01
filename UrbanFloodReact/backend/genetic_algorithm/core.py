import os
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .setup_mixin import SetupMixin
from .evolution_mixin import EvolutionMixin
from .geometry_mixin import GeometryMixin

class GeneticEvacuationPlanner(SetupMixin, EvolutionMixin, GeometryMixin):
    # Average walking speed in m/s (roughly 4.3 km/h evacuee pace)
    WALKING_SPEED_MS = 1.2
    
    # How heavily to penalise flooded edges (each metre of depth multiplies edge
    # cost by this factor). 5 makes 20 cm depth roughly double the effective cost.
    FLOOD_PENALTY_FACTOR = 5.0
    
    # Capacity overflow penalty per excess person.
    # 100,000 = equivalent to forcing 100km of walking rather than overflowing by 1
    CAPACITY_PENALTY = 100_000
    
    # Traffic Congestion Penalties
    TRAFFIC_PENALTY_FACTOR = 3.0 # Heavy traffic makes edge 3x "longer"
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") 

    def __init__(self, at_risk_nodes, safe_shelters, G,
                 pop_size=60, generations=40, mutation_rate=0.15, use_google_traffic=False):
        """
        at_risk_nodes : list of {'id': node_id, 'pop': count, 'lat': y, 'lon': x}
        safe_shelters : list of {'id': str, 'node_id': int, 'capacity': int,
                                  'lat': y, 'lon': x, ...}
        G             : NetworkX road graph with 'length' edge attr and optional
                        'water_depth' node attr
        use_google_traffic: bool - if True, fetches real-time traffic for major roads
        """
        self.at_risk_nodes = at_risk_nodes
        self.safe_shelters = safe_shelters
        self.G = G
        self.pop_size = pop_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.use_google_traffic = use_google_traffic

        n_risk = len(at_risk_nodes)
        n_shelters = len(safe_shelters)
        
        print(f"  [GA DEBUG] Traffic Awareness Mode: {'ON' if self.use_google_traffic else 'OFF'}")

        # ── Step 0: Traffic Integration ───────────────────────────────────────
        if self.use_google_traffic:
            self._update_graph_with_google_traffic()

        # ── Step 1: build flood-aware edge weights ────────────────────────────
        self._add_flood_edge_weights()
        self.pop_size = pop_size
        self.generations = generations
        self.mutation_rate = mutation_rate

        # ── Step 2: precompute cost matrices (network distance + travel time) ─
        self.dist_matrix = np.full((n_risk, n_shelters), np.inf)
        self.time_matrix = np.full((n_risk, n_shelters), np.inf)
        self._compute_matrices()

        # ── Step 3: greedy nearest-shelter assignment (used to seed population) ─
        self._greedy_chromosome = self._compute_greedy_chromosome()

    def run(self):
        if not self.at_risk_nodes or not self.safe_shelters:
            return []

        population = self._init_population()

        elite_n = max(1, self.pop_size // 10)  # top 10% preserved each gen

        for gen in range(self.generations):
            fitness_scores = np.array([self._fitness(c) for c in population])

            # Elite preservation — carry best chromosomes unchanged
            elite_idx = np.argsort(fitness_scores)[:elite_n]
            elites = [population[i] for i in elite_idx]

            new_pop = list(elites)
            while len(new_pop) < self.pop_size:
                p1 = self._selection(population, fitness_scores)
                p2 = self._selection(population, fitness_scores)
                c1, c2 = self._crossover(p1, p2)
                new_pop.append(self._mutate(c1))
                if len(new_pop) < self.pop_size:
                    new_pop.append(self._mutate(c2))

            population = new_pop

        fitness_scores = np.array([self._fitness(c) for c in population])
        best = population[int(np.argmin(fitness_scores))]
        return self._decode(best)
