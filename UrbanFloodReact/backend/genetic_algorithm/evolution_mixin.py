import random
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

    # ── _capacity_repair is inherited from BaseEvacuationPlanner ─────────────
    # Defined there so GA, ACO, and PSO all share the same implementation.

    # ── _fitness is inherited from BaseEvacuationPlanner ──────────────────────
    # All three planners (GA, ACO, PSO) use the same fitness function
    # defined in base_planner.py for fair, consistent comparison.
    # Do NOT define a local _fitness here — it would be shadowed by the MRO
    # anyway (BaseEvacuationPlanner comes first), but removing the dead code
    # prevents confusion.

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
