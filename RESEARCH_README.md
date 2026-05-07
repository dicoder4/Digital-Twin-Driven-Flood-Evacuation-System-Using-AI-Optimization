# Digital-Twin-Driven Flood Evacuation System Using AI Optimization
## Research Reference Document

**Institution:** M.S. Ramaiah Institute of Technology, Bengaluru (Autonomous, Affiliated to VTU)  
**Course:** CSP81 — Project Work, Feb–June 2025  
**Guide:** Dr. Mallegowda M.  
**Authors:** Aditri B Ray (1MS22CS011), Anisha Ajit (1MS22CS028), Diya D Shah (1MS22CS051)

---

## 1. Abstract

This project presents a **Digital Twin–Driven Flood Evacuation System** that integrates physics-based urban flood simulation with three metaheuristic AI optimization algorithms — Genetic Algorithm (GA), Ant Colony Optimization (ACO), and Particle Swarm Optimization (PSO) — alongside a Generative AI (GenAI) decision-support layer. The system builds an OpenStreetMap-derived road network graph of Bengaluru's administrative sub-regions (Hoblis), simulates dynamic flood propagation using terrain elevation data, incorporates real-time TomTom traffic congestion, and computes optimized evacuation routes to safe shelters. A dual FastMCP architecture grounds a large language model (Gemini/Groq/Ollama) to live simulation state, enabling autonomous agentic disaster planning. The system is deployed as a full-stack web application: FastAPI (Python) backend with Server-Sent Events (SSE) streaming, React 19 frontend with MapLibre GL visualization.

---

## 2. Problem Statement & Motivation

Urban flooding caused by climate variability and rapid urbanization results in significant loss of life and infrastructure damage. Traditional evacuation planning is static and fails to account for real-time environmental changes — rainfall intensity, terrain-dependent water spread, and road congestion. Bengaluru, India's third-largest city, is particularly vulnerable: flash floods in 2022 caused damages exceeding ₹225 crore. Existing literature identifies five key research gaps:

1. **Prediction–Action Disconnect:** Flood prediction systems rarely connect directly to evacuation routing engines.
2. **Limited Multi-Algorithm Benchmarking:** Most digital twin platforms use a single routing strategy.
3. **Computational Scalability Gap:** High-fidelity models (DRL, hydrodynamic solvers) are too slow for real-time use.
4. **Lack of Generative AI Explanation:** No existing system explains routing decisions in natural language grounded to live simulation state.
5. **No Unified Congestion-Aware Architecture:** Congestion modeling and evacuation optimization are rarely co-located.

This system addresses all five gaps within a single, lightweight, deployable platform.

---

## 3. System Architecture

### 3.1 Overall Design

The system uses a **microservices-inspired layered architecture** decoupling computation from visualization:

```
User
 └─ React 19 Dashboard (MapLibre GL, Vite, Tailwind CSS 4)
       ↕ REST (Axios) + SSE (EventSource)
 └─ FastAPI Server (Python 3.10+, Uvicorn ASGI)
       ├─ Flood Simulation Engine      (flood_simulator.py)
       ├─ Population Integrator        (service.py)
       ├─ AI Optimization Layer        (GA / ACO / PSO via base_planner.py)
       ├─ GenAI Agentic Pipeline       (genai/)
       ├─ Network Model                (OSMnx graph builder)
       └─ Data & External Layer
             ├─ MongoDB Atlas          (users, rainfall, population, metro, buses, resources)
             ├─ OpenStreetMap API      (road network geometry)
             └─ TomTom Traffic API     (real-time congestion)
```

### 3.2 Communication Protocol

- **REST (HTTPS):** Region initialization (`GET /load-region`), algorithm invocation (`POST /optimize-evacuation`), GenAI queries.
- **Server-Sent Events (SSE):** One-directional server→client stream delivering flood state as GeoJSON FeatureCollections on every simulation step. The frontend updates flood polygons, shelter states, and road risk colors without polling.
- **Sentinel Bridge (`mcp_state.json`):** A shared JSON file updated every simulation frame. The GenAI layer reads this file rather than hallucinating simulation state — this is the core grounding mechanism.

### 3.3 Backend File Structure

```
backend/
├── main.py                          # FastAPI app, all route definitions
├── service.py                       # GlobalState, simulation orchestration, algorithm dispatch
├── flood_simulator.py               # Hydrodynamic flood engine
├── base_planner.py                  # Shared parent class for GA/ACO/PSO
├── genetic_algorithm/
│   ├── core.py                      # GeneticEvacuationPlanner
│   ├── setup_mixin.py               # TomTom fetch, Dijkstra precompute
│   ├── evolution_mixin.py           # Selection, crossover, mutation, elitism
│   └── geometry_mixin.py            # Chromosome → GeoJSON path decoder
├── aco/
│   └── core.py                      # ACOEvacuationPlanner (vectorised NumPy)
├── pso/
│   └── core.py                      # PSOEvacuationPlanner (vectorised NumPy)
├── genai/
│   ├── app_copilot.py               # Dashboard AI Copilot (agentic loop)
│   ├── evacuation_chat.py           # Post-simulation Q&A
│   ├── expert_panel.py              # Multi-persona panel (Logistics Chief, Tactical Commander)
│   ├── mcp_evacuation_server.py     # FastMCP server — Hard Data (physics engine)
│   ├── mcp_flood_intelligence_server.py  # FastMCP server — Soft Data (logistics, metro)
│   └── context_builder.py           # Simulation state → structured LLM prompt
├── traffic_data/
│   └── tomtom.py                    # Parallel TomTom bulk fetcher (ThreadPoolExecutor)
├── coord_loader.py                  # MongoDB → Hobli coordinates
├── shelter_generator.py             # OSM shelter extraction + capacity assignment
├── gis_terrain_loader.py            # DEM raster → elevation matrix (Rasterio)
├── rainfall_loader.py               # Historical rainfall data injection
└── .env                             # GEMINI_API_KEY, GROQ_API_KEY, TOMTOM_API_KEY, MONGO_URI
```

