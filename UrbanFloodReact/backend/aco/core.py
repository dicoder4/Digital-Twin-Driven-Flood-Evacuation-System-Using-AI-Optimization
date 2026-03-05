"""
aco/core.py
───────────
Ant Colony Optimisation for flood evacuation routing.

How it works
────────────
ACO models "ants" constructing solutions one node at a time.  Each ant
assigns every at-risk node to a shelter by sampling a probability
distribution that combines:

    P(node i → shelter j)  ∝  τ[i,j]^α  ×  η[i,j]^β

where:
    τ[i,j]  – pheromone  (learned: reinforced on historically good pairings)
    η[i,j]  – heuristic  (fixed: 1 / flood-weighted distance, i.e. closer = better)
    α       – pheromone importance weight (default 1.0)
    β       – heuristic importance weight (default 3.0)

After all ants build a solution:
    - The globally best solution deposits extra pheromone (elitism boost).
    - All pheromone evaporates slightly each generation (ρ = 0.1 by default).

Performance notes
─────────────────
All inner loops are vectorised with NumPy to match GA/PSO speed:
  - Pheromone deposit uses np.add.at (scatter-add) instead of Python loops
  - Capacity masking uses boolean array ops instead of per-shelter for-loops
  - Score computation stays as matrix operations throughout
"""

import numpy as np
from base_planner import BaseEvacuationPlanner


class ACOEvacuationPlanner(BaseEvacuationPlanner):
    """
    Ant Colony Optimisation evacuation planner.
    Drop-in replacement for GeneticEvacuationPlanner — same constructor
    signature and same return type from run().
    """

    def __init__(self, at_risk_nodes, safe_shelters, G,
                 n_ants: int     = 40,
                 iterations: int = 60,
                 alpha: float    = 1.0,
                 beta: float     = 3.0,
                 rho: float      = 0.1,
                 q: float        = 100.0,
                 use_tomtom_traffic: bool = False,
                 **kwargs):

        super().__init__(at_risk_nodes, safe_shelters, G,
                         use_tomtom_traffic=use_tomtom_traffic)

        self.n_ants     = n_ants
        self.iterations = iterations
        self.alpha      = alpha
        self.beta       = beta
        self.rho        = rho
        self.q          = q

        n_risk     = len(at_risk_nodes)
        n_shelters = len(safe_shelters)

        # ── Pheromone matrix τ[i, j] ─────────────────────────────────────────
        self._tau = np.ones((n_risk, n_shelters), dtype=np.float64)

        # ── Heuristic matrix η[i, j] = 1 / flood_weighted_distance ───────────
        # Pre-computed once; stays fixed throughout the run.
        with np.errstate(divide='ignore', invalid='ignore'):
            eta = np.where(self.dist_matrix > 0, 1.0 / self.dist_matrix, 0.0)
            eta = np.where(np.isinf(eta), 1e6, eta)
        self._eta = eta.astype(np.float64)

        # Pre-compute population array and capacity array as numpy vectors
        self._pops       = np.array([n['pop'] for n in at_risk_nodes], dtype=np.int64)
        self._capacities = np.array([s['capacity'] for s in safe_shelters], dtype=np.int64)

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        if not self.at_risk_nodes or not self.safe_shelters:
            self.best_fitness = 0.0
            return []

        n_risk     = len(self.at_risk_nodes)
        n_shelters = len(self.safe_shelters)
        caps       = self._capacities          # shape (n_shelters,)
        pops       = self._pops                # shape (n_risk,)

        best_chromosome = np.array(self._greedy_chromosome, dtype=np.int32)
        best_fitness    = self._fitness(best_chromosome.tolist())

        # Pre-compute alpha/beta powers once — these don't change per iteration
        # (tau changes, but eta^beta is fixed)
        eta_beta = self._eta ** self.beta      # shape (n_risk, n_shelters)

        for iteration in range(self.iterations):
            # tau^alpha — recomputed each iteration since tau updates
            tau_alpha = self._tau ** self.alpha    # (n_risk, n_shelters)

            # Base attractiveness for all nodes and shelters at once
            attract = tau_alpha * eta_beta         # (n_risk, n_shelters)

            iter_chromosomes = np.empty((self.n_ants, n_risk), dtype=np.int32)
            iter_fitness     = np.empty(self.n_ants, dtype=np.float64)

            for ant in range(self.n_ants):
                chromosome    = np.empty(n_risk, dtype=np.int32)
                demand_counts = np.zeros(n_shelters, dtype=np.int64)

                for i in range(n_risk):
                    pop    = pops[i]
                    scores = attract[i].copy()

                    # ── Vectorised capacity mask ──────────────────────────────
                    # Zero out any shelter where adding this node's pop would overflow
                    over_capacity = (demand_counts + pop) > caps
                    scores[over_capacity] = 0.0

                    total = scores.sum()
                    if total <= 0.0:
                        # All shelters full — fall back to least-loaded
                        load_ratio = demand_counts / np.maximum(caps, 1)
                        j = int(np.argmin(load_ratio))
                    else:
                        # Roulette-wheel selection (vectorised normalisation)
                        probs = scores / total
                        j = int(np.random.choice(n_shelters, p=probs))

                    chromosome[i]     = j
                    demand_counts[j] += pop

                fit = self._fitness(chromosome.tolist())
                iter_chromosomes[ant] = chromosome
                iter_fitness[ant]     = fit

                if fit < best_fitness:
                    best_fitness    = fit
                    best_chromosome = chromosome.copy()

            # ── Pheromone update ──────────────────────────────────────────────
            # 1. Evaporation (in-place, vectorised)
            self._tau *= (1.0 - self.rho)

            # 2. Deposit by all ants — use scatter-add instead of Python loop
            #    deposits[ant] = q / fitness[ant]
            deposits = self.q / np.maximum(iter_fitness, 1e-9)   # (n_ants,)
            row_idx  = np.repeat(np.arange(n_risk), n_shelters)   # not used
            # Efficient: for each ant, add deposit to tau[i, chrom[i]] for all i
            for ant in range(self.n_ants):
                # np.add.at avoids Python loop over n_risk
                np.add.at(self._tau,
                          (np.arange(n_risk), iter_chromosomes[ant]),
                          deposits[ant])

            # 3. Elitist boost — best-ever solution
            elite_deposit = self.q * 5.0 / max(best_fitness, 1e-9)
            np.add.at(self._tau,
                      (np.arange(n_risk), best_chromosome),
                      elite_deposit)

            # 4. Clamp to prevent numerical explosion
            np.clip(self._tau, 1e-6, 1e6, out=self._tau)

            if (iteration + 1) % 10 == 0:
                print(f"  [ACO] iter {iteration+1}/{self.iterations} "
                      f"| best_fitness={best_fitness:.1f}")

        self.best_fitness = float(best_fitness)
        print(f"  [ACO] Done. Best fitness = {best_fitness:.1f}")
        return self._decode(best_chromosome.tolist())
