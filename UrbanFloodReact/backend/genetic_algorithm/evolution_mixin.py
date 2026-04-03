import random
import math
import numpy as np
from collections import defaultdict

class EvolutionMixin:

    # ── Population Initialisation ─────────────────────────────────────────────

    def _init_population(self):
        """
        Seed 80% of population with variants of the greedy chromosome (small
        random perturbations), and 20% fully random capacity-aware assignments.
        All chromosomes are capacity-repaired before entering the pool.
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
                if chrom[i] == -1:
                    continue  # already unassigned — leave it
                if random.random() < 0.15:
                    row = self.dist_matrix[i]
                    nearest3 = np.argsort(row)[:3]
                    chrom[i] = int(random.choice(nearest3))
            pop.append(self._capacity_repair(chrom))

        for _ in range(random_count):
            # Capacity-aware random: track remaining capacity and don't assign
            # to a shelter that's already full (fast greedy fill from random order)
            remaining = [s['capacity'] for s in self.safe_shelters]
            chrom = []
            indices = list(range(len(self.at_risk_nodes)))
            random.shuffle(indices)
            assigned = [-1] * len(self.at_risk_nodes)
            for i in indices:
                pop_i = self.at_risk_nodes[i]['pop']
                # Try shelters in random order, pick first with capacity left
                order = list(range(n_shelters))
                random.shuffle(order)
                chosen = -1
                for j in order:
                    if remaining[j] >= pop_i:
                        chosen = j
                        remaining[j] -= pop_i
                        break
                assigned[i] = chosen
            pop.append(assigned)

        return pop

    # ── Capacity Repair ───────────────────────────────────────────────────────

    def _capacity_repair(self, chromosome):
        """
        Post-process a chromosome to guarantee no shelter exceeds its capacity.

        For each over-capacity shelter:
          1. Sort its assigned nodes worst-first (farthest from shelter).
          2. Move excess nodes to the nearest shelter with remaining capacity.
          3. If no shelter has remaining capacity, mark the node as -1 (unassigned).

        This makes every chromosome in the population capacity-feasible,
        so the GA never evolves or selects an illegal solution.
        """
        n_shelters = len(self.safe_shelters)
        capacities = [s['capacity'] for s in self.safe_shelters]
        assigned_load = defaultdict(int)

        # Calculate shelter loads
        for i, j in enumerate(chromosome):
            if j < 0:
                continue
            assigned_load[j] += self.at_risk_nodes[i]['pop']

        # Remaining capacity per shelter
        remaining = [capacities[j] - assigned_load[j] for j in range(n_shelters)]

        # Identify nodes assigned to over-capacity shelters, worst-first
        for j in range(n_shelters):
            if remaining[j] >= 0:
                continue  # shelter is within capacity

            # Collect nodes assigned to this over-capacity shelter
            overflow_nodes = [
                i for i, s in enumerate(chromosome)
                if s == j
            ]
            # Sort by descending distance to shelter j (remove farthest first)
            overflow_nodes.sort(
                key=lambda i: self.dist_matrix[i, j],
                reverse=True
            )

            for i in overflow_nodes:
                if remaining[j] >= 0:
                    break  # shelter is now within capacity

                pop_i = self.at_risk_nodes[i]['pop']

                # Try to find another shelter with remaining capacity,
                # sorted by distance from node i (nearest alternative first)
                alt_order = np.argsort(self.dist_matrix[i])
                moved = False
                for alt_j in alt_order:
                    alt_j = int(alt_j)
                    if alt_j == j:
                        continue
                    if remaining[alt_j] >= pop_i:
                        chromosome[i] = alt_j
                        remaining[alt_j] -= pop_i
                        remaining[j] += pop_i
                        moved = True
                        break

                if not moved:
                    # No shelter can absorb this group — mark unassigned
                    chromosome[i] = -1
                    remaining[j] += pop_i

        return chromosome

    # ── Selection ─────────────────────────────────────────────────────────────

    def _selection(self, population, fitness_scores):
        """Tournament selection with k=3."""
        idxs = random.sample(range(len(population)), min(3, len(population)))
        best = min(idxs, key=lambda i: fitness_scores[i])
        return population[best]

    # ── Crossover ─────────────────────────────────────────────────────────────

    def _crossover(self, p1, p2):
        """Two-point crossover + capacity repair on offspring."""
        n = len(p1)
        if n < 3:
            return list(p1), list(p2)
        a, b = sorted(random.sample(range(n), 2))
        c1 = p1[:a] + p2[a:b] + p1[b:]
        c2 = p2[:a] + p1[a:b] + p2[b:]
        return self._capacity_repair(c1), self._capacity_repair(c2)

    # ── Mutation ──────────────────────────────────────────────────────────────

    def _mutate(self, chrom):
        """
        Mutation: reassign a node to one of its 3 nearest shelters (distance-
        biased), but only if that shelter still has remaining capacity.
        Falls back to -1 (unassigned) if no shelters have space.
        Always runs capacity repair after mutation for safety.
        """
        # Precompute current shelter loads to make capacity-aware choices
        shelter_load = defaultdict(int)
        for i, j in enumerate(chrom):
            if j >= 0:
                shelter_load[j] += self.at_risk_nodes[i]['pop']

        for i in range(len(chrom)):
            if random.random() < self.mutation_rate:
                pop_i = self.at_risk_nodes[i]['pop']
                # Remove this node's load from its current shelter
                cur = chrom[i]
                if cur >= 0:
                    shelter_load[cur] -= pop_i

                # Pick from top-3 nearest shelters that have remaining capacity
                nearest3 = np.argsort(self.dist_matrix[i])[:3]
                caps = [s['capacity'] for s in self.safe_shelters]
                candidates = [
                    int(j) for j in nearest3
                    if caps[int(j)] - shelter_load[int(j)] >= pop_i
                ]
                if candidates:
                    chosen = random.choice(candidates)
                    chrom[i] = chosen
                    shelter_load[chosen] += pop_i
                else:
                    chrom[i] = -1  # no capacity anywhere — leave unassigned

        return self._capacity_repair(chrom)  # final safety pass
