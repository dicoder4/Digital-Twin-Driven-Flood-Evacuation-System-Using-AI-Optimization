# 🔬 Algorithm Analysis Mode — Technical Documentation

## Overview

The **Algorithm Analysis Mode** is a deep-dive benchmarking tool that runs three metaheuristic optimisation algorithms — **Genetic Algorithm (GA)**, **Ant Colony Optimisation (ACO)**, and **Particle Swarm Optimisation (PSO)** — on the same flood evacuation scenario multiple times, measuring their fitness quality, stability, convergence behaviour, and path diversity. Results are streamed progressively to the frontend.

---

## Architecture

### Execution Flow

```
User clicks "Analyse Algorithm Performance"
                │
                ▼
    ┌──────────────────────────┐
    │  1. Flood Simulation     │  ← Progressive or Instant (configurable)
    │     propagate N steps    │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │  2. Shared Dijkstra      │  ← ONE precompute, shared across all runs
    │     dist_matrix,         │
    │     time_matrix,         │
    │     greedy_chromosome    │
    └──────────┬───────────────┘
               │
    ┌──────────┴───────────────┐
    │  3. Per-Algorithm Loop   │
    │                          │
    │  for algo in [GA,ACO,PSO]:
    │    → yield progress SSE  │
    │    → run 3 stability     │  ← Sequential in background thread
    │      runs with ±5% noise │
    │    → aggregate metrics   │
    │    → yield algo_result   │  ← UI card appears immediately
    │                          │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │  4. Final Payload        │  ← analysis_done with all metrics
    └──────────────────────────┘
```

### Key Design Decisions

1. **Shared Setup Pattern** — Dijkstra precomputation and optional TomTom traffic fetch happen **once** via the first GA instance. All subsequent runs receive `shared_setup=ga_instance`, copying `dist_matrix`, `time_matrix`, and the greedy chromosome via `copy.deepcopy`. This avoids 9× redundant Dijkstra computations.

2. **±5% Noise Perturbation** — Each of the 9 runs (3 algos × 3 runs) gets a unique Gaussian noise applied to `dist_matrix` (σ=5%, capped ±10%) and `time_matrix` (σ=3%, capped ±7%). This simulates real-world uncertainty in flood depth measurements and forces each run to start from a differently-perturbed greedy chromosome, producing meaningful variance.

3. **Progressive Streaming** — Results stream per-algorithm via SSE (Server-Sent Events). The popup opens after GA finishes (~⅓ of total time); ACO and PSO cards fill in progressively with loading skeletons shown for pending algorithms.

---

## Configuration

### Flood Simulation Mode (service.py, line ~1703)

The analysis mode supports two flood initialization strategies. This is configured on **line 1703** of `service.py` inside `run_advanced_analysis_generator()`:

#### Progressive Mode (Current — Recommended)
```python
sim.set_progressive_rainfall(rainfall_mm, 5)   # line 1703
```
Rainfall is distributed incrementally over 5 sub-steps during each flood propagation step. Each call to `propagate_flood_step()` adds `rainfall_mm / 5 / 1000` metres of water to every node, then propagates hydraulically. This produces a **more realistic flood pattern** — water accumulates gradually, allowing natural drainage and elevation-based flow.

#### Instant Mode (Alternative — Faster)
```python
sim.initialize_from_drains(rainfall_mm)         # replace line 1703
```
All rainfall is dumped at drain and lake nodes instantly. This is faster but produces a "flash flood" pattern where drain nodes get massive water depth immediately. Less realistic for moderate rainfall scenarios.

**Trade-off:** Progressive mode produces more nuanced at-risk node distributions (some nodes flood later than others), which gives the algorithms a more interesting problem to solve. Instant mode floods everything at once, which tends to make the greedy solution harder to beat.

### Analysis Steps (service.py, line ~1718)

```python
analysis_steps = max(5, steps // 2)
```

The analysis uses **half** the user's simulation steps (minimum 5) for flood propagation. This balances realism with speed. To change:
- **Faster analysis:** `analysis_steps = max(3, steps // 3)`
- **More accurate:** `analysis_steps = steps` (uses full step count, slower)

### Stability Runs (service.py, line ~1754)

```python
n_runs = 3
```

Each algorithm runs **3 times** with different distance perturbations. Increasing to 5 gives better statistical confidence but takes ~67% longer. For demos, 3 is sufficient.

---

## Metrics Explained

### 1. Mean Fitness (↓ Lower = Better)
The average best fitness across 3 runs. The fitness function is:

```
fitness = Σ (flood_weighted_distance × population)
        + 0.5 × Σ (travel_time × population)
        + 100,000 × Σ (capacity_overflow²)
        + terrain_penalty
        + 1,000,000 × unassigned_population   ← applied by all three algorithms
```