### 3.4 Frontend File Structure

```
frontend/src/
├── App.jsx                          # Root orchestrator, global state
├── hooks/
│   └── useSimulation.js             # SSE lifecycle, event routing
└── components/
    ├── FloodMap.jsx                  # MapLibre GL map, all layer composition
    ├── ShelterLayer.jsx              # Shelter icons + flood-state detection (ray casting)
    ├── EvacuationLayer.jsx           # Route polylines + citizen pins
    ├── TrafficLayer.jsx              # TomTom congestion color overlay
    ├── SimulationControls.jsx        # Rainfall slider, historical date picker
    ├── EvacuationPanel.jsx           # Algorithm stats, comparison table, shelter list
    ├── AlgoAnalysisPopup.jsx         # Deep benchmarking UI (convergence chart, metrics)
    ├── AppCopilot.jsx                # GenAI Co-Pilot chat interface
    └── EvacuationChat.jsx            # Post-sim natural language Q&A
```

---

## 4. Digital Twin Construction

### 4.1 Road Network (OSMnx + NetworkX)

For each Hobli (lowest administrative unit in Karnataka), the system:
1. Queries OpenStreetMap via `osmnx.graph_from_point()` with a 3 km radius, `network_type='drive'`.
2. Constructs a **directed multigraph** `G` where:
   - **Nodes** = road intersections with attributes: `(lat, lon, elevation, water_depth, population)`
   - **Edges** = road segments with attributes: `(length_m, road_type, speed_kph, flood_weight, traffic_time)`
3. Caches the graph as `.graphml` on disk to avoid re-fetching (typical graph: 800–3,000 nodes, 2,000–8,000 edges for an urban Hobli).

### 4.2 Elevation Data (Rasterio + SRTM DEM)

The module `gis_terrain_loader.py` uses **Rasterio** to:
- Load SRTM 30m-resolution Digital Elevation Model tiles covering the Hobli bounding box.
- Sample elevation at each node's `(lat, lon)` coordinate using bilinear interpolation.
- Assign `node['elevation']` in metres above sea level.

Elevation is the primary input to the hydrodynamic flood propagation model.

### 4.3 Population Integration

Ward-level population data from the **2011 Bengaluru BBMP Census** (with an assumed 15% growth projection) is mapped onto road nodes via a **Two-Pass Matching** algorithm:
1. **Pass 1 (Direct):** Match Hobli name to BBMP ward name.
2. **Pass 2 (Fallback):** If no direct match, aggregate all wards in the same Taluk (Assembly Constituency) and distribute proportionally across unmatched Hoblis.

Population is then distributed proportionally across road nodes weighted by node degree (high-connectivity intersections represent denser areas).

### 4.4 Shelter Identification

`shelter_generator.py` uses `osmnx.features_from_point()` to extract OSM POIs tagged as: `amenity=school`, `amenity=hospital`, `amenity=community_centre`, `amenity=town_hall`, `amenity=police`, `amenity=fire_station`, `building=public`.

Each shelter is:
- Snapped to the nearest road node via `osmnx.nearest_nodes()`.
- Assigned a **rule-based capacity**: School → 500, Hospital → 200, Community Centre → 300, Town Hall → 400, Police/Fire Station → 100, Public Building → 150.
- **Fallback:** If OSM returns < 2 results, 6 synthetic shelters are placed at the highest-degree (most connected) road nodes.

**Real-time flood state:** The React frontend performs **point-in-polygon ray-casting** against the live flood GeoJSON on every SSE frame. Shelters inside the flood zone flip from green to red without any extra API calls.

---

## 5. Flood Simulation Engine

**File:** `backend/flood_simulator.py`  
**Class:** `UrbanFloodSimulator`

### 5.1 Initialization

Water is injected at two node types identified via OSM tags:
- **Drain nodes:** `amenity=drain`, `waterway=drain`, `waterway=ditch`
- **Lake nodes:** `natural=water`, `water=lake`, `water=reservoir`

Initial water depth at source nodes:

```
water_depth[v] = rainfall_mm / 1000   (metres)
```

### 5.2 Progressive Flood Mode (Default)

Rainfall is distributed incrementally across simulation steps. Each call to `propagate_flood_step()` first adds:

```
Δdepth = rainfall_mm / n_steps / 1000   (metres)
```

to every node, simulating continuous rainfall accumulation, before propagating hydraulically.

### 5.3 Hydraulic Propagation

For each node `v` with `water_depth[v] > 0`, flow to neighbor `u` is computed as:

```
hydraulic_head[v] = elevation[v] + water_depth[v]

slope = (hydraulic_head[v] - hydraulic_head[u]) / edge_length(v, u)

manning_flow = (1/n) × A × R^(2/3) × slope^(1/2)     [Manning's equation, simplified]

flow[v→u] = min(water_depth[v], manning_flow) × decay_factor
```

where:
- `n` = Manning's roughness coefficient (default 0.035 for urban roads)
- `decay_factor` ∈ [0.1, 1.0] controls simulation speed/realism (user-configurable)
- Flow only occurs when `hydraulic_head[v] > hydraulic_head[u]` (downhill)
- Sinks (nodes with no lower neighbors) accumulate water

