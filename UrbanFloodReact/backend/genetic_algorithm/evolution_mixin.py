import random
import math
import numpy as np
from collections import defaultdict

class EvolutionMixin:
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
