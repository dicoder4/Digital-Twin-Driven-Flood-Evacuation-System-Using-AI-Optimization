

## Evacuation Shelter Generation (`generate_shelters` branch)

### What it does
After loading a hobli and running the flood simulation, the system automatically identifies valid **evacuation shelter candidates** from OpenStreetMap and evaluates their safety against the current flood state in real time.

**4-step pipeline:**
1. **Extract from OSM** — Queries OpenStreetMap for shelter-suitable buildings (schools, hospitals, community centres, town halls, police stations, fire stations, public buildings) within ~2 km of the hobli centre using `osmnx.features_from_point()`.
2. **Attach to graph** — Each candidate is snapped to the nearest road graph node via `osmnx.nearest_nodes()`, enabling future routing.
3. **Assign capacity** — Rule-based capacity assigned by building type (e.g. School → 500, Hospital → 200).
4. **Filter by flood state** — Frontend runs a point-in-polygon ray-casting check against the live flood GeoJSON on every simulation step. Shelters inside the flood zone turn red in real time without any extra API calls.
5. **Fallback** — If OSM returns no results for a hobli, 6 synthetic shelters are placed at high-degree road intersections (most connected/accessible nodes) and marked with amber icons.

**Result is disk-cached** at `backend/cache/{hobli_key}_shelters.pkl` so repeat loads are instant.

---

### File-by-file changes

#### Backend

| File | What changed |
|------|-------------|
| `backend/shelter_generator.py` | **NEW** — Full 4-step shelter pipeline: OSM query, graph attachment, capacity rules, flood filter, and synthetic fallback. Functions: `extract_shelter_candidates()`, `filter_safe_shelters()`, `_generate_synthetic_shelters()`. |
| `backend/service.py` | Added `fetch_shelters(hobli_name)` — loads/caches candidates via `shelter_generator`, returns raw list (no flood filter — done on frontend). |
| `backend/main.py` | Added `GET /shelters/{hobli_name}` endpoint that calls `service.fetch_shelters()`. |

#### Frontend

| File | What changed |
|------|-------------|
| `frontend/src/utils/geoUtils.js` | **NEW** — `computeShelterSafety(candidates, floodGeoJSON)` and `isPointFlooded()` — pure JS ray-casting point-in-polygon, no dependencies. Recomputed via `useMemo` on every simulation step. |
| `frontend/src/components/ShelterLayer.jsx` | **NEW** — Renders each shelter as a react-map-gl `Marker` with an inline SVG house icon (green = safe, red = flooded, amber = synthetic). Hover tooltip (name, type, capacity, status) via React `onMouseEnter/Leave` + `Popup`. |
| `frontend/src/components/SheltersPanel.jsx` | **NEW** — Sidebar panel with "Find Shelters" button (calls `GET /shelters/{hobli}`), summary count (`N safe · M total`), and a collapsible `<details>` list showing each shelter with type emoji, capacity, and safe/unsafe badge. |
| `frontend/src/App.jsx` | Added `shelterCandidates` state + `sheltersWithSafety` useMemo (recomputed from `sim.floodData`). `SheltersPanel` placed **before** the rainfall panel so shelters can be loaded before the simulation runs. |
| `frontend/src/components/FloodMap.jsx` | Added `ShelterLayer` import and renders it as the topmost map layer. |
| `frontend/src/App.css` | Added styles for `.shelter-details`, `.shelter-details-summary`, `.shelter-popup`, `.shelter-list`, `.shelter-item`, `.shelter-badge`, etc. |

---

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
