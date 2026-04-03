import os
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from base_planner import BaseEvacuationPlanner
from .evolution_mixin import EvolutionMixin

class GeneticEvacuationPlanner(BaseEvacuationPlanner, EvolutionMixin):
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
    TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY") 

    def __init__(self, at_risk_nodes, safe_shelters, G,
                 pop_size=60, generations=40, mutation_rate=0.15,
                 use_tomtom_traffic=False, shared_setup=None, **kwargs):
        """
        at_risk_nodes : list of {'id': node_id, 'pop': count, 'lat': y, 'lon': x}
        safe_shelters : list of {'id': str, 'node_id': int, 'capacity': int,
                                  'lat': y, 'lon': x, ...}
        G             : NetworkX road graph with 'length' edge attr and optional
                        'water_depth' node attr
        use_tomtom_traffic: bool - if True, fetches real-time traffic for major roads
        """
        super().__init__(at_risk_nodes, safe_shelters, G,
                         use_tomtom_traffic=use_tomtom_traffic,
                         shared_setup=shared_setup)

        self.pop_size = pop_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.fitness_history = []  # Track convergence speed

        # ── Step 3: greedy nearest-shelter assignment (used to seed population) ─
        # This was already computed by BaseEvacuationPlanner.__init__ 
        # but we ensure it's on this instance.
        print(f"  [GA DEBUG] Traffic Awareness Mode: {'ON' if self.use_tomtom_traffic else 'OFF'}")

    def run(self):
        if not self.at_risk_nodes or not self.safe_shelters:
            self.best_fitness = 0.0
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
            best_in_gen = float(np.min(fitness_scores))
            self.fitness_history.append(best_in_gen)

        fitness_scores = np.array([self._fitness(c) for c in population])
        best_idx = int(np.argmin(fitness_scores))
        self.best_fitness = float(fitness_scores[best_idx])
        self.best_chromosome = population[best_idx]
        best = self.best_chromosome
        print(f"  [GA] Best fitness = {self.best_fitness:.1f}")
        return self._decode(best)

    def calculate_pressure_points(self, results: list, top_n: int = 5):
        from collections import defaultdict
        node_loads = defaultdict(int)
        node_routes = defaultdict(int)
        
        for route in results:
            pop = route.get('pop', 0)
            path_nodes = route.get('path_nodes', [])
            for node in path_nodes:
                node_loads[node] += pop
                node_routes[node] += 1
        
        junctures = []
        for node, load in node_loads.items():
            if node_routes[node] > 1 or load > 500:
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