After each step, the **Sentinel Bridge** is updated:
```python
sentinel_state = {
    "step": current_step,
    "flooded_nodes": [...],
    "at_risk_population": N,
    "safe_shelters": [...],
    "unsafe_shelters": [...],
    "flood_polygons": {...}   # GeoJSON
}
```

### 5.4 Risk Classification

Road segments are classified by average water depth on incident nodes:
- **Green (Passable):** `depth < 0.15m`
- **Yellow (Caution):** `0.15m ≤ depth < 0.30m`
- **Red (Dangerous/Blocked):** `depth ≥ 0.30m`

Nodes with `depth ≥ 0.20m` are classified **at-risk** and become evacuation sources.

### 5.5 Flood Impact Polygon

After each simulation step, flooded nodes are alpha-shaped into a **GeoJSON Polygon** using `alphashape` and broadcast via SSE. The frontend updates the flood overlay layer in real time.

---

## 6. AI Optimization Algorithms

### 6.1 Shared Base Planner (`base_planner.py`)

All three algorithms inherit from `BaseEvacuationPlanner`, which provides:

**Flood-Aware Edge Weight:**
```
flood_weight(u,v) = road_length(u,v) × (1 + 5 × avg_water_depth(u,v)) × traffic_factor(u,v)
```

**Dijkstra Precomputation:**
Single-source Dijkstra from each safe shelter `s` over flood-weighted edges produces:
- `dist_matrix[i][j]` = flood-weighted distance from at-risk node `i` to shelter `j`
- `time_matrix[i][j]` = estimated travel time = `raw_distance / 1.2` (m/s walking speed)

**Shared Fitness Function:**
```
fitness(chromosome) =
    Σᵢ [ dist_matrix[i][chromo[i]] × pop[i] ]           # flood-weighted distance cost
  + 0.5 × Σᵢ [ time_matrix[i][chromo[i]] × pop[i] ]     # travel time cost
  + 100,000 × Σⱼ max(0, assigned[j] - capacity[j])²     # capacity overflow penalty
  + 1,000,000 × unassigned_population                    # hard penalty for unrouted people
```

**Greedy Seed Chromosome:**
Each at-risk node is assigned to the nearest shelter (by `dist_matrix`) with remaining capacity, providing an informed starting solution for all algorithms.

---

### 6.2 Genetic Algorithm (GA)

**File:** `backend/genetic_algorithm/core.py`  
**Class:** `GeneticEvacuationPlanner(BaseEvacuationPlanner)`

#### Parameters
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Population size | 30–60 | Scales with number of at-risk nodes |
| Generations | 30–60 | Computational budget |
| Mutation rate | 0.15 | Balances exploration vs. exploitation |
| Elitism | Top 10% | Preserves best solutions across generations |
| Greedy seeding | 80% | Informed initialization; 20% random for diversity |

#### Algorithm

**Initialization:**
```
80% of chromosomes: greedy_seed + random perturbation (±15% shelter reassignment)
20% of chromosomes: fully random, capacity-aware assignment
```

**Selection:** Tournament (k=3) — sample 3 chromosomes, keep best by fitness.

**Crossover (Two-Point):**
```python
# For two parents p1, p2, select cut points i < j
child[0:i]   = p1[0:i]
child[i:j]   = p2[i:j]
child[j:end] = p1[j:end]
```

**Mutation (Distance-Biased):**
```python
# With probability mutation_rate, reassign group g to one of its 3 nearest shelters
# (sampled proportionally to 1/distance, not uniformly)
```

**Capacity Repair (Hard Constraint):**
Any chromosome where `assigned[j] > capacity[j]` for any shelter `j` has excess population randomly redistributed to shelters with available capacity. This ensures all GA solutions are strictly feasible (capacity-violating chromosomes never reach fitness evaluation with overflow).

**Output:** Best chromosome → decoded to GeoJSON route paths via `geometry_mixin.py`.

---

### 6.3 Ant Colony Optimization (ACO)

**File:** `backend/aco/core.py`  
**Class:** `ACOEvacuationPlanner(BaseEvacuationPlanner)`

#### Parameters
| Parameter | Symbol | Value |
|-----------|--------|-------|
| Number of ants | m | 30–60 |
| Iterations | T | 30–60 |
| Pheromone importance | α | 1 |
| Heuristic importance | β | 3 |
| Evaporation rate | ρ | 0.1 |
| Initial pheromone | τ₀ | 1.0 (uniform) |

#### Algorithm

**Pheromone matrix:** `τ[i][j]` — pheromone strength on assignment of group `i` to shelter `j`.

**Heuristic:** `η[i][j] = 1 / dist_matrix[i][j]` (closer = more attractive).

**Ant construction (for each ant per iteration):**
```
For each at-risk group i:
    P(shelter j) ∝ τ[i,j]^α × η[i,j]^β    if capacity[j] not exceeded
                 = 0                          otherwise (capacity mask)
    Sample shelter j from probability distribution P
```

**Pheromone update (after all ants complete a tour):**
```
τ[i,j] ← (1 - ρ) × τ[i,j] + Σ_ants [Δτ_ant]
Δτ_ant[i,j] = Q / fitness(ant)   if ant assigned group i to shelter j
            = 0                   otherwise
```

where `Q = best_known_fitness × 0.1` (adaptive deposit scale).

