"""
evacuation_ga.py
────────────────
Genetic Algorithm for post-flood evacuation routing.

Multi-factor fitness:
  1. Flood-aware network distance   — shortest path using road lengths penalised
                                      by flood depth (deep water = effectively longer)
  2. Estimated travel time          — raw network distance / walking speed
  3. Capacity overflow penalty      — heavy penalty if shelter is over-assigned

Population seeding:
  - 80% greedy: each at-risk node assigned to its nearest (flood-weighted) shelter
  - 20% random: ensures diversity so GA can escape local optima

Elitism: top N chromosomes are carried unchanged into the next generation.
"""
import random
import math
import numpy as np
import networkx as nx
from collections import defaultdict


class GeneticEvacuationPlanner:
    # Average walking speed in m/s (roughly 4.3 km/h evacuee pace)
    WALKING_SPEED_MS = 1.2
    # How heavily to penalise flooded edges (each metre of depth multiplies edge
    # cost by this factor). 5 makes 20 cm depth roughly double the effective cost.
    FLOOD_PENALTY_FACTOR = 5.0
    # Capacity overflow penalty per excess person.
    # 100,000 = equivalent to forcing 100km of walking rather than overflowing by 1
    CAPACITY_PENALTY = 100_000

    def __init__(self, at_risk_nodes, safe_shelters, G,
                 pop_size=60, generations=40, mutation_rate=0.15):
        """
        at_risk_nodes : list of {'id': node_id, 'pop': count, 'lat': y, 'lon': x}
        safe_shelters : list of {'id': str, 'node_id': int, 'capacity': int,
                                  'lat': y, 'lon': x, ...}
        G             : NetworkX road graph with 'length' edge attr and optional
                        'water_depth' node attr
        """
        self.at_risk_nodes = at_risk_nodes
        self.safe_shelters = safe_shelters
        self.G = G
        self.pop_size = pop_size
        self.generations = generations
        self.mutation_rate = mutation_rate

        n_risk = len(at_risk_nodes)
        n_shelters = len(safe_shelters)

        # ── Step 1: build flood-aware edge weights ────────────────────────────
        self._add_flood_edge_weights()

        # ── Step 2: precompute cost matrices (network distance + travel time) ─
        # dist_matrix[i, j] = flood-weighted network cost from at_risk[i] → shelter[j]
        # time_matrix[i, j] = estimated travel time in seconds (raw length / speed)
        self.dist_matrix = np.full((n_risk, n_shelters), np.inf)
        self.time_matrix = np.full((n_risk, n_shelters), np.inf)
        self._compute_matrices()

        # ── Step 3: greedy nearest-shelter assignment (used to seed population) ─
        self._greedy_chromosome = self._compute_greedy_chromosome()

    # ─────────────────────────────────────────────────────────────────────────
    # Setup helpers
    # ─────────────────────────────────────────────────────────────────────────

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
        the next-nearest is tried.
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

    # ─────────────────────────────────────────────────────────────────────────
    # GA core
    # ─────────────────────────────────────────────────────────────────────────

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

    def _init_population(self):
        """
        Seed 80% of population with variants of the greedy chromosome (small
        random perturbations), and 20% fully random.  This gives the GA a
        strong starting point while keeping diversity.
        """
        n_shelters = len(self.safe_shelters)
        pop = []

        greedy_count = int(self.pop_size * 0.8)
        random_count = self.pop_size - greedy_count

        for _ in range(greedy_count):
            # Perturb greedy solution: randomly reassign ~15% of nodes to their
            # 2nd or 3rd nearest shelter so we don't all start from the same point
            chrom = list(self._greedy_chromosome)
            for i in range(len(chrom)):
                if random.random() < 0.15:
                    # Pick one of the 3 nearest shelters (weighted by distance)
                    row = self.dist_matrix[i]
                    nearest3 = np.argsort(row)[:3]
                    chrom[i] = int(random.choice(nearest3))
            pop.append(chrom)

        for _ in range(random_count):
            # Purely random — ensures exploration
            pop.append([random.randint(0, n_shelters - 1)
                        for _ in range(len(self.at_risk_nodes))])

        return pop

    def _fitness(self, chromosome):
        """
        Multi-factor fitness (lower = better):
          - Weighted sum of flood-aware network distance per person
          - Weighted sum of travel time per person
          - Heavy capacity overflow penalty
        """
        total_dist = 0.0
        total_time = 0.0
        shelter_counts = defaultdict(int)

        for i, j in enumerate(chromosome):
            pop = self.at_risk_nodes[i]['pop']
            dist = self.dist_matrix[i, j]
            t = self.time_matrix[i, j]

            # If infinite (disconnected), use a large fallback
            if not math.isfinite(dist):
                dist = 1_000_000
            if not math.isfinite(t):
                t = 1_000_000

            total_dist += dist * pop
            total_time += t * pop
            shelter_counts[j] += pop

        # Combine: distance is the primary factor, time adds secondary weight.
        # Penalty is quadratic so that putting 1000 extra people in 1 shelter
        # is mathematically *much* worse than putting 100 extra people in 10 shelters.
        penalty = 0.0
        for j, count in shelter_counts.items():
            cap = self.safe_shelters[j]['capacity']
            if count > cap:
                penalty += ((count - cap) ** 2) * self.CAPACITY_PENALTY

        return total_dist + 0.5 * total_time + penalty

    def _selection(self, population, fitness_scores):
        """Tournament selection with k=3."""
        idxs = random.sample(range(len(population)), min(3, len(population)))
        best = min(idxs, key=lambda i: fitness_scores[i])
        return population[best]

    def _crossover(self, p1, p2):
        """Two-point crossover for less disruptive recombination."""
        n = len(p1)
        if n < 3:
            return list(p1), list(p2)
        a, b = sorted(random.sample(range(n), 2))
        c1 = p1[:a] + p2[a:b] + p1[b:]
        c2 = p2[:a] + p1[a:b] + p2[b:]
        return c1, c2

    def _mutate(self, chrom):
        """
        Mutation: with probability mutation_rate, reassign a node to one of
        its 3 nearest shelters (distance-biased) rather than purely random.
        This keeps mutations locally sensible.
        """
        for i in range(len(chrom)):
            if random.random() < self.mutation_rate:
                # Prefer nearby shelters — pick from top-3 nearest
                nearest3 = np.argsort(self.dist_matrix[i])[:3]
                chrom[i] = int(random.choice(nearest3))
        return chrom

    # ─────────────────────────────────────────────────────────────────────────
    # Node snapping helper (ported from old evacuation_algorithms.py)
    # ─────────────────────────────────────────────────────────────────────────

    def _find_nearest_node_robust(self, lat, lon):
        """
        3-strategy fallback to always resolve a (lat, lon) to a valid graph node.
        Ported from find_nearest_node_robust() in the old evacuation_algorithms.py.

        Strategy 1: ox.distance.nearest_nodes (fast BallTree spatial index)
        Strategy 2: manual Euclidean brute-force over all nodes
        Strategy 3: first node in graph (last resort)
        """
        import osmnx as ox
        try:
            # OSMnx uses (X=lon, Y=lat) ordering
            return ox.distance.nearest_nodes(self.G, lon, lat)
        except Exception:
            pass
        try:
            min_dist = float('inf')
            nearest = None
            for node, data in self.G.nodes(data=True):
                if 'x' in data and 'y' in data:
                    dist = ((lon - data['x']) ** 2 + (lat - data['y']) ** 2) ** 0.5
                    if dist < min_dist:
                        min_dist = dist
                        nearest = node
            if nearest is not None:
                return nearest
        except Exception:
            pass
        # Last resort: return the first node in the graph
        return next(iter(self.G.nodes()))

    # ─────────────────────────────────────────────────────────────────────────
    # Decode: build route geometries for the map
    # ─────────────────────────────────────────────────────────────────────────

    def _path_to_coords(self, path_nodes):
        """
        Convert a list of node IDs into [lon, lat] coordinate pairs that follow
        the actual road curvature stored in OSMnx edge geometry attributes.

        OSMnx stores road curves as a Shapely LineString on each edge
        (G[u][v][key]['geometry']).  Using only node coordinates (intersections)
        loses all intermediate waypoints, making curved/diagonal roads appear
        as straight lines on the map.
        """
        coords = []
        for k in range(len(path_nodes) - 1):
            u, v = path_nodes[k], path_nodes[k + 1]

            # OSMnx uses MultiDiGraph: G[u][v] = {0: {edge_data}, 1: ...}
            edge_dict = self.G.get_edge_data(u, v)
            if edge_dict is None:
                # Defensive: no edge found, use straight node-to-node segment
                if k == 0:
                    coords.append([self.G.nodes[u]['x'], self.G.nodes[u]['y']])
                coords.append([self.G.nodes[v]['x'], self.G.nodes[v]['y']])
                continue

            # Pick the parallel edge with the shortest length (matches Dijkstra)
            if isinstance(next(iter(edge_dict.values())), dict):
                best = min(edge_dict.values(),
                           key=lambda d: d.get('length', float('inf')))
            else:
                best = edge_dict

            geom = best.get('geometry')  # Shapely LineString or None
            if geom is not None:
                seg = [[c[0], c[1]] for c in geom.coords]
            else:
                # No geometry stored — straight line between the two nodes
                seg = [
                    [self.G.nodes[u]['x'], self.G.nodes[u]['y']],
                    [self.G.nodes[v]['x'], self.G.nodes[v]['y']],
                ]

            if k == 0:
                coords.extend(seg)          # include the start node
            else:
                coords.extend(seg[1:])      # skip duplicate junction point

        # Edge case: single-node path (origin == destination)
        if not coords and path_nodes:
            n = path_nodes[0]
            coords = [[self.G.nodes[n]['x'], self.G.nodes[n]['y']]]

        return coords

    def _decode(self, chromosome):
        results = []
        for i, j in enumerate(chromosome):
            node_info = self.at_risk_nodes[i]
            shelter   = self.safe_shelters[j]
            pop       = node_info['pop']
            node_id   = node_info['id']

            # Straight-line — only kept if all snapping + pathfinding fails
            path_coords = [
                [node_info['lon'], node_info['lat']],
                [shelter['lon'],   shelter['lat']],
            ]
            fallback = True

            # ── Resolve at-risk node ──────────────────────────────────────────
            # at_risk node_id is already a graph node, but guard against stale copies
            if not self.G.has_node(node_id):
                node_id = self._find_nearest_node_robust(node_info['lat'], node_info['lon'])
                print(f"  [DECODE] at-risk node snapped to {node_id} via nearest-node lookup")

            # ── Resolve shelter node ─────────────────────────────────────────
            # This is the primary cause of straight-line routes: shelter.node_id
            # is None or belongs to a different graph copy.
            shelter_node = shelter.get('node_id')
            if shelter_node is None or not self.G.has_node(shelter_node):
                shelter_node = self._find_nearest_node_robust(shelter['lat'], shelter['lon'])
                print(f"  [DECODE] shelter '{shelter['id']}' snapped to node {shelter_node} via lat/lon")

            # ── Path geometry via flood-aware shortest path ───────────────────
            try:
                path_nodes = nx.shortest_path(
                    self.G, node_id, shelter_node, weight='flood_weight'
                )
                # Extract full road geometry (edge waypoints), not just node coords.
                # This prevents diagonal/curved roads from appearing as straight lines.
                path_coords = self._path_to_coords(path_nodes)
                fallback = False
            except Exception as e:
                # Truly disconnected — keep straight-line and flag it
                print(f"  [DECODE] no road path from {node_id} to {shelter_node}: {e}")

            results.append({
                'from_node':  node_info['id'],
                'to_shelter': shelter['id'],
                'pop':        pop,
                'path':       path_coords,
                'fallback':   fallback,   # True = straight-line (disconnected nodes)
            })
        return results