The unassigned-node penalty is enforced by all three planners — leaving a group unrouted is treated as equivalent to 1000 km of walking per person, ensuring algorithms never gain fitness by abandoning people.

Fitness values in the **millions are normal** — they represent the cumulative cost across all at-risk nodes. A 1-2% difference between algorithms translates to thousands of people walking shorter/longer distances.

### 2. Standard Deviation (Std Dev)
Variance across 3 runs. Lower = more predictable. For real-time disaster response, predictability matters — you can't afford a "bad run."

### 3. Stochastic Stability (↑ Higher = Better)
```
stability = 1 - (std_dev / mean_fitness)
```
- **>99%**: Very stable — algorithm gives consistent results across different distance perturbations
- **95-99%**: Moderately stable
- **<95%**: Sensitive to initial conditions

**Caveat:** Stability = 100.0% exactly may indicate the algorithm is **stuck on the greedy seed** and failed to explore beyond it. This is different from "perfect consistency."

### 4. Convergence Speed (↓ Lower = Faster)
The iteration at which 95% of the total improvement was achieved.
- **Value = 1**: Algorithm never improved beyond its starting greedy solution. It "converged immediately" — which actually means it failed to explore.
- **Value = 5-15**: Healthy convergence — the algorithm found improvements over the first 5-15 iterations.
- **Value = 30+**: Slow convergence — the algorithm is still improving at the end, suggesting more iterations would help.

### 5. Path Diversity (↑ Higher = Better)
Fraction of unique (origin → shelter) assignments out of total assignments. Higher diversity means evacuees are spread across more shelters, reducing road congestion.
- **>30%**: Good diversity
- **20-30%**: Moderate — some road congestion likely
- **<20%**: Most people funnelled to the same few shelters

---

## Algorithm Comparison

### Genetic Algorithm (GA)

| Aspect | Detail |
|--------|--------|
| **Mechanism** | Crossover (two-point) + mutation (nearest-3 shelter swap) + elitism |
| **Population Init** | 80% greedy-seeded (15% perturbation), 20% random |
| **Constraint Handling** | Capacity repair ensures every chromosome is feasible |
| **Parameters** | `pop_size=30-60`, `generations=30-60`, `mutation_rate=0.15`, `elite=10%` |

**Strengths:**
- Most diverse solutions (highest path diversity) — crossover creates novel assignment combinations
- Capacity repair means every solution is feasible (no overflow penalties)
- Robust across different problem sizes

**Weaknesses:**
- Crossover can disrupt good sub-routes — if Person A's assignment is optimal, crossover might swap it with Person B's worse assignment
- Tends to have the **highest fitness** (worst route quality) because random crossover breaks the greedy's carefully constructed assignments without always finding better alternatives within the iteration budget

### Ant Colony Optimisation (ACO)

| Aspect | Detail |
|--------|--------|
| **Mechanism** | Ants construct solutions using pheromone × distance heuristic |
| **Pheromone** | Evaporation ρ=0.1, reinforcement on best solution |
| **Warm Start** | Greedy solution as initial best (pheromone seeded) |
| **Constraint Handling** | Capacity masking during construction + post-construction capacity repair |
| **Parameters** | `n_ants=30-60`, `iterations=30-60`, `alpha=1`, `beta=3` |

**Strengths:**
- **Naturally suited to graph routing** — designed for shortest-path-on-graph problems (TSP, VRP)
- Typically achieves the **lowest fitness** (best route quality) because the pheromone-distance heuristic directly optimises for shortest weighted paths
- High stability — pheromone reinforcement is deterministic
- Double-layer capacity enforcement: masking prevents overflow during construction; repair catches the rare fallback case

**Weaknesses:**
- **Needs 100+ iterations** to build meaningful pheromone differentiation. With only 30-60 iterations, ACO often can't improve beyond its greedy seed (convergence_speed=1)
- Lower diversity — pheromone reinforcement funnels all ants toward the same "best path"

### Particle Swarm Optimisation (PSO)

| Aspect | Detail |
|--------|--------|
| **Mechanism** | Discrete adaptation with sigmoid velocity, pbest/gbest attraction |
| **Velocity** | Inertia w=0.7, cognitive c₁=1.5, social c₂=2.0 |
| **Init** | 80% greedy-seeded (±15% perturbation), 20% fully random capacity-aware |
| **Constraint Handling** | Post-update capacity repair on every particle each iteration |
| **Parameters** | `n_particles=30-60`, `iterations=30-60` |

**Strengths:**
- **Fastest convergent** — finds improvements quickly (convergence_speed of 5-10 is typical)
- The **only algorithm that consistently shows a visible convergence curve** — PSO starts high and slopes downward, demonstrating active optimisation
- Good balance between exploration (high inertia early) and exploitation (swarm collapse later)
- Mixed initialisation ensures genuine explorers exist from the start, reducing premature convergence

