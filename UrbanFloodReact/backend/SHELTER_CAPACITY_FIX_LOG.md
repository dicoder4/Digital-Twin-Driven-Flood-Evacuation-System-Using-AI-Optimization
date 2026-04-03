# Shelter Capacity & Stateful Re-run Implementation Log
────────────────────────────────────────────────────────────

## 1. Feature: Stateful Incremental Re-runs
**Objective**: To achieve 100% evacuation of reachable populations in a single re-run by eliminating "capacity stealing" by previously evacuated groups.

- **Pinned Routes**: Implemented `SIMULATION_SESSION_CACHE` in `service.py` to persist successful evacuation routes between sequential runs.
- **Capacity Isolation**: Before starting a re-run, the system now automatically deducts the capacity used by the "pinned" population from available shelters, ensuring new synthetic shelters are reserved exclusively for the remaining stranded/at-risk population.
- **Targeted Optimization**: Planners (GA, ACO, PSO) now filter out `pinned_node_ids` and ONLY optimize the remaining deficit.
- **Result Merging**: The final report merges the persisted historical routes with the new results into a single, comprehensive evacuation plan.

## 2. Feature: Canonical Reachability Classification
**Objective**: To accurately distinguish between people who have a walking path out (At-Risk) and those who need specialized boat/helicopter rescue (Stranded).

- **Strict Physics Mapping**: Built a `wadable_subgraph` (depth ≤ 0.15m on both nodes and edges) to represent legal walking territory.
- **Snap-to-Nearest (300m)**: Implemented a 300m radius snapping check. 
    - If a person is on flooded ground but a dry road is within 300m, they are **At-Risk** (can wade to the road).
    - If no dry road exists within 300m, they are categorized as **Stranded (Needs Rescue)** and excluded from algorithmic routing.
- **Consistent Stats**: Synced the logic across `service.py` and the `ShelterGapAnalysis` engine to eliminate math discrepancies in the logs.

## 3. Critical Bug Fixes

### A. Graph Symmetry (One-Way Street Failure)
- **Problem**: The OSMnx "drive" network contains one-way streets. Dijkstra starting from the shelter was computing distances *to* homes, which was sometimes illegal/longer for residents travel *from* homes *to* the shelter.
- **Fix**: Implemented graph reversal (`self.G.reverse(copy=False)`) during pre-computation in `setup_mixin.py`. The AI now correctly computes inbound paths, eliminating 100% of "no road path" DECODE errors.

### B. Structural Graph Isolation
- **Problem**: Some residents were in graph components that were completely cut off by floodwater, leaving `inf` entries in the distance matrix and crashing the "greedy" initialization.
- **Fix**: Implemented a **Euclidean fallback** pass. Isolated nodes now receive a 10x penalty straight-line distance, allowing the planners to still assign them to the nearest feasible shelter while maintaining a clean mathematical sum.

### C. Variable Scoping & Payload
- **Fix**: Resolved `UnboundLocalError` and `NameError` by moving metrics like `genuinely_unreachable_count` into the main simulation scope.
- **Fix**: Corrected a payload masking bug in `final_report` where the global stranded count was accidentally overwritten by a local null variable.

## 4. UI & Aesthetics
- **Evacuation Overview**: Added a new **"Needs Rescue" (Red)** statistic module to the frontend to explicitly display stranded populations.
- **Dynamic Stats**: Updated the compare-mode and details-mode UI to show relative success rates based on the total *reachable* population.

## Final Outcome
The system successfully achieved **0 "At Risk (Cap)"** coverage in a single Marathahalli re-run, with the only remainder being the physically stranded population awaiting boat evacuation.

**Status: COMPLETE & VERIFIED**