**Warm start:** The greedy chromosome is used as the initial best-known solution, seeding pheromone on its assignments before iteration 1.

**Vectorised implementation:** Probability computation and pheromone deposits use `np.add.at()` and masked NumPy arrays, enabling performance parity with GA on large graphs.

---

### 6.4 Particle Swarm Optimization (PSO)

**File:** `backend/pso/core.py`  
**Class:** `PSOEvacuationPlanner(BaseEvacuationPlanner)`

#### Parameters
| Parameter | Symbol | Value |
|-----------|--------|-------|
| Number of particles | N | 30–60 |
| Iterations | T | 30–60 |
| Inertia weight | w | 0.7 |
| Cognitive coefficient | c₁ | 1.5 |
| Social coefficient | c₂ | 2.0 |
| Max velocity | v_max | 4.0 |

#### Algorithm

Discrete adaptation of standard PSO for integer shelter-assignment vectors.

**State per particle:**
- `position[n][i]` ∈ {0, ..., S-1} — shelter index for group `i`
- `velocity[n][i]` ∈ [-v_max, v_max] — continuous velocity
- `pbest[n]` — personal best position
- `gbest` — global best position across all particles

**Velocity update:**
```
v[n][i] = w × v[n][i]
         + c₁ × r₁ × (pbest[n][i] - x[n][i])
         + c₂ × r₂ × (gbest[i]    - x[n][i])
v[n][i] = clip(v[n][i], -v_max, v_max)
```

**Position update (sigmoid-based discrete):**
```
P_switch[i] = sigmoid(v[n][i]) = 1 / (1 + exp(-v[n][i]))

If rand() < P_switch[i]:
    x_new[n][i] = pbest[n][i] if rand() < 0.5 else gbest[i]
Else:
    x_new[n][i] = x[n][i]    (keep current)
```

**Capacity Repair:** After each position update, `max(0, assigned[j] - capacity[j])` excess population is redistributed to shelters with remaining capacity, ensuring feasibility.

**Initialization:**
```
80% particles: greedy_seed ± random reassignment (15% of groups)
20% particles: fully random, capacity-aware (genuine exploration)
```

---

### 6.5 Algorithm Performance Benchmarking (Analysis Mode)

The **Algorithm Analysis Mode** runs GA → ACO → PSO on the same flood scenario with **3 stability runs each** (9 total). Each run applies independent Gaussian noise:
- `dist_matrix` perturbation: σ=5%, capped at ±10%
- `time_matrix` perturbation: σ=3%, capped at ±7%

Dijkstra precomputation runs **once** and is shared via `copy.deepcopy` across all 9 runs to eliminate computational bias.

#### Metrics

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| Mean Fitness | `avg(best_fitness over 3 runs)` | Lower = better route quality |
| Std Dev | `std(best_fitness over 3 runs)` | Lower = more predictable |
| Stochastic Stability | `1 - (std_dev / mean_fitness)` | > 99% = highly stable |
| Convergence Speed | Iteration where 95% improvement achieved | Lower = faster convergence |
| Path Diversity | Unique (origin→shelter) pairs / total pairs | Higher = less road congestion |

#### Empirical Results (Typical Bengaluru Urban Hobli, ~150 at-risk nodes)

```
Algorithm   Mean Fitness    Std Dev    Stability    Convergence    Path Diversity
ACO         583,600         1,200      99.79%       1–3            18–22%
PSO         583,800         2,800      99.52%       5–10           21–25%
GA          588,500         4,100      99.30%       15–25          28–35%
```

**Key finding:** ACO achieves lowest fitness (best route quality) but requires 100+ iterations for full pheromone differentiation; with 30–60 iterations it often converges at the greedy seed (convergence_speed = 1). PSO shows the most visible convergence curve (active optimization visible in charts). GA produces the highest path diversity.

#### Recommendation by Use Case

| Use Case | Recommended | Reason |
|----------|------------|--------|
| Final evacuation plan (quality) | **ACO** | Graph-native pheromone routing = lowest fitness |
| Real-time replanning (speed) | **PSO** | Fastest active convergence (5–10 iterations) |
| Contingency planning (diversity) | **GA** | Highest path diversity → multiple distinct plans |

---

## 7. Real-Time Traffic Integration (TomTom)

**File:** `backend/traffic_data/tomtom.py`

### 7.1 Parallel Bulk Fetch

Up to **100 major road segments** (motorway, trunk, primary, secondary) are pre-identified from the loaded OSMnx graph. Their geographic midpoints are submitted to TomTom's `flowSegmentData` API endpoint **concurrently** using `ThreadPoolExecutor(max_workers=10)`, reducing total fetch time from potentially 100+ seconds (sequential) to **3–10 seconds** in practice.

### 7.2 Traffic-Aware Edge Weight

Fetched `currentTravelTime` and `freeFlowTravelTime` are matched back to graph edges by coordinate proximity:

```
traffic_factor = min(5.0, currentTravelTime / freeFlowTravelTime)

flood_weight(u,v) = road_length(u,v) × (1 + 5 × avg_water_depth(u,v)) × traffic_factor(u,v)
```

A `traffic_factor = 2.0` doubles the effective edge cost — the GA/ACO/PSO naturally routes evacuees around congested roads.

### 7.3 Traffic Congestion Visualization

After optimization, the backend returns a GeoJSON FeatureCollection with `congestion_factor` per segment. The frontend renders colored signal markers:
- 🟢 Clear: `congestion_factor < 1.05`
- 🟡 Moderate: `1.05 ≤ congestion_factor ≤ 2.0`
- 🔴 Heavy: `congestion_factor > 2.0`

