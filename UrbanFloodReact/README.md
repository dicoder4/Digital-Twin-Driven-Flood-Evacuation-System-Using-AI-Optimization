# Urban Flood Model Use Guide

This project uses a decoupled architecture for high performance:
- **Backend**: FastAPI (Python) for physics simulation.
- **Frontend**: React + MapLibre for high-performance visualization.

## Setup Instructions

### 1. Backend Setup
Navigate to the `backend` folder and install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

Run the backend server:
```bash
uvicorn main:app --reload
```
The API will be available at `http://localhost:8000`.

### 2. Frontend Setup
Open a new terminal, navigate to the `frontend` folder, and install dependencies:
```bash
cd frontend
npm install
```

Run the development server:
```bash
npm run dev
```
Open the link (usually `http://localhost:5173`) in your browser.

## Features
- **Multi-Hobli Support**: Hierarchical region selection (District → Taluk → Hobli) for Bengaluru Urban and Rural.
- **Lazy Loading**: Automatic downloading and disk-caching of road networks (OSMnx) for the selected region.
- **Historical Rainfall Data**: Simulation based on real meteorological data from May, June, and July datasets.
- **Road Risk Assessment**: Real-time coloring of road segments based on calculated flood depth (Green: Passable, Yellow: Caution, Red: Dangerous).
- **Population Integration**: 
  - **Ward-Level Data**: Loads total, male, and female metrics from BBMP ward-level CSV datasets.
  - **Two-Pass Matching**: Matches hoblis to wards directly or falls back to Taluk-level aggregation.
  - **Taluk Bucketing**: Groups wards by Assembly Constituency to calculate Taluk-wide population totals.
  - **Proportional Scaling**: Distributes aggregated Taluk counts evenly across hoblis without direct matches.
- **Evacuation Shelter Candidate Identification**
  - **Extract from OSM** — Queries OpenStreetMap for shelter-suitable buildings (schools, hospitals, community centres, town halls, police stations, fire stations, public buildings) within ~2 km of the hobli centre using `osmnx.features_from_point()`.
  - **Attach to graph** — Each candidate is snapped to the nearest road graph node via `osmnx.nearest_nodes()`, enabling future routing.
  - **Assign capacity** — Rule-based capacity assigned by building type (e.g. School → 500, Hospital → 200).
  - **Filter by flood state** — Frontend runs a point-in-polygon ray-casting check against the live flood GeoJSON on every simulation step. Shelters inside the flood zone turn red in real time without any extra API calls.
  - **Fallback** — If OSM returns no results for a hobli, 6 synthetic shelters are placed at high-degree road intersections (most connected/accessible nodes) and marked with amber icons.
- **MapLibre Visualization**: Uses a light CartoDB Positron basemap for a clean, Google Maps-like aesthetic.
- **SSE Real-time Updates**: Server-Sent Events (SSE) provide a smooth, step-by-step animation of flood propagation.

## How it works
- **Region Initialization**: Selecting a Hobli triggers the backend to load its road network. If not cached, it downloads data from OpenStreetMap.
- **Rainfall Input**: 
  - **Manual**: Adjust rainfall (mm) using a slider.
  - **Historical**: Select a specific date from history to auto-populate rainfall levels and see calculated "Risk Departure" badges.
- **Physics Propagation**: 
  - Water is "injected" at drains and lake boundaries.
  - In each time step, water flows to neighbors with lower elevation, adjusted by the **Flow Decay** factor.
- **Visualization**: 
  - **Flood Area**: A gradient poly-layer showing general flood extent.
  - **Road Overlay**: Specific road segments are highlighted and colored based on depth thresholds (e.g., >15cm is High risk).
- **Legend**: A dynamic legend in the bottom-right corner provides context for the color mappings.

## Flooding
- **Initialization**: Water is "injected" at identified drain locations (simulating overflow) and lake boundaries based on the rainfall amount.
- **Propagation**: In each time step, every node with water checks its connected neighbors. If a neighbor is at a lower elevation, a portion of the water (determined by the decay factor and slope steepness) flows down to that neighbor.
- **Accumulation**: If a node has no lower neighbors (a "sink"), water accumulates there.
- **Heatmap**: We visualize this depth as a color gradient (Green→Yellow→Red) growing outwards from the sources over time.

### User flow
```
Load Hobli → Click "Find Shelters" → House icons appear on map (all green)
                                              ↓
                              Run flood simulation
                                              ↓
              Icons turn red live as flood reaches each shelter
              Sidebar shows: "4 safe · 6 total"  ← updates each step
                                              ↓
              Hover over any icon → tooltip shows name, type, capacity
                                              ↓
               Click "View shelter list" in sidebar → full scrollable list
```

---

## Genetic Algorithm — Evacuation Route Optimization

### Overview

After the flood simulation completes, a **Genetic Algorithm (GA)** runs once to assign every at-risk population group to a safe evacuation shelter. The goal is to minimise total evacuation cost — a combinatorial optimisation problem too large to solve exhaustively (*S^N* combinations for *N* groups and *S* shelters).

### Three-Phase Design

#### Phase 1 — Flood-Aware Precomputation

