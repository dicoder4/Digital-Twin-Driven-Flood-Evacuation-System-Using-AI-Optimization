# Digital Twin-Driven Flood Evacuation System Using AI Optimization

A research-grade urban flood evacuation platform combining physics-based digital twin simulation, metaheuristic AI optimization, and generative AI — built for real-time emergency response in Bengaluru.

**M.S. Ramaiah Institute of Technology, Bengaluru**  
Aditri B Ray · Anisha Ajit · Diya D Shah

**Live Demo:** [urbanflood-frontend-244754524479.asia-south1.run.app](https://urbanflood-frontend-244754524479.asia-south1.run.app/)

---

## Overview

This system integrates a hydrodynamic flood simulator with three competing AI optimization algorithms (GA, ACO, PSO) to generate congestion-aware evacuation plans. A generative AI layer, grounded to live simulation state via FastMCP, provides natural language explanations and agentic advisory capabilities. Real-time flood state is streamed to a React 19 + MapLibre GL frontend via Server-Sent Events.

---

## Architecture

```
UrbanFloodReact/
├── backend/          # FastAPI + Python simulation engine
│   ├── main.py                    # FastAPI app + route registration
│   ├── service.py                 # Core business logic + algorithm dispatch
│   ├── region_manager.py          # OSMnx graph loading + state store
│   ├── flood_simulator.py         # Hydrodynamic flood propagation
│   ├── simulate_routes.py         # Citizen routing simulation (SSE)
│   ├── simulation_engine.py       # Person movement physics + rerouting
│   ├── genetic_algorithm/core.py  # GA optimizer
│   ├── aco/core.py                # ACO optimizer
│   ├── pso/core.py                # PSO optimizer
│   ├── base_planner.py            # Shared Dijkstra + traffic precompute
│   ├── genai/                     # Generative AI layer
│   │   ├── mcp_evacuation_server.py      # FastMCP: hard simulation data
│   │   ├── mcp_flood_intelligence_server.py  # FastMCP: logistics + metro
│   │   ├── evacuation_chat.py            # Streaming Q&A (Gemini/Groq)
│   │   ├── expert_panel.py               # Multi-persona AI advisors
│   │   ├── app_copilot.py                # Agentic co-pilot (tool use)
│   │   └── context_builder.py            # Sim state → LLM prompts
│   ├── traffic_data/tomtom.py     # TomTom real-time traffic fetching
│   ├── shelter_generator.py       # OSM amenity → shelter extraction
│   ├── gis_terrain_loader.py      # SRTM DEM elevation (Rasterio)
│   ├── db.py                      # MongoDB Atlas connection + schema
│   ├── auth_routes.py             # JWT + role-based access
│   ├── citizen_routes.py          # Citizen interface endpoints
│   ├── notification_routes.py     # SMS/email alerting
│   ├── rainfall_loader.py         # Historical + simulated rainfall
│   └── weather_watcher.py         # Automated weather monitoring
│
└── frontend/         # React 19 + Vite + MapLibre GL
    ├── src/
    │   ├── App.jsx                    # Global state + routing
    │   ├── components/
    │   │   ├── FloodMap.jsx           # MapLibre GL map + layer composition
    │   │   ├── EvacuationPanel.jsx    # Algorithm stats + shelter list
    │   │   ├── ShelterLayer.jsx       # Shelter markers + flood detection
    │   │   ├── EvacuationLayer.jsx    # Route polylines + animated citizens
    │   │   ├── SimulateCitizenView.jsx  # Personal routing simulation UI
    │   │   ├── PanelOfExperts.jsx     # Multi-persona expert AI UI
    │   │   ├── AppCopilot.jsx         # Co-pilot chat interface
    │   │   ├── EvacuationChat.jsx     # Post-simulation Q&A
    │   │   ├── AlgoAnalysisPopup.jsx  # Algorithm benchmarking
    │   │   ├── RainfallPanel.jsx      # Rainfall date picker + intensity
    │   │   ├── PopulationPanel.jsx    # Population data explorer
    │   │   └── SheltersPanel.jsx      # Shelter data explorer
    │   └── hooks/useSimulation.js     # SSE lifecycle + event routing
    └── package.json
```

---

## Features

### Flood Simulation
- Physics-based hydrodynamic flood propagation using SRTM 30m elevation data
- Elevation-based water depth tracking across OpenStreetMap road graphs
- Historical + configurable rainfall injection (date picker + intensity slider)
- Real-time state streamed to frontend as GeoJSON via SSE

### AI Optimization (3 Competing Algorithms)
All three run in parallel and results are benchmarked head-to-head:

| Algorithm | Config | Key Mechanism |
|-----------|--------|---------------|
| **Genetic Algorithm (GA)** | 60 pop, 40 generations | Elite preservation (top 10%), 2-point crossover, tournament selection |
| **Ant Colony Optimization (ACO)** | 40 ants, 60 iterations | Pheromone matrix τ + heuristic η, vectorized NumPy scatter-add |
| **Particle Swarm Optimization (PSO)** | 40 particles, 60 iterations | Sigmoid velocity + probabilistic discrete shelter selection |

**Shared cost model:**
- Flood penalty: 5× per meter of water depth on edge
- Capacity overflow: 100,000 per excess person at shelter
- Traffic congestion: 3× edge cost multiplier (TomTom live data)

### Generative AI Layer

The GenAI layer is grounded entirely to live simulation state — LLMs never hallucinate shelter names or route distances because they call tools that read directly from MongoDB, which FastAPI writes to after every simulation run.

#### MCP Servers (FastMCP)

Two MCP servers expose simulation state as callable tools:

**`mcp_evacuation_server.py`** — Hard simulation data:

| Tool | What it returns |
|------|----------------|
| `get_simulation_state` | Algorithm used, success rate, evacuee counts, shelter overview |
| `get_shelter_status` | Per-shelter occupancy, capacity, fill %, severity (CRITICAL / HIGH / MODERATE) |
| `get_route_summary` | Total routes, people routed, avg/max distance, routes to critical shelters |
| `get_pressure_junctures` | Top bottlenecks: road name, converging evacuee volume, flood depth |
| `analyze_road_conditions` | Flood status of a specific road or top-5 bottlenecks |
| `narrate_best_route` | Lowest-distance evacuation route, optionally filtered by shelter name |
| `get_terrain_analysis` | Min/avg/max elevation from SRTM DEM for the loaded region |
| `get_rescue_guidelines` | NDRF protocols for unreachable individuals (boat, HCV, aerial) |
| `check_bus_availability` | Nearest BMTC bus stops + active routes for a lat/lon pin |
| `analyze_transit_disruptions` | Which BMTC routes go offline when a location floods |
| `identify_evacuation_hubs` | Top shelters by capacity with live occupancy for a named zone |
| `generate_evacuation_strategy` | Full Gemini-generated tactical plan: shelter redirections, route rebalancing, time-phased actions |
| `get_expert_analysis` | Calls the expert panel for logistics / tactical / civic persona advice |
| `ask_evacuation_question` | Free-form Q&A proxied to the evacuation chat endpoint |
| `get_realtime_weather` | Live rainfall (mm), temperature, and conditions for the current hobli |

**`mcp_flood_intelligence_server.py`** — Soft / situational intelligence:

| Tool | What it returns |
|------|----------------|
| `get_metro_status` | Per-line BMRC station health: unsafe/caution/safe counts, disruption %, CRITICAL/DEGRADED/OPERATIONAL |
| `get_flood_impact` | Population impact (initial vs evacuated vs stranded), flooded junctions and metro stations, severity tier |
| `get_shelter_resource_map` | Safe shelters mapped to nearby logistics (boats, medical, food, transport); identifies "Super-Hubs" |
| `get_vulnerability_hotspots` | High-density flooded zones with population > 50 and depth ≥ threshold; per-hotspot rescue action |

Both servers run over **stdio or SSE transport** and share state via MongoDB — FastAPI writes after simulation, MCP servers read on-demand. No local state files needed on any deployment.

#### App Co-pilot (`app_copilot.py`)

An agentic loop powered by **Gemini 2.5 Flash function calling** that drives the UI directly — it doesn't just answer questions, it takes actions:

- **Region selection**: Fuzzy-matches hobli/taluk names from natural language (e.g. "run Hebbal" → `select_region("Hebbal Hobli")`). Python-side difflib pre-check runs before the LLM call to avoid wasting tokens on obvious location lookups.
- **Parameter clarification**: If simulation params are incomplete, calls `ask_clarification` with clickable option buttons rendered in the frontend (algorithm, rainfall mm, traffic toggle, evacuation mode).
- **Simulation trigger**: Calls `run_simulation(hobli, algorithm, rainfall_mm, use_traffic, evacuation_mode)` once all params are resolved.
- **Map pin awareness**: If the user drops a pin on the map, the copilot receives `{lat, lon}` and automatically uses those coordinates for bus availability and transit queries.
- **Backend tool chain**: For crisis questions (shelter status, road conditions, metro disruptions, resource maps), the copilot calls the MCP tools directly in an agentic loop (up to 10 iterations), sending tool results back to Gemini until it produces a final text answer.
- **Fallback**: On Gemini rate limits (429), transparently falls back to **Groq Llama-3.3-70B** with the same tool schema translated to OpenAI function-calling format.

The co-pilot distinguishes two tool classes:
- **Backend tools** (MCP functions) → executed server-side, result fed back to the model
- **Frontend tools** (`select_region`, `navigate`, `run_simulation`, `ask_clarification`) → returned to the UI immediately for the React layer to act on

#### Expert Panel (`expert_panel.py`)

Three autonomous AI personas that generate independent, role-specific advisories from the same simulation context:

- **Logistics Chief** — Shelter capacity analysis, resource allocation, supply chain
- **Tactical Commander** — Route inspection, NDRF deployment instructions, bottleneck interventions
- **Civic Leader** — Government situation reports, public warnings, comms strategy

Each persona receives a structured context built by `context_builder.py` (shelter severity breakdown, route statistics, pressure junctures, algorithm comparison) and streams its response via SSE with Gemini 2.5 Flash.

#### Evacuation Chat (`evacuation_chat.py`)

Free-form Q&A interface where responders can ask anything about the current simulation — "Why is Hebbal School overloaded?", "Which route carries the most evacuees?", "What's the best path to the nearest shelter?" — answered using only grounded simulation data, streamed token-by-token via SSE.

### Real-time & Traffic
- TomTom Traffic API for live congestion-aware routing (parallel fetch via `ThreadPoolExecutor`)
- Metro station flood risk scoring with EMA smoothing + 2-hop neighborhood analysis
- Automated weather monitoring with alert dispatch

### Population & Shelter Modeling
- 2011 BBMP census + 15% growth projection, distributed by OSM node degree
- Shelter extraction from OSM amenities (schools, hospitals, town halls) with capacity assignment
- Per-shelter occupancy tracking + overflow penalties in routing

### Dual User Interfaces
- **Emergency Responder Dashboard**: Full simulation control, algorithm comparison, expert AI panel, authority notifications
- **Citizen Interface**: Personal routing simulation, real-time rerouting, evacuation chat

### Notifications
- Twilio SMS + Gmail SMTP for SOS alerts and evacuation plan broadcasts
- Role-based targeting (responder vs. citizen)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI + Uvicorn (async ASGI) |
| Database | MongoDB Atlas |
| Graph / GIS | OSMnx, NetworkX, Rasterio, Shapely, GeoPandas |
| AI optimization | NumPy-vectorized GA / ACO / PSO |
| GenAI | Gemini 2.5 Flash, Groq, Ollama via FastMCP |
| Traffic | TomTom Traffic API |
| Notifications | Twilio SMS, Gmail SMTP |
| Frontend | React 19, Vite 7, MapLibre GL 5, Tailwind CSS 4 |
| Charts | Recharts 3 |
| Routing | React Router 7 |
| Streaming | Server-Sent Events (SSE) |
| Auth | JWT + role-based access control |
| CI/CD | GitHub Actions → Google Cloud Run (asia-south1) |

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- MongoDB Atlas cluster
- API keys (see `.env` section below)

### Backend

```bash
cd UrbanFloodReact/backend
pip install -r ../../requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd UrbanFloodReact/frontend
npm install
npm run dev
```

> **Or just use the live deployment** — no setup needed:  
> [https://urbanflood-frontend-244754524479.asia-south1.run.app/](https://urbanflood-frontend-244754524479.asia-south1.run.app/)

### Environment Variables

Create a `.env` file in the project root:

```env
MONGO_URI=your_mongodb_atlas_uri
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
TOMTOM_API_KEY=your_tomtom_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
OPENTOPOGRAPHY_API_KEY=your_opentopo_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
```

### Access

- Backend API: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- Default credentials:
  - Admin: `admin / admin123`
  - Responder: `responder / resp123`

---

## Research Context

**Paper:** Digital Twin-Driven Flood Evacuation System Using AI Optimization

**Research gaps addressed:**
1. Bridging flood prediction to real-time actionable routing
2. Multi-algorithm benchmarking (GA vs ACO vs PSO) on a shared cost model
3. GenAI natural language grounding via MCP state sentinel
4. Congestion-aware evacuation planning in a unified platform
5. Agentic disaster advisory with live simulation grounding

---

## License

MIT License — see [LICENSE](LICENSE) for details.