### 7.4 Graceful Degradation

If TomTom API is unavailable (missing key, rate limit, no major roads in region), `traffic_factor = 1.0` for all edges — flood-only routing proceeds without disruption.

---

## 8. Generative AI (GenAI) Architecture

### 8.1 Multi-Tier Fallback LLM Stack

```
Primary:   Google Gemini 2.5 Flash  (google-generativeai SDK)
Fallback 1: Groq Llama 3.3-70b      (groq SDK, cloud)
Fallback 2: Ollama Llama 3.2        (local inference, offline)
```

If any tier fails (rate limit, timeout, API error), the system automatically retries on the next tier, guaranteeing 100% uptime for AI features during critical operations.

### 8.2 The Sentinel Bridge (`mcp_state.json`)

The `SentinelBridge` is the core anti-hallucination mechanism. Every simulation frame, `UrbanFloodSimulator.updateSentinelState()` writes:

```json
{
  "simulation_step": 12,
  "total_steps": 20,
  "rainfall_mm": 85.0,
  "at_risk_population": 14230,
  "safe_population": 0,
  "flooded_node_count": 342,
  "safe_shelters": [{"name": "GKVK School", "capacity": 500, "occupied": 0}],
  "unsafe_shelters": [...],
  "road_blockages": 89,
  "evacuation_results": {...},
  "hobli_name": "Yelahanka",
  "timestamp": "2025-07-14T09:23:11"
}
```

The GenAI layer reads exclusively from this file — it cannot hallucinate flood depths, shelter states, or population counts because all values are grounded to the current simulation frame.

### 8.3 Dual FastMCP Architecture

Two specialized FastMCP servers expose different data domains:

**Evacuation Server (`mcp_evacuation_server.py`) — "Hard Data":**
- `get_flood_state()` — current flood depths, at-risk nodes
- `get_evacuation_routes()` — algorithm results (fitness, paths, shelter assignments)
- `get_road_blockages()` — impassable road segments
- `get_shelter_status()` — safe/unsafe shelters with capacity

**Intelligence Server (`mcp_flood_intelligence_server.py`) — "Soft Data":**
- `get_metro_status()` — Bengaluru metro line integrity (from MongoDB)
- `get_bus_availability()` — BMTC fleet status and depot locations
- `get_shelter_resource_map()` — IDRN inventory (medical, food, SAR equipment)
- `check_resource_gaps()` — compares inventory against NDRF/SDRF guidelines

### 8.4 Agentic Execution Loop

The `GenAICopilot` (`app_copilot.py`) follows an **Intent → Thinking → Execution → Synthesis** loop:

1. **Intent Stage:** Classify user query (disaster scale assessment, route optimization, resource audit, etc.)
2. **Thinking Loop:** Autonomously chain tool calls across both MCP servers. Example: `get_metro_status()` reveals Purple Line disrupted → immediately calls `get_shelter_resource_map()` for nearest shelters with inflatable boats.
3. **Execution:** Parallel tool calls where semantically independent.
4. **Synthesis:** Merge Hard Data (physics constraints) with Soft Data (logistics) into a tactical plan.

### 8.5 Expert Panel Pipeline

`expert_panel.py` generates multi-persona concurrent analysis:
- **Tactical Commander** — evacuation route priorities, bottleneck identification
- **Logistics Chief** — resource gap analysis against NDRF guidelines, bus dispatch
- **Medical Officer** — hospital capacity, medical supply adequacy
- **Infrastructure Analyst** — metro/road network integrity

Each persona receives the same Sentinel state but produces domain-specific structured recommendations. Results are merged into a unified tactical advisory.

---

## 9. Database Schema (MongoDB Atlas)

| Collection | Key Fields | Purpose |
|-----------|-----------|---------|
| `users` | `email, password_hash, role, permissions` | JWT-based RBAC authentication |
| `hobli_coordinates` | `hobli_name, lat, lon, district, bbox` | Geographic boundaries for OSM fetch |
| `rainfall_data` | `station_name, hobli_ref, date, rainfall_mm` | Historical simulation seeding |
| `population` | `ward_num, hobli_ref, population, male, female` | Demographic distribution |
| `metro_infrastructure` | `station_name, line_color, lat, lon, status` | Transit integrity for GenAI |
| `buses_depots` | `bus_id, depot_name, capacity, availability_status` | Fleet management for GenAI |
| `disaster_resources` | `shelter_ref, resource_category, item_name, quantity_available` | IDRN inventory for gap analysis |

---

## 10. Frontend Visualization

**Technology:** React 19, Vite, MapLibre GL JS, Tailwind CSS 4, Recharts, Lucide React

### Map Layers (stacked, toggleable)
1. **Basemap:** CartoDB Positron (light, Google Maps aesthetic)
2. **Road Network:** All edges colored by flood risk (Green/Yellow/Red)
3. **Flood Polygon:** Alpha-shaped flood extent with opacity gradient
4. **Shelter Layer:** House icons (Green=Safe, Red=Flooded, Amber=Synthetic) with hover tooltips
5. **Evacuation Routes:** Purple polylines following actual road network; Citizen pins at sources
6. **Traffic Layer:** Signal markers at road midpoints colored by congestion factor

### Real-time Performance Optimization
- **Selective re-renders:** Only flood polygon and road overlay layers update per SSE frame
- **Point-in-polygon ray casting:** Client-side shelter flood state (no extra API calls)
- **Vector tile rendering:** MapLibre GL renders 10,000+ nodes at 60 FPS via GPU acceleration
- **State management:** React Context for shared simulation state (no Redux overhead)