Before the GA starts, real road-network distances are computed for every (group, shelter) pair using **Dijkstra's algorithm** with flood-penalised edge weights:

```
flood_weight = road_length × (1 + 5 × avg_water_depth_on_edge)
```

Edges with deeper water count as substantially longer, so evacuees are automatically routed **around flooded roads** — not through them.

#### Phase 2 — Greedy Population Seeding

Rather than starting from random assignments, **80% of the initial population** is seeded from a greedy nearest-shelter heuristic: each group is assigned to the nearest (flood-weighted) shelter that still has remaining capacity, with small perturbations for diversity. The remaining 20% are fully random to prevent premature convergence.

#### Phase 3 — GA Evolution

| Operator | Detail |
|---|---|
| **Fitness** | `flood_dist × pop + 0.5 × travel_time × pop + capacity_overflow_penalty` |
| **Selection** | Tournament (k = 3) — best of 3 random chromosomes |
| **Crossover** | Two-point crossover for minimal disruption |
| **Mutation** | Reassigns to one of the 3 nearest shelters (distance-biased, not random) |
| **Elitism** | Top 10% carried unchanged into each new generation |

Capacity overflow is penalised heavily (×2000 per excess person) to prevent overfilling shelters.

### Multi-Factor Fitness

The fitness function balances three concerns simultaneously:

1. **Flood-weighted network distance** — prefers shorter routes on drier roads
2. **Travel time** — estimated as raw road distance ÷ walking speed (1.2 m/s)
3. **Shelter capacity** — heavy penalty for over-assignment

### Output & Visualisation

Each GA result entry includes `from_node`, `to_shelter`, `pop`, and a `path` — ordered `[lon, lat]` waypoints tracing the flood-aware road route.

In the **Evacuation tab**, click any shelter row to see:
- 🟣 **Purple route lines** following the actual road network (flood-aware)
- 🧍 **Citizen pins** at each source location, labeled "Citizen N (X people)"
- 📍 **Destination pin** at the shelter with its name

Click the row again to clear the routes.

### Evacuation Mode (1% Scale)

Enable **Evacuation Mode** before running to scale population to 1% of real count, reducing GA runtime from minutes to seconds for rapid testing. The map people-layer also scales immediately on toggle.

---

## Live Traffic Integration (TomTom)

When **Live Traffic** is enabled alongside Evacuation Mode, real-time road congestion data from the **TomTom Traffic Flow API** is fetched and woven into the evacuation model before the GA runs. Here is how it works end-to-end:

1. **Regional Bulk Fetch via TomTom Flow API**
   Rather than querying traffic per-route (which would require hundreds of individual API calls and block the simulation), the system pre-identifies up to **100 major road segments** (motorway, trunk, primary, secondary) from the loaded OSMnx graph. Their geographic midpoints are submitted to TomTom's `flowSegmentData` endpoint **concurrently** using a `ThreadPoolExecutor` with 10 parallel workers — reducing total fetch time from potentially minutes (sequential) to **3–10 seconds** in practice. Each response returns `currentTravelTime` and `freeFlowTravelTime` in seconds for the nearest road segment.

2. **Traffic-Aware Edge Weight Augmentation**
   Fetched travel times are matched back to graph edges by coordinate proximity and stored as `traffic_time` and `free_flow_time` on each edge. The existing `flood_weight` formula is then extended with a **traffic multiplier**:
   ```
   traffic_factor = min(5.0, actual_time / free_flow_time)
   flood_weight   = road_length × flood_penalty × traffic_factor
   ```
   A road carrying 2× its normal traffic volume appears twice as "long" to Dijkstra — meaning the GA naturally routes evacuees **away from congested roads** toward free-flowing alternatives, even before shelter assignments are made.

3. **Effect on GA Route Optimisation**
   Because traffic factors feed directly into the precomputed `dist_matrix` that the GA uses for fitness evaluation, congested major roads incur a higher effective cost. Evacuees assigned near a heavily congested primary road will be re-routed to a parallel secondary or residential route with lower effective weight, even if it is geometrically longer. This mirrors real-world emergency management: emergency planners avoid congested arterials and favour quieter residential corridors during evacuations.

4. **Traffic Congestion Visualisation on Map**
   After simulation completes, the backend's `get_traffic_geojson()` method returns a **GeoJSON FeatureCollection** of all edges that received TomTom data, each tagged with a computed `congestion_factor`. Toggling **🚦 Show Traffic** on the map renders signal markers at the midpoint of each segment, colour-coded by severity:
   - 🟢 **Clear** (`< 1.05×`) — free-flowing, no meaningful delay
   - 🟡 **Moderate** (`1.05–2.0×`) — minor slowdown, slight cost increase
   - 🔴 **Heavy** (`> 2.0×`) — significant congestion, up to 5× edge cost penalty applied

5. **Graceful Degradation Without Traffic Data**
   If the TomTom API key is missing, the network returns no results, or all fetched segments are unresolvable (e.g., the hobli has no major roads), the system falls back silently to **flood-weight-only routing**. The GA continues to run normally and evacuation routes remain fully functional — traffic simply does not influence the route cost in that case. This ensures the simulation is never blocked by traffic API failures during critical emergency scenarios.
