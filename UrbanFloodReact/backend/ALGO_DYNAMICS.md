# Evacuation Algorithm Audit: GA/PSO vs. ACO Dynamics

This document analyzes the current divergence in evacuation performance observed within the Urban Flood Digital Twin, specifically addressing why **ACO (Ant Colony)** typically achieves higher success rates than **GA (Genetic)** and **PSO (Particle Swarm)** under heavy flood conditions.

## 1. The "Success Gap" (The Lifeboat Problem)

In high-intensity simulations (e.g., 100mm rainfall), the number of at-risk evacuees often exceeds the total physical capacity of safe shelters. This exposes a fundamental difference in how each algorithm handles "full" buildings.

### GA & PSO (The "Rule-Followers")
*   **Behavior**: These algorithms rely on a **Strict Greedy Seed**. During initialization, if a person tries to enter a shelter and its capacity is already 100% full, the person is assigned a `-1` (Unassigned) flag.
*   **Optimization Strategy**: Because our fitness function carries a massive **Capacity Penalty**, the GA/PSO search processes often "conclude" that leaving a person in the flood (a fixed penalty) is mathematically better than overstuffing a shelter (which carries a quadratic, exploding penalty).
*   **Result**: 30–50% success rates. The algorithms report "I followed your rules, so I cannot fit these people."

### ACO (The "First Responder")
*   **Behavior**: ACO uses **Probabilistic Path Construction**. If an "ant" is building a route and discovers that *every* shelter is full, it triggers a **Least-Loaded Fallback**. Instead of giving up, it forces the person into the building that is currently the least "overstuffed" by ratio.
*   **Optimization Strategy**: ACO assumes that **any shelter is better than the water**. It builds a complete solution first, then tries to optimize the pheromone trails to balance the loads.
*   **Result**: 95–100% success rates. The algorithm reports "I found a home for everyone, but some schools are now at 300% capacity."

---

## 2. Comparative Analysis of Techniques

| Feature | Genetic Algorithm (GA) | Particle Swarm (PSO) | Ant Colony (ACO) |
| :--- | :--- | :--- | :--- |
| **Philosophy** | "Survival of the Fittest" | "The Wisdom of the Crowd" | "Social Cooperation" |
| **Logic** | Mutation & Crossover of existing plans. | Particles move toward Global/Personal bests. | Ants leave pheromone trails on good routes. |
| **Constraint Handling** | **Discrete/Rigid**. Harder to recover from an initial `-1` (unassigned) state. | **Velocity-Based**. If the "Best" is unassigned, everyone moves toward being unassigned. | **Constructive**. Every "ant" must build a full plan every time—no one is left behind. |
| **Best For...** | Long-term planning, small-to-medium datasets. | Rapid, continuous optimization (flight paths, etc). | **Dynamic Routing** & Network Flow (like floods). |

---

## 3. The "Unreachable" vs. "Unassigned" Distinction

It is critical to distinguish between these two "failure" states:

1.  **Unreachable (Physics-Limited)**: No road exists between the person and the shelter because of deep water (>0.5m). This is a **valid result** of the flood model.
2.  **Unassigned (Capacity-Limited)**: A safe road exists, but the buildings are full. This is currently what is dragging down the GA/PSO success rates.

---

## 4. Proposed Technical Alignment

To ensure a fair comparison and better utility for researchers, we recommend updating the **Base Planner** logic (used by GA/PSO) to match the ACO's **"Solution-Oriented"** approach.

> [!TIP]
> **Conclusion**: By forcing GA and PSO to assign people to the "Least-Bad" shelter instead of giving up, we can turn the "Success Rate" into a pure metric of **Road Accessibility**, and use the "Occupancy Bars" to measure **Infrastructure Sufficiency**.

*Standardizing these rules would make the Digital Twin prioritize human life over strict occupancy limits.*