---

## 11. Security Architecture

- **JWT Authentication:** RS256-signed tokens for role-based access (Researcher vs. Disaster Authority)
- **RBAC:** Only Disaster Authorities can trigger resource-intensive simulations
- **API Key Security:** All external API keys (TomTom, Gemini, Groq, MongoDB) stored in `.env`, never exposed to frontend
- **Pydantic Validation:** All incoming simulation parameters strictly validated before reaching physics engine
- **CORS Policy:** Backend allows only authorized frontend origins
- **Privacy-by-Design:** Population data is purely synthetic (no PII stored or processed)

---

## 12. Scalability & Reliability

### Scalability
- **Stateless Backend:** No session state in memory — enables horizontal scaling
- **Two-Tier Caching:** In-process OSMnx graph cache + disk-based `.graphml` files (eliminates repeated OSM downloads)
- **Async Architecture:** `asyncio` + `ThreadPoolExecutor` — flood simulation and TomTom fetch run as non-blocking background tasks

### Reliability (Graceful Degradation)
| Failure | Fallback |
|---------|---------|
| TomTom API down | Free-flow traffic assumption (traffic_factor = 1.0) |
| OSM/Overpass down | Cached `.graphml` graph used |
| MongoDB outage | Read-only mode (cached data) |
| SSE connection drop | Recent frame buffered for replay on reconnect |
| GenAI API failure | Next tier in fallback stack (Gemini → Groq → Ollama) |

---

## 13. Technology Stack Summary

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend framework | React | 19 |
| Build tool | Vite | 5.x |
| Map rendering | MapLibre GL JS + react-map-gl | 4.x |
| UI styling | Tailwind CSS | 4 |
| Charts | Recharts | 2.x |
| HTTP client | Axios | 1.x |
| Backend framework | FastAPI + Uvicorn (ASGI) | 0.115.x |
| Language | Python | 3.10+ |
| Graph library | OSMnx + NetworkX | 1.9.x / 3.x |
| Geospatial | GeoPandas, Shapely, Rasterio, Pyproj | Latest |
| Numerical | NumPy, SciPy, Pandas | Latest |
| Database | MongoDB Atlas (PyMongo) | 7.x |
| GenAI (primary) | Google Gemini 2.5 Flash | API |
| GenAI (fallback 1) | Groq Llama 3.3-70b | API |
| GenAI (fallback 2) | Ollama Llama 3.2 | Local |
| MCP servers | FastMCP | Latest |
| Traffic API | TomTom Traffic Flow API | v4 |
| Road data | OpenStreetMap via OSMnx | — |
| Elevation data | SRTM 30m DEM via Rasterio | — |

---

## 14. Key Research Contributions

1. **Unified Prediction-to-Action Pipeline:** The system is the first to tightly couple OSMnx-based digital twin construction, progressive hydrodynamic flood simulation, and three head-to-head metaheuristic algorithms within a single deployable platform.

2. **Tri-Algorithm Benchmarking Framework:** Systematic comparison of GA, ACO, and PSO on identical flood scenarios with shared fitness function, distance matrices, and ±5% perturbation stability testing — enabling statistically valid algorithm selection guidance.

3. **Sentinel-Grounded Agentic GenAI:** The dual FastMCP architecture with `mcp_state.json` grounding prevents LLM hallucination of physical constraints, enabling safe deployment of autonomous AI decision support in life-critical scenarios.

4. **Traffic-Flood Compound Cost Model:** The compound edge weight `road_length × flood_penalty × traffic_factor` simultaneously penalizes flooded and congested roads within a single Dijkstra precomputation — reducing the multi-objective routing problem to a single-weight shortest-path problem.

5. **Hard-Constraint Capacity Feasibility:** All three algorithms enforce shelter capacity as a hard constraint (not a penalty), guaranteeing physically realizable evacuation plans — a critical requirement for operational deployment.

---

## 15. Limitations

- The system uses software-based simulation; no IoT water-level sensors or physical hardware interface.
- Population data based on 2011 Census with 15% growth projection (not real-time census).
- TomTom API is rate-limited; rural or low-road-density regions may have sparse traffic data.
- Flood physics is simplified (no full 2D Shallow Water Equations); Manning's equation approximates flow but does not model backflow or pressure waves.
- GenAI responses are bounded by the LLM's knowledge cutoff and quality of Sentinel state.

---

## 16. Future Work

- Real-time SAR satellite + IoT ultrasonic sensor integration for live flood tracking
- Multi-modal evacuation (rescue trucks, inflatable boats, drones) for "manual rescue required" population
- Multi-agent Reinforcement Learning (MARL) for dynamic re-routing as flood evolves
- Public alerting API (SMS/push) integrated with national emergency communication systems
- Global scalability engine — automate digital twin construction for any city via coordinates
- Predictive pathing using 6–12 hour meteorological forecast integration

---

## 17. Key References (from Literature Survey)

[1] X. Zhang et al., "Deep reinforcement learning for optimal rescue path planning in uncertain urban pluvial flood scenarios," *Appl. Soft Comput.*, 2023.

[2] J. Li et al., "A novel emergency evacuation route optimization model in flood disasters," *Saf. Sci.*, vol. 180, 2024.

[3] A. Gupta et al., "Artificial intelligence for flood risk management: A comprehensive state-of-the-art review," *Environ. Model. Softw.*, vol. 185, 2025.

