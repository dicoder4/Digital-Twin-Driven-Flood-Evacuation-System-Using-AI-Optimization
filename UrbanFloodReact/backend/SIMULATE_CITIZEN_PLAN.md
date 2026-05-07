# Simulate Citizen Feature — Comprehensive Plan
**Project:** Digital Twin Flood Evacuation System  
**Feature:** Simulate Person Mode — Test Flood Routing Without Real Rain  
**Date:** 2026-05-05  
**Depends on:** CITIZEN_NAVIGATION_PLAN.md (routing engine must exist first)

---

## Table of Contents
1. [What This Feature Is](#1-what-this-feature-is)
2. [Confirmed Data Available](#2-confirmed-data-available)
3. [Architecture](#3-architecture)
4. [Rainfall Simulation Engine](#4-rainfall-simulation-engine)
5. [Person Movement Simulation](#5-person-movement-simulation)
6. [Backend Implementation](#6-backend-implementation)
7. [Frontend Implementation](#7-frontend-implementation)
8. [File Change Table](#8-file-change-table)
9. [Build Order](#9-build-order)
10. [Feasibility Analysis](#10-feasibility-analysis)

---

## 1. What This Feature Is

### Problem
The citizen routing system can only be tested when it rains in Bengaluru and when the app is deployed live. That makes development and demonstration nearly impossible.

### Solution
A **Simulate Citizen** mode — accessible from the DRA/researcher dashboard and as a standalone demo login — that:

1. Lets a user **drop a person pin** anywhere on the Bengaluru map
2. Lets a user **click or search for a destination**
3. **Generates realistic rainfall** drawn from the historical dataset (4 months of Hobli-level data stored in MongoDB)
4. **Runs full flood physics + A* routing** on the corridor, just like a real citizen would get
5. **Animates the person moving** along the route at configurable speed (walking / car / emergency)
6. **Evolves rainfall over simulation time** — the storm intensifies, shifts, or dissipates — and **automatically reroutes** when flood conditions change, showing the new path on the map
7. **Shows route history** — previous routes are kept as faded lines so you can visually see how the route changed as the flood evolved

### Who Uses It
- **DRA/Authority users** — to demonstrate the system to stakeholders without needing real rain
- **Researchers** — to test routing under different flood scenarios
- **Demo login** — a "Simulate" demo button on the login page for live demos

### What Makes It Different from the Real Citizen Mode

| Aspect | Real Citizen Mode | Simulate Citizen Mode |
|---|---|---|
| Person location | GPS (browser) | Draggable pin on map |
| Rainfall source | Live KSNDMC API | Historical MongoDB data + evolution |
| Movement | Real user walking/driving | Animated interpolation at set speed |
| Time | Real time | Compressed simulation time (configurable) |
| Reroute trigger | Every 30s real time | Every N ticks of simulation clock |
| Purpose | Emergency navigation | Testing, demo, training |

---

## 2. Confirmed Data Available

### 2.1 Historical Rainfall — `rainfall_data` (MONGO_URI main DB)

4 documents, one per month:
```
month   : str  — "April", "May", "June", "July"
records : list — list of per-hobli daily records
```

Per record:
```
Date          : str   — "2052025" (DDMMYYYY format, e.g. 2052025 = 2 May 2025)
District      : str   — "BENGALURU URBAN"
Taluk         : str   — e.g. "Anekal", "Bangalore North"
Hobli         : str   — e.g. "Koramangala", "BTM Layout", "Anekal_1"
24h_Normal_mm : float — historical normal rainfall for this date
24h_Actual_mm : float — actual recorded rainfall (THIS IS WHAT WE USE)
24h_Dep_Pct   : float — % departure from normal
```

**Key insight:** `24h_Actual_mm` is 24-hour total. For simulation, we scale it:
- A "tick" = 5 simulated minutes
- Per-tick rainfall = `24h_Actual_mm / (24 * 12)` = mm per 5-minute period
- A heavy rain day (50mm/24h) = ~0.17mm per tick — realistic

**Coverage:** ~690 unique Hobli-date combinations per month. June and July have the heaviest actual rainfall — best for dramatic flood demos.

**Available distinct Hoblis in dataset:**
Anekal_1, Attibele_1, Jigani_1, Koramangala, BTM Layout, and ~60+ more covering all of Bengaluru Urban district.

### 2.2 Hobli Centroids — `hobli_coords` (MONGO_URI main DB)

106 documents:
```
hobli_name : str   — matches Hobli field in rainfall_data
latitude   : float
longitude  : float
type       : str
```

Used to map hobli rainfall → nearest graph nodes (same nearest-centroid haversine approach as ward mapping for live routing).

### 2.3 Shelter Cache — `shelter_cache` (MONGO_URI main DB)

4 documents, each with a `candidates` list of `{name, lat, lon}`. Currently only has test data (2 shelters). The simulation can use these + the proxy approach (high-elevation nearby nodes) from the citizen plan.

### 2.4 Historical Rainfall Statistics (derived, for random generation)

From the dataset we can pre-compute per-Hobli:
- Mean `24h_Actual_mm` across all dates → typical day
- Max `24h_Actual_mm` → worst-case flood event
- Month with highest rainfall → July (monsoon peak)

These stats drive the random rainfall generator — we don't invent values, we sample from the real distribution.

---

## 3. Architecture

### 3.1 Simulation State Machine

```
IDLE
  ↓ user drops person pin
PIN_PLACED
  ↓ user sets destination
DESTINATION_SET
  ↓ user clicks "Start Simulation"
SCENARIO_LOADING (fetch corridor + choose historical scenario)
  ↓
RUNNING ←──────────────────────────────────────────────────┐
  │                                                         │
  │ every tick (configurable: 1s real = 5min simulated):   │
  │   1. advance person position along route                │
  │   2. evolve rainfall (hobli values change)              │
  │   3. check reroute condition                            │
  │   4. if reroute: re-run A* → update route on map        │
  │   5. update rainfall heatmap overlay                    │
  └──────────────────────────────────────────────────────── ↑
  ↓ person reaches destination OR user clicks Stop
FINISHED
```

### 3.2 Request Flow During Simulation

```
[Frontend — Simulate Panel]
        │
        │ 1. Drop pin + set destination
        ↓
POST /simulate/start
  → fetch corridor from MongoDB (same as citizen route)
  → pick historical scenario (random date from rainfall_data)
  → run corridor flood + A* routing
  → return: route + initial rainfall snapshot + scenario metadata
        │
        │ 2. Every tick (client-side timer):
        ↓
POST /simulate/tick
  → evolve rainfall (advance storm by one step)
  → check if active hobli rainfall changed > threshold
  → if yes: re-run A* from current simulated position
  → return: evolved rainfall map + new route (if rerouted) + person's new position
        │
        │ 3. Frontend renders:
        ↓
  → Move person marker along route path (smooth interpolation)
  → Update MapLibre rainfall heatmap layer
  → If rerouted: draw new route + keep old as faded history
  → Update stats panel (time elapsed, distance covered, flood risk)
```

### 3.3 Simulation Time Model

```
real_seconds_per_tick  : configurable (default: 2s)
simulated_mins_per_tick: configurable (default: 5 min)
speed_mode             : "walk" (4 km/h) | "car" (30 km/h) | "emergency" (60 km/h)

distance_per_tick_m = speed_kph / 60 * simulated_mins_per_tick * 1000
  walk:      4/60 * 5 * 1000 = 333m per tick
  car:      30/60 * 5 * 1000 = 2500m per tick
  emergency: 60/60 * 5 * 1000 = 5000m per tick
```

---

## 4. Rainfall Simulation Engine

### 4.1 Scenario Selection

When simulation starts, the backend picks a **historical scenario**:

```python
def pick_scenario(month: str = None, intensity: str = "random") -> dict:
    """
    intensity: "light" | "moderate" | "heavy" | "extreme" | "random"
    Returns a snapshot: { hobli_name: mm_per_tick }
    """
    # 1. Choose month
    if month is None:
        month = random.choice(["May", "June", "July"])  # monsoon months

    # 2. Fetch all records for that month from MongoDB
    records = db.rainfall_data.find_one({"month": month})["records"]

    # 3. Filter by intensity
    intensity_ranges = {
        "light":    (0,  10),
        "moderate": (10, 30),
        "heavy":    (30, 60),
        "extreme":  (60, 200),
    }
    if intensity == "random":
        min_mm, max_mm = 0, 200
    else:
        min_mm, max_mm = intensity_ranges[intensity]

    filtered = [
        r for r in records
        if min_mm <= float(r.get("24h_Actual_mm", 0)) <= max_mm
    ]
    if not filtered:
        filtered = records  # fallback

    # 4. Pick a random date from filtered records
    target_date = random.choice(filtered)["Date"]
    date_records = [r for r in records if r["Date"] == target_date]

    # 5. Build hobli → mm_per_tick mapping
    # Scale 24h total to per-tick (5-minute) amount
    TICK_SCALE = 1 / (24 * 12)   # 24h / (12 ticks per hour)
    return {
        r["Hobli"]: float(r.get("24h_Actual_mm", 0)) * TICK_SCALE
        for r in date_records
    }, target_date, month
```

### 4.2 Rainfall Evolution (Storm Progression)

After each tick, the rainfall evolves to simulate a moving storm:

```python
def evolve_rainfall(
    current_snapshot: dict,      # { hobli: mm_per_tick }
    hobli_coords: dict,          # { hobli: (lat, lon) }
    tick: int,
    mode: str = "intensify",     # "intensify" | "dissipate" | "move" | "random"
) -> dict:
    """
    Evolves the rainfall snapshot by one tick.
    
    Modes:
      intensify : rainfall ramps up 5% per tick (storm building)
      dissipate : rainfall drops 8% per tick (storm ending)  
      move      : rainfall shifts spatially (storm cell moving NE at ~20 km/h)
      random    : random walk ±15% per hobli each tick
    """
    new_snapshot = {}

    if mode == "intensify":
        for hobli, mm in current_snapshot.items():
            new_snapshot[hobli] = min(mm * 1.05, 5.0)  # cap at 5mm/tick = 60mm/h

    elif mode == "dissipate":
        for hobli, mm in current_snapshot.items():
            new_snapshot[hobli] = max(mm * 0.92, 0.0)

    elif mode == "move":
        # Shift storm cell NE: increase rainfall for hoblis to the NE,
        # decrease for hoblis to the SW
        storm_center = _compute_storm_center(current_snapshot, hobli_coords)
        move_lat = 0.002 * tick  # ~0.2km per tick northward
        move_lon = 0.002 * tick  # ~0.2km per tick eastward
        new_center = (storm_center[0] + move_lat, storm_center[1] + move_lon)
        for hobli, (hlat, hlon) in hobli_coords.items():
            dist_to_new = _haversine(hlat, hlon, *new_center)
            intensity = max(0, 1 - dist_to_new / 10000)  # falloff over 10km
            base = current_snapshot.get(hobli, 0)
            new_snapshot[hobli] = base * 0.7 + intensity * 2.0  # blend

    elif mode == "random":
        import random
        for hobli, mm in current_snapshot.items():
            factor = random.gauss(1.0, 0.15)  # ±15% standard deviation
            new_snapshot[hobli] = max(0, mm * factor)

    return new_snapshot

def _compute_storm_center(snapshot, hobli_coords):
    """Weighted centroid of rainfall — where is the heaviest rain?"""
    total_rain = sum(snapshot.values()) or 1
    lat = sum(hobli_coords[h][0] * mm for h, mm in snapshot.items() if h in hobli_coords) / total_rain
    lon = sum(hobli_coords[h][1] * mm for h, mm in snapshot.items() if h in hobli_coords) / total_rain
    return lat, lon
```

### 4.3 Reroute Condition During Simulation

Same logic as real citizen mode, but with a lower threshold (simulation is more sensitive for demo purposes):

```python
REROUTE_THRESHOLD_MM_PER_TICK = 0.5  # any hobli changes by 0.5mm/tick → reroute

def should_reroute(old_snapshot, new_snapshot, active_hoblis):
    for hobli in active_hoblis:
        old = old_snapshot.get(hobli, 0)
        new = new_snapshot.get(hobli, 0)
        if abs(new - old) >= REROUTE_THRESHOLD_MM_PER_TICK:
            return True, hobli
    return False, None
```

---

## 5. Person Movement Simulation

### 5.1 Path Interpolation

The route is a list of graph nodes. Each node has `(lat, lon)`. The person's position is interpolated along the path based on distance covered per tick.

```python
class PersonPosition:
    def __init__(self, path_nodes: list, G: nx.DiGraph, speed_kph: float, tick_mins: float):
        self.path_nodes = path_nodes
        self.G = G
        self.speed_kph = speed_kph
        self.tick_mins = tick_mins
        self.current_edge_idx = 0     # which edge in path are we on
        self.edge_progress = 0.0      # 0.0–1.0 progress along current edge

    def advance(self) -> tuple[float, float]:
        """Move person by one tick. Returns (lat, lon) of new position."""
        dist_to_cover = (self.speed_kph / 60) * self.tick_mins * 1000  # metres

        while dist_to_cover > 0 and self.current_edge_idx < len(self.path_nodes) - 1:
            u = self.path_nodes[self.current_edge_idx]
            v = self.path_nodes[self.current_edge_idx + 1]
            edge_len = self.G[u][v]["length"]
            remaining_on_edge = edge_len * (1 - self.edge_progress)

            if dist_to_cover >= remaining_on_edge:
                dist_to_cover -= remaining_on_edge
                self.current_edge_idx += 1
                self.edge_progress = 0.0
            else:
                self.edge_progress += dist_to_cover / edge_len
                dist_to_cover = 0

        return self._interpolate_position()

    def _interpolate_position(self) -> tuple[float, float]:
        if self.current_edge_idx >= len(self.path_nodes) - 1:
            n = self.G.nodes[self.path_nodes[-1]]
            return n["lat"], n["lon"]
        u = self.path_nodes[self.current_edge_idx]
        v = self.path_nodes[self.current_edge_idx + 1]
        nu, nv = self.G.nodes[u], self.G.nodes[v]
        t = self.edge_progress
        return (
            nu["lat"] + t * (nv["lat"] - nu["lat"]),
            nu["lon"] + t * (nv["lon"] - nu["lon"]),
        )

    def current_node(self) -> int:
        return self.path_nodes[min(self.current_edge_idx, len(self.path_nodes) - 1)]

    def is_arrived(self) -> bool:
        return self.current_edge_idx >= len(self.path_nodes) - 1
```

### 5.2 State Stored Per Session

All simulation state is stored **server-side** keyed by `session_id` so that each tick call is stateless from the frontend's perspective:

```python
# In-memory session store (dict in simulate_routes.py)
SIMULATE_SESSIONS: dict[str, SimulationSession] = {}

class SimulationSession:
    session_id:      str
    G:               nx.DiGraph        # corridor graph (kept in memory)
    path_nodes:      list[int]         # current route
    position:        PersonPosition    # movement state
    rainfall:        dict              # current { hobli: mm_per_tick }
    hobli_coords:    dict              # { hobli: (lat, lon) }
    active_hoblis:   list[str]         # hoblis on current route
    route_history:   list[dict]        # previous routes as GeoJSON (for faded overlay)
    tick:            int               # simulation step counter
    evolution_mode:  str               # "intensify" | "dissipate" | "move" | "random"
    speed_kph:       float
    tick_mins:       float             # simulated minutes per real tick
    dst_lat:         float
    dst_lon:         float
    scenario_date:   str
    scenario_month:  str
```

Sessions are evicted after 2 hours of inactivity (simple `last_accessed` timestamp check).

---

## 6. Backend Implementation

### 6.1 New File: `backend/simulate_routes.py`

FastAPI APIRouter mounted at `/simulate`.

---

#### `POST /simulate/start`

```python
class SimulateStartRequest(BaseModel):
    src_lat:        float
    src_lon:        float
    dst_lat:        float
    dst_lon:        float
    speed_mode:     str = "car"          # "walk" | "car" | "emergency"
    intensity:      str = "random"       # "light"|"moderate"|"heavy"|"extreme"|"random"
    month:          str | None = None    # None = random monsoon month
    evolution_mode: str = "random"       # "intensify"|"dissipate"|"move"|"random"
    tick_mins:      float = 5.0          # simulated minutes per tick
```

**Response:**
```json
{
  "session_id": "uuid4",
  "route_geojson": { "type": "FeatureCollection", "features": [...] },
  "steps": [...],
  "initial_rainfall": { "Koramangala": 0.14, "BTM Layout": 0.22, ... },
  "rainfall_heatmap": [
    { "lat": 12.93, "lon": 77.62, "intensity": 0.14, "hobli": "Koramangala" }
  ],
  "scenario": { "date": "2052025", "month": "May", "evolution_mode": "random" },
  "person_position": { "lat": 12.935, "lon": 77.732 },
  "summary": { "total_distance_m": 1840, "eta_minutes": 4, "safe": true },
  "active_hoblis": ["Koramangala", "BTM Layout"],
  "tick": 0,
  "arrived": false
}
```

**Logic:**
1. `fetch_corridor(src_lat, src_lon, dst_lat, dst_lon)` → edges, nodes
2. `build_graph(edges, nodes)` → G
3. Fetch `hobli_coords` from MONGO_URI main DB
4. `pick_scenario(month, intensity)` → initial `rainfall_snapshot`
5. Map hoblis to graph nodes: `assign_hoblis_to_nodes(G, hobli_coords)`
6. `compute_flood(G, rainfall_as_mm, hobli_for_node)` → annotate depths
   - Note: rainfall_snapshot is in mm/tick; convert to mm/hour for flood physics:
     `mm_per_hour = mm_per_tick * (60 / tick_mins)`
7. `astar_route(G, src_node, dst_node)` → path
8. Create `SimulationSession`, store in `SIMULATE_SESSIONS[session_id]`
9. Return full response

---

#### `POST /simulate/tick`

```python
class SimulateTickRequest(BaseModel):
    session_id: str
```

**Response:**
```json
{
  "session_id": "uuid4",
  "tick": 7,
  "person_position": { "lat": 12.942, "lon": 77.738 },
  "current_rainfall": { "Koramangala": 0.18, "BTM Layout": 0.31 },
  "rainfall_heatmap": [...],
  "rerouted": true,
  "reroute_reason": "Rainfall increased in BTM Layout",
  "route_geojson": { ... },
  "route_history_geojson": [...],
  "steps": [...],
  "current_step_idx": 3,
  "summary": { "total_distance_m": 1200, "eta_minutes": 3, "safe": true },
  "arrived": false,
  "warning": null
}
```

**Logic:**
1. Load session from `SIMULATE_SESSIONS`
2. `position.advance()` → new `(lat, lon)`, check `is_arrived()`
3. `evolve_rainfall(session.rainfall, hobli_coords, tick, evolution_mode)` → new rainfall
4. `should_reroute(old_rainfall, new_rainfall, active_hoblis)` → bool
5. If reroute needed:
   - Save current `route_geojson` to `session.route_history` (max 5 kept)
   - Recompute flood on updated graph
   - Re-run A* from `position.current_node()` to `dst_node`
   - Update `session.path_nodes`, reset `position.current_edge_idx` and `edge_progress`
6. Increment `session.tick`
7. Return response

---

#### `POST /simulate/reset`

```python
class SimulateResetRequest(BaseModel):
    session_id: str
```

Clears the session from `SIMULATE_SESSIONS`. Frontend calls this when user clicks "Reset" or leaves.

---

#### `GET /simulate/scenarios`

Returns available scenario options derived from the historical dataset:

```json
{
  "months": ["April", "May", "June", "July"],
  "intensities": ["light", "moderate", "heavy", "extreme", "random"],
  "evolution_modes": ["intensify", "dissipate", "move", "random"],
  "speed_modes": [
    { "key": "walk",      "label": "Walking (4 km/h)",       "km_h": 4  },
    { "key": "car",       "label": "Car (30 km/h)",          "km_h": 30 },
    { "key": "emergency", "label": "Emergency (60 km/h)",    "km_h": 60 }
  ],
  "sample_heavy_dates": ["2072025", "15062025"]
}
```

---

#### `GET /simulate/rainfall-stats`

Pre-computes and returns per-hobli statistics from the historical dataset (used to set realistic heatmap colour scale):

```json
{
  "max_24h_mm": 87.4,
  "avg_24h_mm": 12.3,
  "hobli_maxes": { "Koramangala": 45.2, "BTM Layout": 38.7, ... }
}
```

---

### 6.2 Hobli → Node Mapping (for simulation)

Unlike the ward-based approach for live routing, simulation uses Hobli centroids directly:

```python
async def fetch_hobli_coords() -> dict:
    """Returns { hobli_name: (lat, lon) } from hobli_coords collection."""
    db = get_main_db()  # MONGO_URI
    docs = await db.hobli_coords.find({}, {"_id":0,"hobli_name":1,"latitude":1,"longitude":1}).to_list(200)
    return { d["hobli_name"]: (float(d["latitude"]), float(d["longitude"])) for d in docs }

def assign_hoblis_to_nodes(G: nx.DiGraph, hobli_coords: dict) -> dict:
    """
    For each node in G, find nearest hobli centroid.
    Returns { node_id: hobli_name }.
    Same haversine approach as assign_wards_to_nodes() in rainfall_service.py.
    """
```

---

### 6.3 Rainfall Unit Conversion

The historical data is in `24h_mm` but the flood physics expects `mm` as a total accumulation input. The conversion bridge:

```python
def scenario_to_flood_input(rainfall_snapshot: dict, tick_mins: float) -> dict:
    """
    Convert mm/tick to mm/hour for flood physics.
    The flood simulator uses mm as an intensity input —
    higher mm = more water depth on edges.
    """
    ticks_per_hour = 60.0 / tick_mins
    return {
        hobli: mm_per_tick * ticks_per_hour
        for hobli, mm_per_tick in rainfall_snapshot.items()
    }
```

---

## 7. Frontend Implementation

### 7.1 Access Points

**Access Point A — DRA Sidebar button:**
In `DraSidebar.jsx`, add a "Simulate Citizen" button that opens `SimulateCitizenPanel` as an overlay.

**Access Point B — Demo Login:**
A fourth demo button on `LoginPage.jsx`: "Simulate" → logs in as `simulate` role → renders `SimulateCitizenView` directly.

**Access Point C — Researcher toolbar:**
A "Simulate" icon button in the researcher toolbar.

### 7.2 New File: `frontend/src/components/SimulateCitizenView.jsx`

**State variables:**
```jsx
const [simPhase, setSimPhase]           = useState('IDLE')
// IDLE | PIN_PLACED | DESTINATION_SET | LOADING | RUNNING | PAUSED | FINISHED

const [personPin, setPersonPin]         = useState(null)   // {lat, lon}
const [destination, setDestination]    = useState(null)   // {lat, lon, label}
const [sessionId, setSessionId]        = useState(null)
const [sessionData, setSessionData]    = useState(null)   // full /simulate/start response
const [personPos, setPersonPos]        = useState(null)   // {lat, lon} — animated
const [routeHistory, setRouteHistory]  = useState([])    // [{geojson, tick}] max 5
const [rainfall, setRainfall]          = useState({})    // current hobli rainfall
const [heatmap, setHeatmap]            = useState([])    // [{lat,lon,intensity}]
const [rerouted, setRerouted]          = useState(false)
const [rerouteMsg, setRerouteMsg]      = useState(null)
const [tick, setTick]                  = useState(0)
const [stats, setStats]                = useState(null)
const [arrived, setArrived]            = useState(false)

// Config
const [speedMode, setSpeedMode]        = useState('car')
const [intensity, setIntensity]        = useState('random')
const [month, setMonth]                = useState(null)
const [evolutionMode, setEvolutionMode]= useState('random')
const [tickIntervalMs, setTickIntervalMs] = useState(2000)  // 2s real = 5min simulated

const tickTimerRef = useRef(null)
```

**Map interaction — dropping pins:**
```jsx
const handleMapClick = useCallback((e) => {
  const { lat, lng } = e.lngLat;
  if (simPhase === 'IDLE') {
    setPersonPin({ lat, lon: lng });
    setSimPhase('PIN_PLACED');
  } else if (simPhase === 'PIN_PLACED') {
    setDestination({ lat, lon: lng, label: `${lat.toFixed(4)}, ${lng.toFixed(4)}` });
    setSimPhase('DESTINATION_SET');
  }
}, [simPhase]);
```

**Start simulation:**
```jsx
const handleStart = async () => {
  setSimPhase('LOADING');
  const res = await fetch('/simulate/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      src_lat: personPin.lat, src_lon: personPin.lon,
      dst_lat: destination.lat, dst_lon: destination.lon,
      speed_mode: speedMode, intensity, month,
      evolution_mode: evolutionMode, tick_mins: 5.0,
    })
  }).then(r => r.json());

  setSessionId(res.session_id);
  setSessionData(res);
  setPersonPos(res.person_position);
  setRainfall(res.initial_rainfall);
  setHeatmap(res.rainfall_heatmap);
  setStats(res.summary);
  setSimPhase('RUNNING');
  startTickLoop(res.session_id);
};
```

**Tick loop:**
```jsx
const startTickLoop = (sid) => {
  tickTimerRef.current = setInterval(async () => {
    const res = await fetch('/simulate/tick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sid })
    }).then(r => r.json());

    setPersonPos(res.person_position);
    setRainfall(res.current_rainfall);
    setHeatmap(res.rainfall_heatmap);
    setTick(res.tick);
    setStats(res.summary);

    if (res.rerouted) {
      setRouteHistory(prev => [...prev.slice(-4), {
        geojson: sessionData.route_geojson,
        tick: res.tick
      }]);
      setSessionData(prev => ({ ...prev, route_geojson: res.route_geojson }));
      setRerouted(true);
      setRerouteMsg(res.reroute_reason);
      setTimeout(() => setRerouted(false), 4000);
    }

    if (res.arrived) {
      clearInterval(tickTimerRef.current);
      setSimPhase('FINISHED');
      setArrived(true);
    }
  }, tickIntervalMs);
};
```

**Pause/Resume:**
```jsx
const handlePause = () => {
  clearInterval(tickTimerRef.current);
  setSimPhase('PAUSED');
};
const handleResume = () => {
  setSimPhase('RUNNING');
  startTickLoop(sessionId);
};
```

---

### 7.3 UI Layout

```
┌─────────────────────────────────────────────────────┐
│  TOP BAR (fixed)                                    │
│  [⚡ Simulate Citizen]  Tick: 7  Time: 35min elapsed │
│  [⏸ Pause] [🔄 Reset]  Speed: Car  Storm: Intensify │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                                                     │
│   FULL MAP (MapLibre)                               │
│                                                     │
│   [Person pin 🚶/🚗 — animated moving]             │
│   [Destination pin 📍]                             │
│   [Current route — colour-coded flood risk]        │
│   [Route history — 3 faded grey lines]             │
│   [Rainfall heatmap — blue to red overlay]         │
│   [Flood depth on roads — coloured edges]          │
│                                                     │
│   Phase IDLE: "Click map to drop person"           │
│   Phase PIN_PLACED: "Now click destination"        │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  BOTTOM PANEL (collapsible, 220px)                  │
│                                                     │
│  CONFIGURATION (shown before start):               │
│  Month:    [May ▼]    Intensity: [Heavy ▼]         │
│  Storm:    [Intensify ▼]  Speed: [Car ▼]           │
│  [▶ Start Simulation]                              │
│                                                     │
│  STATS (shown during RUNNING):                     │
│  Distance remaining: 1.2km  │  ETA: 2 min          │
│  Current flood risk: 🟡 MEDIUM                     │
│  Max depth on route: 0.34m                         │
│  Reroutes so far: 2                                │
│  ┌─────────────────────────────┐                   │
│  │ 🔴 Rerouted! BTM Layout     │  ← flash 4s       │
│  │    rainfall jumped +0.8mm  │                   │
│  └─────────────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

---

### 7.4 New File: `frontend/src/components/SimulateRainfallLayer.jsx`

MapLibre heatmap layer showing live rainfall intensity per hobli centroid:

```jsx
// Uses MapLibre's built-in heatmap layer type
// Source: GeoJSON FeatureCollection of hobli centroids with 'intensity' property

<Source id="rainfall-heat" type="geojson" data={heatmapGeoJSON}>
  <Layer
    id="rainfall-heatmap"
    type="heatmap"
    paint={{
      'heatmap-weight':    ['interpolate', ['linear'], ['get', 'intensity'], 0, 0, 5, 1],
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 10, 1, 15, 3],
      'heatmap-color': [
        'interpolate', ['linear'], ['heatmap-density'],
        0,   'rgba(0,0,255,0)',    // transparent
        0.2, 'rgba(0,100,255,0.3)', // light blue
        0.5, 'rgba(255,165,0,0.5)', // orange
        0.8, 'rgba(255,0,0,0.7)',   // red
        1.0, 'rgba(139,0,0,0.9)',   // dark red
      ],
      'heatmap-radius':   ['interpolate', ['linear'], ['zoom'], 10, 30, 15, 80],
      'heatmap-opacity':  0.7,
    }}
  />
</Source>
```

### 7.5 New File: `frontend/src/components/SimulateRouteLayer.jsx`

Renders current route + faded route history:

```jsx
// Route history: faded grey lines
{routeHistory.map((r, i) => (
  <Source key={i} id={`history-${i}`} type="geojson" data={r.geojson}>
    <Layer
      id={`history-line-${i}`}
      type="line"
      paint={{
        'line-color': '#9ca3af',
        'line-width': 2,
        'line-opacity': 0.2 + (i / routeHistory.length) * 0.3,
        'line-dasharray': [4, 3],
      }}
    />
  </Source>
))}

// Current route: flood-risk colour-coded (same as CitizenRouteLayer)
// Person marker: animated 🚗/🚶 marker that smoothly moves each tick
```

### 7.6 Person Marker Animation

Smooth movement between tick positions using CSS transition:

```jsx
// PersonMarker.jsx
<Marker longitude={personPos.lon} latitude={personPos.lat}>
  <div
    style={{
      transition: `transform ${tickIntervalMs * 0.8}ms ease-in-out`,
      fontSize: '24px',
    }}
  >
    {speedMode === 'walk' ? '🚶' : speedMode === 'emergency' ? '🚨' : '🚗'}
  </div>
</Marker>
```

The marker's position updates every tick, and CSS handles the smooth visual interpolation between positions.

---

### 7.7 Control Panel — Speed & Tick Rate Slider

```jsx
// In SimulateCitizenView.jsx bottom panel
<div className="sim-controls">
  <label>Simulation Speed</label>
  <input type="range" min={500} max={5000} step={500}
    value={tickIntervalMs}
    onChange={e => {
      setTickIntervalMs(+e.target.value);
      if (simPhase === 'RUNNING') {
        clearInterval(tickTimerRef.current);
        startTickLoop(sessionId);  // restart with new interval
      }
    }}
  />
  <span>{tickIntervalMs/1000}s per tick (= 5 sim-min)</span>
</div>
```

---

### 7.8 Login Page — 4th Demo Button

```jsx
<button onClick={() => handleDemoLogin('simulate')} className="demo-btn simulate-demo">
  <div className="demo-icon"><Zap size={18} color="#7c3aed" /></div>
  <div>
    <span className="demo-role">Simulate</span>
    <span className="demo-sub">Test flood routing</span>
  </div>
</button>
```

---

## 8. File Change Table

### New Backend Files

| # | File | What |
|---|---|---|
| 1 | `backend/simulate_routes.py` | FastAPI router: `/simulate/start`, `/simulate/tick`, `/simulate/reset`, `/simulate/scenarios`, `/simulate/rainfall-stats` |
| 2 | `backend/simulation_engine.py` | `pick_scenario()`, `evolve_rainfall()`, `should_reroute()`, `scenario_to_flood_input()`, `fetch_hobli_coords()`, `assign_hoblis_to_nodes()`, `SIMULATE_SESSIONS` store, `SimulationSession` dataclass, `PersonPosition` class |

### New Frontend Files

| # | File | What |
|---|---|---|
| 3 | `frontend/src/components/SimulateCitizenView.jsx` | Main simulation UI, state machine, tick loop, config panel |
| 4 | `frontend/src/components/SimulateRainfallLayer.jsx` | MapLibre heatmap of live rainfall per hobli |
| 5 | `frontend/src/components/SimulateRouteLayer.jsx` | Current route + faded history lines |
| 6 | `frontend/src/components/PersonMarker.jsx` | Animated person marker (🚗/🚶/🚨) |

### Modified Files

| # | File | Change |
|---|---|---|
| 7 | `backend/main.py` | Mount simulate router |
| 8 | `backend/auth_routes.py` | Add `simulate` role to DEMO_USERS |
| 9 | `frontend/src/App.jsx` | Add `isSimulateMode = user?.role === 'simulate'` + early return to `<SimulateCitizenView>` |
| 10 | `frontend/src/pages/LoginPage.jsx` | 4th demo button (Simulate/purple) |
| 11 | `frontend/src/App.css` | Simulation panel styles, animation, heatmap legend |

**Total: 6 new files, 5 modified files.**

---

## 9. Build Order

```
DAY 1 — Simulation Engine (backend, no HTTP)
  Step 1: simulation_engine.py
    - fetch_hobli_coords() — verify hobli_coords collection returns correct centroids
    - pick_scenario() — test with month="July", intensity="heavy"
    - print: { "Koramangala": 0.14, "BTM_Layout": 0.22, ... }

  Step 2: pick_scenario integration with flood pipeline
    - scenario_to_flood_input() conversion
    - Full test: pick scenario → assign hoblis to nodes → compute_flood → check depths
    - Use month=July (heaviest rain) and verify non-zero depths appear

  Step 3: evolve_rainfall() — test all 4 modes
    - "intensify": all values increase
    - "dissipate": all values decrease
    - "move": heavy area shifts spatially
    - "random": values random-walk ±15%

  Step 4: PersonPosition class
    - Test: build small path (5 nodes), advance() 10 times, verify position moves
    - Test: is_arrived() returns True after sufficient advances

  Step 5: should_reroute() — unit test
    - Same rainfall → False
    - Any hobli changes by 0.5 mm/tick → True

DAY 2 — Simulation API (backend)
  Step 6: simulate_routes.py — all 5 endpoints
  Step 7: Mount in main.py + auth changes (simulate role)
  Step 8: Curl test /simulate/start:
    curl -X POST http://localhost:8000/simulate/start \
      -H "Content-Type: application/json" \
      -d '{"src_lat":12.935,"src_lon":77.732,"dst_lat":12.960,"dst_lon":77.740,
           "speed_mode":"car","intensity":"heavy","month":"July","evolution_mode":"intensify"}'
    Expected: session_id, route_geojson, initial_rainfall with non-zero values

  Step 9: Curl test /simulate/tick 5 times:
    curl -X POST http://localhost:8000/simulate/tick \
      -H "Content-Type: application/json" \
      -d '{"session_id":"<from above>"}'
    Expected: person_position changes, rainfall changes, rerouted=true at some point

DAY 3 — Frontend Shell
  Step 10: LoginPage.jsx — 4th demo button (simulate)
  Step 11: App.jsx — isSimulateMode + placeholder SimulateCitizenView
  Step 12: Test: login as simulate → see placeholder

DAY 4 — Frontend Core
  Step 13: SimulateCitizenView.jsx — IDLE + PIN_PLACED + DESTINATION_SET phases
    - Map click drops pins
    - Config panel appears

  Step 14: LOADING + RUNNING phases
    - /simulate/start call on button click
    - Tick loop runs, person_pos updates

  Step 15: PersonMarker.jsx — animated marker on map

  Step 16: SimulateRouteLayer.jsx — route renders, history fades in

DAY 5 — Rainfall Heatmap + Polish
  Step 17: SimulateRainfallLayer.jsx — MapLibre heatmap
  Step 18: Reroute banner animation
  Step 19: Stats panel (distance, ETA, reroute count)
  Step 20: Speed slider — real-time tick interval change
  Step 21: Pause/Resume/Reset flow
  Step 22: FINISHED state (person arrives)

DAY 6 — Testing
  Step 23: Demo run with July + extreme intensity → verify reroutes occur
  Step 24: Test all 3 speed modes (walk/car/emergency)
  Step 25: Test all 4 evolution modes
  Step 26: Test reset + restart
  Step 27: Verify route history shows max 5 faded lines
  Step 28: Mobile viewport test (375px)
```

---

## 10. Feasibility Analysis

### 10.1 Technical Feasibility

| Component | Feasibility | Confidence | Notes |
|---|---|---|---|
| Historical rainfall data | ✅ HIGH | 100% | Confirmed in `rainfall_data` MongoDB collection. May, June, July, April data. ~2070 records per month. |
| Hobli centroid mapping | ✅ HIGH | 100% | `hobli_coords` collection confirmed with 106 hobli centroids. Direct lat/lon available. |
| Routing engine reuse | ✅ HIGH | 100% | `_compute_route()` from citizen plan is 100% reusable. Simulation just passes different rainfall. |
| Server-side session state | ✅ HIGH | 95% | In-memory dict `SIMULATE_SESSIONS` keyed by UUID. Works for single-server deployment. Multi-server needs Redis (future). |
| Person movement interpolation | ✅ HIGH | 90% | Pure math — haversine + linear interpolation on path nodes. Well-understood problem. |
| Storm evolution logic | ✅ HIGH | 90% | 4 modes, all simple math. No ML, no external calls. |
| MapLibre heatmap layer | ✅ HIGH | 90% | Built-in MapLibre layer type. Already proven in the existing app's flood layers. |
| Animated person marker | ✅ HIGH | 90% | CSS transitions handle smooth movement between tick positions. |
| Rerouting during simulation | ✅ HIGH | 95% | Reuses `/citizen/location-update` logic. Threshold-based, deterministic. |
| Route history overlay | ✅ HIGH | 90% | Store last N GeoJSON responses, render as faded layers. Standard MapLibre pattern. |
| Hobli name matching (data → coords) | ⚠️ MEDIUM | 70% | Historical `rainfall_data` uses names like "Anekal_1", "BTM Layout". `hobli_coords` uses different naming convention. Need fuzzy/exact match alignment. |

### 10.2 Hobli Name Mismatch — The Main Risk

The historical data has hobli names like `"Anekal_1"`, `"Jigani_1"` (with suffixes), while `hobli_coords` has names like `"Anekal"`, `"Jigani"`. There will be ~20–30% name mismatches.

**Mitigation:**
```python
def normalize_hobli_name(name: str) -> str:
    """Strip trailing _1, _2 etc. and lowercase for matching."""
    import re
    return re.sub(r'_\d+$', '', name).strip().lower()

# Build lookup with normalized keys:
hobli_lookup = {
    normalize_hobli_name(hobli): coords
    for hobli, coords in hobli_coords.items()
}
```

This should resolve ~90% of mismatches. Remaining unmatched hoblis get the city centroid as fallback (12.9716, 77.5946).

### 10.3 Performance Feasibility

| Operation | Estimated Time | Acceptable? |
|---|---|---|
| /simulate/start (cold corridor) | 2–4s | ✅ One-time cost at session start |
| /simulate/tick (warm graph) | 30–80ms | ✅ Tick every 2s — plenty of headroom |
| evolve_rainfall() | < 5ms | ✅ Simple arithmetic |
| PersonPosition.advance() | < 1ms | ✅ Pure Python math |
| Re-run A* on reroute | 5–30ms | ✅ Graph already in memory |
| MapLibre heatmap render | < 16ms | ✅ GPU-accelerated |

The tick pipeline is: evolve → reroute check → maybe A* → return JSON. Under 100ms total. Well within a 2-second tick interval.

### 10.4 Free-Tier Cost Analysis

| Resource | Simulation Cost | Notes |
|---|---|---|
| MongoDB MONGO_URI2 | 1 query at session start | Corridor fetch only once — graph held in server memory |
| MongoDB MONGO_URI | 1 query at session start | `hobli_coords` + `rainfall_data` fetched once per session |
| KSNDMC | 0 | Not used in simulation |
| Nominatim | 0 | Destination set by map click (no geocoding needed) |
| TomTom | 0 | Not used |
| AI (Gemini/Groq) | 0 | Not used |
| Server RAM | ~50MB per active session | NetworkX graph for corridor: ~5MB. Manageable for ≤10 concurrent sessions. |

**The simulation is entirely free to run.** All data is already in MongoDB. All computation is local Python.

### 10.5 Simulation vs Reality — Accuracy

| Aspect | Accuracy | Notes |
|---|---|---|
| Flood depths | Approximate | Steady-state model, not full hydrodynamic simulation. Depths are directionally correct, not physically precise. |
| Rainfall values | Real historical | Drawn from actual KSNDMC records — realistic magnitudes. |
| Storm evolution | Parameterized | "Intensify", "dissipate", "move" are simplified models. Real storms are more complex. |
| Routing quality | High | A* on real road network with real elevation. Routing decisions are physically grounded. |
| Person speed | Configurable | 4/30/60 km/h are realistic for walk/car/emergency. |

**The simulation is accurate enough for system demonstration and testing.** It is not a scientific flood model — it is a routing test harness with realistic inputs.

### 10.6 What This Feature Enables

1. **Development testing** — developers can test rerouting logic without waiting for rain
2. **Stakeholder demos** — show the system working during dry-season meetings
3. **Training** — BBMP officers can learn the system before a real flood event
4. **Scenario planning** — test "what if a heavy storm hits Koramangala" routing behaviour
5. **Research** — compare routing outcomes across different storm intensities

### 10.7 Summary Verdict

| Question | Answer |
|---|---|
| Is it feasible? | **Yes — highly feasible** |
| Does it require new data? | **No — all data already exists in MongoDB** |
| Does it require paid APIs? | **No — zero external API calls** |
| Does it reuse the routing engine? | **Yes — 100% reuse, no duplication** |
| Is the historical data good enough? | **Yes — 4 months of real Bengaluru hobli rainfall** |
| Estimated development time? | **6 days (2 backend + 4 frontend)** |
| Biggest risk? | **Hobli name mismatch (easily mitigated with normalization)** |
| Second biggest risk? | **Server RAM for concurrent sessions (mitigated by session eviction)** |