**Weaknesses:**
- **Designed for continuous spaces** — the sigmoid-based discrete adaptation is a mathematical compromise, not a native discrete operator
- Can plateau if gbest dominates social pull before the swarm has explored widely
- Middle-of-the-road fitness — better than GA but usually worse than ACO on raw route quality

---

## 🏆 Best Algorithm Recommendation

### For Real-World Flood Evacuation Deployment: **ACO**

**Rationale:** The evacuation problem is fundamentally a **graph-based assignment and routing problem** — "assign N people to M shelters via shortest flood-weighted paths on a road network." This is precisely the class of problems ACO was invented for (Travelling Salesman, Vehicle Routing). ACO's pheromone × distance heuristic directly optimises for what matters: the shortest safe path on the actual road graph.

In empirical testing, ACO consistently achieves the **lowest fitness** (best total evacuation distance). For a disaster response agency (DRA), the quality of the final plan matters most — every meter of unnecessary walking distance is risk exposure for evacuees.

### For Time-Critical Re-Planning: **PSO**

If the DRA needs to **re-run the algorithm in real-time** (e.g., a new road floods, shelter capacity changes), PSO is the best choice. It converges the fastest — reaching 95% of its best solution within 5-10 iterations. This means it can produce a "good enough" plan in seconds, even if the absolute quality is slightly worse than ACO.

### For Maximum Solution Diversity: **GA**

If the DRA wants to see **multiple different evacuation strategies** (e.g., "what if we route people to different shelters?"), GA produces the most diverse set of solutions. This is useful for planning contingencies — "Plan A sends people north, Plan B sends people west."

### Summary Ranking

| Rank | Algorithm | Best For | Key Metric |
|------|-----------|----------|------------|
| 🥇 | **ACO** | Route quality (lowest fitness) | Mean Fitness ↓ |
| 🥈 | **PSO** | Speed of convergence + active optimisation | Convergence Speed ↓ |
| 🥉 | **GA** | Solution diversity | Path Diversity ↑ |

> All three algorithms now enforce capacity feasibility equally — GA via crossover/mutation repair, ACO via construction masking + post-repair, PSO via post-update repair. Capacity feasibility is no longer a differentiator between algorithms.

### Important Caveat

With the current iteration budget (30-60 iterations), **ACO is operating below its optimal range**. ACO's pheromone mechanism requires 100+ iterations to build trails that meaningfully diverge from the greedy seed. If iterations are increased to 100+, ACO's advantage over PSO and GA would become significantly more pronounced.

Conversely, **GA's ranking might improve** with higher mutation rates (currently 0.15) or tournament selection instead of elite-based selection. The current configuration favours stability over exploration.

---

## Files Involved

| File | Role |
|------|------|
| `backend/service.py` | Analysis generator (`run_advanced_analysis_generator`) — flood sim, shared setup, per-algo loop |
| `backend/base_planner.py` | Shared fitness function, dist/time matrices, greedy chromosome |
| `backend/genetic_algorithm/core.py` | GA planner (crossover, mutation, elitism) |
| `backend/genetic_algorithm/evolution_mixin.py` | GA evolution logic (population init, selection, crossover, mutation) |
| `backend/aco/core.py` | ACO planner (pheromone, ant construction) |
| `backend/pso/core.py` | PSO planner (velocity, pbest/gbest) |
| `backend/flood_simulator.py` | Flood propagation engine (progressive/instant rainfall) |
| `backend/genai/expert_panel.py` | Research Planner AI prompt (`algo_analyst` persona) |
| `frontend/src/components/EvacuationPanel.jsx` | Analysis trigger button, SSE handler, progress state |
| `frontend/src/components/AlgoAnalysisPopup.jsx` | Analysis popup UI (dashboard, convergence chart, breakdown, AI tab) |

---

## Convergence Chart Interpretation

The convergence chart shows the **averaged best fitness** across 3 runs per algorithm at each iteration:

- **Flat line at low Y**: Algorithm is stuck on its greedy seed (common for ACO with low iterations)
- **Downward slope**: Algorithm is actively improving — this is healthy optimisation
- **Sharp early drop then plateau**: Algorithm converged quickly (typical of PSO)
- **Gradual continuous descent**: Algorithm explores steadily (typical of GA with high mutation)

The Y-axis is **auto-scaled** to the data range (not starting from 0) so small differences between algorithms are visible. Values in the tooltip are formatted as comma-separated integers.

---

*Last updated: April 2026 — capacity repair unified across all three planners; PSO swarm diversity improved (80/20 greedy/random init); unassigned-node penalty bug fixed in shared fitness function*