[4] Y. Zhou et al., "A framework for incorporating rainfall data into a flooding digital twin," *J. Hydrol.*, 2025.

[5] Y. Chen et al., "Large-scale real-time evacuation modeling during urban floods," *Int. J. Disaster Risk Reduction*, vol. 95, 2025.

[6] D. Mandal et al., "City-scale digital twin framework for flood impact analysis," *Urban Climate*, 2025.

[7] H. Yin et al., "An overview of flood evacuation planning: Models, methods, and future directions," *J. Hydrol.*, vol. 656, 2025.

[8] H. Behrooz and M. Ilbeigi, "Adaptive emergency evacuation routing with directional road control," *IEEE Access*, vol. 12, 2024.

[9] Li, C. et al., "Optimising urban flood evacuation routes with metaheuristic algorithms: A case study of York, UK," *IAHR*, 2025.

[10] H. Nirwana et al., "An intelligent optimization method for evacuation route planning," *Eng. Technol. Appl. Sci. Res.*, vol. 14, no. 6, 2024.

[11] A. Prihatmanto et al., "The digital twin city in enhancing flood evacuation systems," *IEEE SMC*, 2025.

[12] P. P. Mujumdar et al., "Development of an urban flood model for Bengaluru city," *Current Science*, vol. 120, no. 9, 2021.

[13] W. Xu and K. Zhang, "Ant Colony optimization for urban flood rescue routing," *SSRN*, 2024.

---

## 18. Research Comparisons (Paper Justification Work)

This section documents the two main empirical comparisons being built to justify the
project in the research paper, along with implementation decisions made during development.

---

### 18.1 Why These Comparisons?

The paper needs to answer two fundamental questions:

> **"Why use a digital twin?"**
> → Comparison A: Digital Twin routing vs naive nearest-shelter routing.

> **"Why use MCP for GenAI?"**
> → Comparison B: MCP tool-calling vs static context dump (non-MCP).

Both comparisons share the same philosophy: **hold everything constant except one
variable**, measure the difference, and show it matters for disaster response quality.

---

### 18.2 Comparison A: Digital Twin vs Naive Routing (Planned)

**What changes:** the edge weight used by Dijkstra.

| Mode | Edge weight |
|------|-------------|
| Naive | `road_length` (raw metres, no flood or traffic awareness) |
| Digital Twin | `road_length × (1 + 5×flood_depth) × traffic_factor` |

**Metrics to capture per scenario:**

- Fitness score (lower = better route quality)
- % of routes that pass through flooded road segments
- Shelter capacity overflows (naive tends to crowd the nearest shelter)
- Average elevation of assigned shelters (naive routes downhill into flood zones)
- Unassigned population (people who cannot reach a shelter)

**Experimental design:** Run 3 flood intensity scenarios (low / medium / high rainfall)
on the same Hobli with both edge weights. Show the gap widens as flooding gets worse
— naive routing becomes catastrophically bad under severe floods.

**Status:** Planned. Infrastructure (base_planner.py's Dijkstra + fitness function)
is fully ready; only needs a ~60-line `run_naive_baseline()` method and an API endpoint.

---

### 18.3 Comparison B: MCP vs Non-MCP GenAI (Implemented)

#### The Core Idea in Plain English

The system uses GenAI (Gemini) to answer questions about the evacuation state —
"which shelter is overflowing?", "which roads are bottlenecks?", "are there buses
near the flood zone?", etc.

There are two ways to give the AI the data it needs:

- **Non-MCP (baseline):** Dump everything — shelter occupancy, routes, road conditions,
  terrain, metro status, flood impact, rescue guidelines — into one big prompt upfront.
  Like handing someone a 150-page briefing and asking them to find an answer.

- **MCP (our system):** Give the AI a tiny summary (6 fields, ~80 words) and a set of
  tools it can call on demand. Like a doctor who orders the specific tests they need
  rather than reading the entire patient history.

The comparison isolates exactly one variable: **retrieval mechanism**. Both modes use
the same model (Gemini 2.5 Flash), the same underlying data, and answer the same 8 questions.

#### Design Decisions Made

**Why minimal seed for MCP?**
Initially, both arms received the full `enriched_context` (140 shelters, 25 routes,
pressure junctures, etc.). Gemini found all the answers inline and never called a
single tool. The fix: give MCP only a 6-field simulation summary — it is then forced
to call `get_shelter_status()`, `get_route_summary()`, `analyze_road_conditions()` etc.
to actually retrieve the data it needs.

**Why strip `local_inventory` from non-MCP?**
The `enriched_context` contains 200 fire-station/hospital resource items (supply sources
for the logistics expert panel). These caused hallucinations: the model confused "SOUTH
FIRE STATION — Slotted Screwdrivers 4 Nos at 0.8km" with shelter recommendations,
fabricating "State Disaster Response Force A Company — Tent Store" advice. Stripping
`local_inventory` eliminates this noise without removing any shelter data.

**Why Groq as judge fallback?**
Gemini's free tier allows 20 API requests per day. One comparison run (8 questions × 3
calls: non-MCP arm + MCP arm + judge) = 24 calls — already over the limit. Adding Groq
llama-3.3-70b as judge fallback means testing continues unblocked even after Gemini
quota is exhausted.

#### Files Created

| File | Role |
|------|------|
| `genai/non_mcp_chat.py` | Non-MCP arm: pre-materializes all tool outputs, strips local_inventory, no tools given to Gemini |
| `genai/mcp_chat_metrics.py` | MCP arm: minimal seed + Gemini tool-calling, records every tool call with name/args/result |
| `genai/mcp_evaluator.py` | Comparison harness: runs both arms in parallel, auto-metrics, LLM judge (Gemini → Groq fallback) |
| `main.py` (modified) | New endpoint: `POST /research/mcp-comparison` |

