"""
pso/core.py
───────────
Particle Swarm Optimisation for flood evacuation routing.
(Fully vectorised — velocity/position updates use NumPy arrays)

How it works
────────────
PSO models a swarm of "particles", each representing a complete assignment
solution (chromosome = array[int] where chromosome[i] = shelter index for
at-risk node i).

Discrete adaptation
───────────────────
Standard PSO operates on continuous vectors.  For this discrete assignment
problem we use a *sigmoid velocity + probabilistic update* approach:

    v[i,d]  ←  w*v[i,d]  +  c1*r1*(pbest[i,d]-x[i,d])
                            +  c2*r2*(gbest[d]  -x[i,d])

where v represents continuous "pressure toward a shelter":

    P(update x[i,d])  =  sigmoid(|v[i,d]|)

If a particle is updating gene d, the new shelter index is chosen from:
    - pbest[d] with prob proportional to c1
    - gbest[d] with prob proportional to c2
    - otherwise: nearest-shelter (distance-biased, like GA mutation)

This keeps PSO discrete and problem-aware.

Performance notes
─────────────────
Velocity and position updates are fully vectorised across the n_risk
dimension using NumPy — no inner Python loop over genes per particle.
"""

import numpy as np
from base_planner import BaseEvacuationPlanner


class PSOEvacuationPlanner(BaseEvacuationPlanner):
    """
    Particle Swarm Optimisation evacuation planner.
    Drop-in replacement for GeneticEvacuationPlanner.
    """

    def __init__(self, at_risk_nodes, safe_shelters, G,
                 n_particles: int = 40,
                 iterations: int  = 60,
                 w: float         = 0.7,
                 c1: float        = 1.5,
                 c2: float        = 2.0,
                 v_max: float     = 4.0,
                 use_tomtom_traffic: bool = False,
                 **kwargs):

        super().__init__(at_risk_nodes, safe_shelters, G,
                         use_tomtom_traffic=use_tomtom_traffic)

        self.n_particles = n_particles
        self.iterations  = iterations
        self.w           = w
        self.c1          = c1
        self.c2          = c2
        self.v_max       = v_max

        # Pre-compute nearest-shelter lookup for mutation fallback
        # nearest_shelter[i] = shelter index closest to at-risk node i
        self._nearest_shelter = np.argmin(self.dist_matrix, axis=1).astype(np.int32)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _init_particle(self, n_risk: int) -> np.ndarray:
        """Greedy chromosome ± 15% random perturbation → numpy int array."""
        chrom = np.array(self._greedy_chromosome, dtype=np.int32)
        mask  = np.random.random(n_risk) < 0.15
        if mask.any():
            # For perturbed genes, pick from the nearest 3 shelters
            for i in np.where(mask)[0]:
                nearest3   = np.argsort(self.dist_matrix[i])[:3]
                chrom[i]   = int(np.random.choice(nearest3))
        return chrom

    @staticmethod
    def _sigmoid_arr(v: np.ndarray) -> np.ndarray:
        """Element-wise sigmoid: P(update) = 1/(1+exp(-|v|)), vectorised."""
        return 1.0 / (1.0 + np.exp(-np.abs(v)))

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        if not self.at_risk_nodes or not self.safe_shelters:
            self.best_fitness = 0.0
            return []

        n_risk     = len(self.at_risk_nodes)
        n_shelters = len(self.safe_shelters)

        # ── Initialise swarm ── (n_particles × n_risk NumPy arrays) ──────────
        positions  = np.stack([self._init_particle(n_risk)
                                for _ in range(self.n_particles)])           # (P, R)
        velocities = np.random.uniform(-1.0, 1.0,
                                        size=(self.n_particles, n_risk))     # (P, R)

        pbest         = positions.copy()
        pbest_fitness = np.array([self._fitness(p.tolist()) for p in pbest],
                                  dtype=np.float64)

        gbest_idx     = int(np.argmin(pbest_fitness))
        gbest         = pbest[gbest_idx].copy()
        gbest_fitness = float(pbest_fitness[gbest_idx])

        print(f"  [PSO] Init best fitness = {gbest_fitness:.1f}")

        c_total = self.c1 + self.c2
        p_pbest = self.c1 / c_total   # prob of pulling toward pbest

        for iteration in range(self.iterations):
            # ── Vectorised velocity update ────────────────────────────────────
            r1 = np.random.random((self.n_particles, n_risk))
            r2 = np.random.random((self.n_particles, n_risk))

            velocities = (self.w  * velocities
                          + self.c1 * r1 * (pbest      - positions)   # (P, R)
                          + self.c2 * r2 * (gbest[None] - positions))  # broadcast

            np.clip(velocities, -self.v_max, self.v_max, out=velocities)

            # ── Vectorised position update ────────────────────────────────────
            # Decide which genes update (sigmoid probability)
            update_mask = np.random.random((self.n_particles, n_risk)) \
                          < self._sigmoid_arr(velocities)               # (P, R) bool

            # For updated genes: randomly pull toward pbest or gbest
            pull_pbest = np.random.random((self.n_particles, n_risk)) < p_pbest

            new_positions = positions.copy()
            # Pull toward pbest
            pbest_pull = update_mask &  pull_pbest
            if pbest_pull.any():
                new_positions[pbest_pull] = pbest[pbest_pull]
            # Pull toward gbest
            gbest_pull = update_mask & ~pull_pbest
            if gbest_pull.any():
                # gbest is 1-D — broadcast across particles
                gbest_2d = np.broadcast_to(gbest[None], positions.shape)
                new_positions[gbest_pull] = gbest_2d[gbest_pull]

            positions = new_positions

            # ── Fitness evaluation ────────────────────────────────────────────
            for p_idx in range(self.n_particles):
                fit = self._fitness(positions[p_idx].tolist())
                if fit < pbest_fitness[p_idx]:
                    pbest[p_idx]         = positions[p_idx].copy()
                    pbest_fitness[p_idx] = fit
                    if fit < gbest_fitness:
                        gbest         = positions[p_idx].copy()
                        gbest_fitness = fit

            if (iteration + 1) % 10 == 0:
                print(f"  [PSO] iter {iteration+1}/{self.iterations} "
                      f"| gbest_fitness={gbest_fitness:.1f}")

        self.best_fitness = float(gbest_fitness)
        print(f"  [PSO] Done. Best fitness = {gbest_fitness:.1f}")
        return self._decode(gbest.tolist())