#### Auto-Measurable Metrics (no human needed)

| Metric | How measured |
|--------|-------------|
| `prompt_words` | `len(prompt.split())` before sending to Gemini |
| `response_words` | `len(response.split())` |
| `latency_s` | Wall-clock time from send to first token |
| `tool_call_count` | Count of function_call parts in response stream (MCP only) |
| `tools_used` | List of tool names called, in order (MCP only) |
| `shelter_name_match_count` | Real shelter names from simulation found in response |
| `numeric_match_rate` | Fraction of numbers cited that match actual simulation data |
| `suspicious_capitalised` | Title-Case noun phrases not matching any real shelter (hallucination heuristic) |

#### LLM-Judge Rubric (Gemini/Groq blind-scores 1–5)

| Dimension | 1 (worst) | 5 (best) |
|-----------|-----------|---------|
| `accuracy` | Cites wrong names/numbers | All data exactly matches simulation |
| `specificity` | Generic boilerplate advice | Data-grounded, names specific nodes/shelters |
| `actionability` | NDRF officer could not act on this | Immediate operational action possible |
| `hallucination_severity` | Severely fabricated entities | Zero hallucinations detected |

The judge receives: simulation ground truth (trimmed to 15 shelters + route overview) +
the question + the response. It does NOT know which mode produced the response (blind scoring).

#### Question Bank (8 Questions)

1. Which shelter is most at risk of overflow and what should we do about it?
2. What is the safest evacuation route from the most flooded zone?
3. How many people cannot be evacuated and why?
4. Which roads are critical bottlenecks and how should NDRF approach them?
5. Are there bus stops near the flooded zones that can support evacuation?
6. Which transit routes will be disabled by the current flood?
7. What are the unmet rescue needs, and who should we escalate to?
8. Give me an overall situation report I can hand to the District Commissioner.

Questions 5 and 6 are the most differentiating — non-MCP physically cannot answer
them (no bus/transit data in the static dump). MCP calls `check_bus_availability(lat, lon)`
and `analyze_transit_disruptions(location, depth)` to answer them specifically.

#### Test Results (Single Question, Beguru-1, ACO, 140 shelters)

Question: *"Which shelter is most at risk of overflow?"*

| Metric | Non-MCP | MCP |
|--------|---------|-----|
| Prompt words | 7,658 | 80 |
| Response words | 118 | 38 |
| Latency | 6.6s | 6.3s |
| Tool calls | 0 | 1 (`identify_evacuation_hubs`) |
| Shelter name matches | 8 | 3 |
| Numeric match rate | 0.875 | **1.000** |
| Judge: Accuracy | 4/5 | 5/5 |
| Judge: Specificity | 5/5 | 3/5 |
| Judge: Actionability | 4/5 | **1/5** |
| Judge: Hallucination severity | 4/5 | **5/5** |

**Interpretation:** For broad factual lookup questions (answerable from the static dump),
non-MCP achieves better completeness/actionability. MCP achieves perfect numeric accuracy
and zero hallucinations but uses a suboptimal tool (`identify_evacuation_hubs` vs the
more appropriate `get_shelter_status`). Tool selection quality depends on seed context quality.

#### Expected Differentiating Results (not yet tested — quota limit hit)

For questions 5 and 6 (bus stops, transit disruptions):
- Non-MCP: empty response or hallucinated generic answer (no tool data in dump)
- MCP: calls `check_bus_availability` / `analyze_transit_disruptions`, returns
  specific BMTC route names and stop distances

This is the strongest comparison point for the paper.

#### Research Claim Being Built

> "MCP-enabled GenAI agents produce more accurate, less hallucinated responses
> than equivalent static-dump prompting for questions requiring real-time or
> location-specific data. For broad factual summaries, static dumping achieves
> comparable coverage at lower latency. The appropriate approach is therefore
> question-type-aware: MCP for targeted/live queries, static dump for comprehensive
> factual overviews."

This nuanced claim — not just "MCP is better" but "MCP is better for this class
of question" — is more defensible academically and more novel to reviewers.

---

### 18.4 Implementation Roadmap

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | Backend: 3 new files + endpoint | **Done** |
| Phase 1b | Groq fallback for LLM judge | **Done** |
| Phase 2 | Frontend: "Research Lab" UI panel with side-by-side comparison | To do |
| Phase 3 | Research script: 3 scenarios × 8 questions = 48 pairs, CSV/JSON output | To do |

**Phase 2 plan (Research Lab UI panel):**
- New tab in the sidebar
- Dropdown of 8 preset questions + free-text custom input
- Side-by-side response cards (Non-MCP left, MCP right)
- Metrics row under each card (latency, tool calls, judge scores, word count)
- MCP tool trace: expandable list of which tools were called in order
- "Run Comparison" button triggers `POST /research/mcp-comparison`

**Phase 3 plan (paper research script):**
- `paper/run_mcp_vs_non_mcp.py` — standalone CLI
- Loops through 3 simulation states (run simulation at low/medium/high flood, save mcp_state.json each time)
- Runs all 8 questions through both arms per state = 48 paired comparisons
- Outputs:
  - `paper/mcp_results_raw.json` — full responses for human review
  - `paper/mcp_results_metrics.csv` — LaTeX table-ready
  - `paper/mcp_results_summary.md` — auto-generated aggregate stats
