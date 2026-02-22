from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import osmnx as ox
import networkx as nx
import geopandas as gpd
import json
import asyncio
import uvicorn
from contextlib import asynccontextmanager
import os
import pickle
import numpy as np
import pandas as pd
import hashlib
from pathlib import Path
from collections import defaultdict

from flood_simulator import UrbanFloodSimulator

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

URBAN_JSON = DATA_DIR / "hobli_coordinates_urban.json"
RURAL_JSON = DATA_DIR / "hobli_coordinates_rural.json"

# Rainfall Excel files (May / June / July)
RAINFALL_FILES = {
    "May":  DATA_DIR / "Bengaluru_Rainfall_24Hrs_May.xlsx",
    "June": DATA_DIR / "Bengaluru_Rainfall_24Hrs_June.xlsx",
    "July": DATA_DIR / "Bengaluru_Rainfall_24Hrs_July.xlsx",
}

# ── In-memory Stores ───────────────────────────────────────────────────────────
# HOBLI_COORDS: normalised_key → {lat, lon, district}
HOBLI_COORDS: dict = {}
# REGIONS_TREE: district → taluk → [hobli_name, ...]
REGIONS_TREE: dict = {}
# RAINFALL_DATA: normalised_key → [{date, actual_mm, normal_mm, dep_pct}, ...]
RAINFALL_DATA: dict = {}
# REGION_CACHE: normalised_key → {G, drain_nodes, lake_nodes}
REGION_CACHE: dict = {}
# In-memory sim cache (params_key → result) — one entry per region+params combo
SIMULATION_CACHE: dict = {}


# ── Helper: key normalisation ──────────────────────────────────────────────────
def norm_key(name: str) -> str:
    """Normalise hobli key: strip, lowercase, unify dash/underscore separators."""
    return name.strip().lower().replace("_", "-")


# ── Coordinate loader ──────────────────────────────────────────────────────────
def _load_coords_from_json(path: Path, district: str):
    """
    Load a hobli coordinates JSON (array of {hobli_name, latitude, longitude}).
    Multiple rows per hobli_name are averaged (centroid).
    Returns dict: norm_key → {lat, lon, original_name, district}
    """
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    # Accumulate all lat/lon values per normalised key
    buckets: dict[str, list] = defaultdict(list)
    names_map: dict[str, str] = {}
    for r in records:
        raw   = r["hobli_name"]
        key   = norm_key(raw)
        buckets[key].append((r["latitude"], r["longitude"]))
        names_map[key] = raw          # last write wins for display name

    result = {}
    for key, coords in buckets.items():
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        result[key] = {
            "lat":           round(sum(lats) / len(lats), 6),
            "lon":           round(sum(lons) / len(lons), 6),
            "original_name": names_map[key],
            "district":      district,
            "num_points":    len(coords),
        }
    return result


# ── Rainfall loader ────────────────────────────────────────────────────────────
def _load_rainfall_excels():
    """
    Load all rainfall Excel files and build RAINFALL_DATA.
    Expected columns (case-insensitive): Date, District, Taluk, Hobli,
                                         24h_Normal_mm, 24h_Actual_mm, 24h_Dep_Pct
    """
    frames = []
    for month, path in RAINFALL_FILES.items():
        if not path.exists():
            print(f"  [WARN] Rainfall file missing: {path.name}")
            continue
        try:
            df = pd.read_excel(path)
            df.columns = [c.strip() for c in df.columns]
            df["_month"] = month
            frames.append(df)
            print(f"  Loaded {len(df)} rows from {path.name}")
        except Exception as e:
            print(f"  [WARN] Could not load {path.name}: {e}")

    if not frames:
        print("  [WARN] No rainfall Excel files loaded.")
        return

    combined = pd.concat(frames, ignore_index=True)

    # Flexible column detection
    col_map = {}
    for col in combined.columns:
        cl = col.lower().replace(" ", "_").replace("-", "_")
        if cl in ("date",):                     col_map["date"]       = col
        if cl in ("district",):                 col_map["district"]   = col
        if cl in ("taluk",):                    col_map["taluk"]      = col
        if cl in ("hobli",):                    col_map["hobli"]      = col
        if "normal" in cl and "mm" in cl:       col_map["normal_mm"]  = col
        if "actual" in cl and "mm" in cl:       col_map["actual_mm"]  = col
        if "dep" in cl and ("pct" in cl or "percent" in cl or "%" in cl):
                                                col_map["dep_pct"]    = col

    required = {"date", "hobli", "actual_mm"}
    missing  = required - set(col_map.keys())
    if missing:
        print(f"  [ERROR] Rainfall columns not found: {missing}")
        print(f"          Available columns: {combined.columns.tolist()}")
        return

    for _, row in combined.iterrows():
        raw_hobli = str(row[col_map["hobli"]]).strip()
        key       = norm_key(raw_hobli)

        # Parse date — try multiple formats
        raw_date = str(row[col_map["date"]]).strip()
        try:
            parsed = pd.to_datetime(raw_date, dayfirst=True)
            date_str = parsed.strftime("%d-%m-%Y")
        except Exception:
            date_str = raw_date

        entry = {
            "date":       date_str,
            "actual_mm":  float(row.get(col_map.get("actual_mm", ""), 0) or 0),
            "normal_mm":  float(row.get(col_map.get("normal_mm", ""), 0) or 0) if "normal_mm" in col_map else None,
            "dep_pct":    float(row.get(col_map.get("dep_pct", ""), 0) or 0)   if "dep_pct"   in col_map else None,
            "district":   str(row.get(col_map.get("district",""), "")).strip()  if "district"  in col_map else "",
            "taluk":      str(row.get(col_map.get("taluk",""), "")).strip()     if "taluk"     in col_map else "",
            "month":      row.get("_month", ""),
        }
        RAINFALL_DATA.setdefault(key, []).append(entry)

    print(f"  Rainfall data loaded for {len(RAINFALL_DATA)} unique hoblis.")


# ── Regions tree builder ───────────────────────────────────────────────────────
def _build_regions_tree():
    """
    Build REGIONS_TREE from rainfall data (district → taluk → hobli list).
    Falls back to coord keys if no rainfall data.
    """
    tree: dict[str, dict[str, list]] = {}

    for key, entries in RAINFALL_DATA.items():
        if not entries:
            continue
        e         = entries[0]
        district  = e.get("district", "Unknown") or "Unknown"
        taluk     = e.get("taluk",    "Unknown") or "Unknown"

        # Use the original display name from coords if available
        display = HOBLI_COORDS.get(key, {}).get("original_name", key)

        tree.setdefault(district, {}).setdefault(taluk, [])
        if display not in tree[district][taluk]:
            tree[district][taluk].append(display)

    # Sort everything
    for dist in tree:
        for tal in tree[dist]:
            tree[dist][tal].sort()
        tree[dist] = dict(sorted(tree[dist].items()))

    REGIONS_TREE.clear()
    REGIONS_TREE.update(dict(sorted(tree.items())))
    total = sum(len(h) for d in tree.values() for h in d.values())
    print(f"  Regions tree built: {len(tree)} districts, {total} hoblis.")


# ── OSMnx graph loader ─────────────────────────────────────────────────────────
def _load_graph_for_hobli(hobli_key: str):
    """
    Load (or retrieve cached) OSMnx graph + drains + lakes for a hobli.
    Uses centroid coords from HOBLI_COORDS with a 2 km bbox.
    Caches to disk as cache/{hobli_key}_graph.graphml and cache/{hobli_key}_features.pkl
    """
    if hobli_key in REGION_CACHE:
        return REGION_CACHE[hobli_key]

    coords = HOBLI_COORDS.get(hobli_key)
    if not coords:
        raise ValueError(f"No coordinates found for hobli key: '{hobli_key}'")

    lat, lon    = coords["lat"], coords["lon"]
    safe_key    = hobli_key.replace("/", "_").replace(" ", "_")
    graph_file  = CACHE_DIR / f"{safe_key}_graph.graphml"
    feat_file   = CACHE_DIR / f"{safe_key}_features.pkl"

    # 1. Load / download graph
    if graph_file.exists():
        print(f"  Loading cached graph: {graph_file.name}")
        G = ox.load_graphml(str(graph_file))
    else:
        print(f"  Downloading OSMnx graph for {coords['original_name']} ({lat:.4f}, {lon:.4f}) …")
        G = ox.graph_from_point((lat, lon), dist=2000, dist_type="bbox", network_type="drive")
        ox.save_graphml(G, str(graph_file))
        print(f"  Graph saved → {graph_file.name}")

    # 2. Load / extract drains & lakes
    drain_nodes, lake_nodes = [], []

    if feat_file.exists():
        print(f"  Loading cached features: {feat_file.name}")
        with open(feat_file, "rb") as f:
            data        = pickle.load(f)
            drain_nodes = data.get("drains", [])
            lake_nodes  = data.get("lakes", [])
    else:
        center = (lat, lon)
        # Drains
        try:
            ww = ox.features_from_point(center, tags={"waterway": ["drain", "stream", "ditch", "canal"]}, dist=2000)
            if not ww.empty:
                cxs = ww.geometry.centroid.x.tolist()
                cys = ww.geometry.centroid.y.tolist()
                dn  = ox.nearest_nodes(G, cxs, cys)
                drain_nodes = list(dn) if hasattr(dn, "__iter__") else [dn]
                print(f"    Drains: {len(drain_nodes)} nodes")
        except Exception as e:
            print(f"    [WARN] Drains: {e}")

        # Lakes
        try:
            lake_tags = {"natural": "water", "water": ["lake","pond","reservoir"], "landuse": ["reservoir","basin"]}
            lakes = ox.features_from_point(center, tags=lake_tags, dist=2000)
            lake_pts = []
            if not lakes.empty:
                for _, row in lakes.iterrows():
                    g = row.geometry
                    if g.geom_type in ("Polygon", "MultiPolygon"):
                        polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
                        for poly in polys:
                            ext = poly.exterior
                            n   = max(5, int(ext.length / 0.0002))
                            lake_pts += [(ext.interpolate(i/n, normalized=True).x,
                                          ext.interpolate(i/n, normalized=True).y) for i in range(n)]
                    else:
                        lake_pts.append((g.centroid.x, g.centroid.y))
            if lake_pts:
                lake_pts = list(set(lake_pts))
                ln = ox.nearest_nodes(G, [p[0] for p in lake_pts], [p[1] for p in lake_pts])
                lake_nodes = list(ln) if hasattr(ln, "__iter__") else [ln]
                print(f"    Lakes: {len(lake_nodes)} nodes")
        except Exception as e:
            print(f"    [WARN] Lakes: {e}")

        with open(feat_file, "wb") as f:
            pickle.dump({"drains": drain_nodes, "lakes": lake_nodes}, f)
        print(f"  Features saved → {feat_file.name}")

    entry = {"G": G, "drain_nodes": drain_nodes, "lake_nodes": lake_nodes}
    REGION_CACHE[hobli_key] = entry
    return entry


# ── App Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initialising Urban Flood Backend (multi-hobli) …")

    # Load coordinate maps
    print("Loading hobli coordinate maps …")
    urban_coords = _load_coords_from_json(URBAN_JSON, "BENGALURU URBAN")
    rural_coords = _load_coords_from_json(RURAL_JSON, "BENGALURU RURAL")
    HOBLI_COORDS.update(urban_coords)
    HOBLI_COORDS.update(rural_coords)
    print(f"  Loaded {len(HOBLI_COORDS)} unique hoblis ({len(urban_coords)} urban, {len(rural_coords)} rural).")

    # Load rainfall Excel files
    print("Loading rainfall data …")
    _load_rainfall_excels()

    # Build regions tree
    _build_regions_tree()

    print("Backend Ready. No graph pre-loaded — regions are lazy-loaded on demand.")
    yield
    print("Shutting down.")


app = FastAPI(lifespan=lifespan, title="Urban Flood Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ─────────────────────────────────────────────────────────────
class LoadRegionRequest(BaseModel):
    hobli: str


class SimulationParams(BaseModel):
    rainfall_mm: float  = 150.0
    steps:       int    = 20
    decay_factor: float = 0.5


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/regions")
async def get_regions():
    """Return district → taluk → [hobli] tree for the UI cascade selector."""
    return REGIONS_TREE


@app.post("/load-region")
async def load_region(req: LoadRegionRequest):
    """
    Lazy-load the OSMnx graph for a hobli (cached on disk after first call).
    Returns centre coords and status so the frontend can pan the map.
    """
    key = norm_key(req.hobli)

    coords = HOBLI_COORDS.get(key)
    if not coords:
        raise HTTPException(
            status_code=404,
            detail=f"Hobli '{req.hobli}' not found in coordinate map. Available keys sample: {list(HOBLI_COORDS.keys())[:5]}"
        )

    try:
        await asyncio.get_event_loop().run_in_executor(None, _load_graph_for_hobli, key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load graph: {e}")

    return {
        "status":  "loaded",
        "hobli":   req.hobli,
        "lat":     coords["lat"],
        "lon":     coords["lon"],
        "district": coords["district"],
    }


@app.get("/rainfall-data/{hobli_name}")
async def get_rainfall_data(hobli_name: str):
    """
    Return all historical rainfall records for a given hobli.
    Entries are sorted chronologically.
    """
    key = norm_key(hobli_name)
    entries = RAINFALL_DATA.get(key)

    if not entries:
        raise HTTPException(
            status_code=404,
            detail=f"No rainfall data for hobli '{hobli_name}'."
        )

    # Sort by date string (dd-mm-yyyy) chronologically
    try:
        sorted_entries = sorted(entries, key=lambda e: pd.to_datetime(e["date"], dayfirst=True))
    except Exception:
        sorted_entries = entries

    return {
        "hobli":   hobli_name,
        "count":   len(sorted_entries),
        "records": sorted_entries,
    }


@app.get("/map-data")
async def get_map_data(hobli: str = Query(..., description="Hobli name")):
    """Return road network GeoJSON for the selected hobli."""
    key = norm_key(hobli)

    if key not in REGION_CACHE:
        raise HTTPException(
            status_code=400,
            detail=f"Region '{hobli}' not loaded. Call POST /load-region first."
        )

    G     = REGION_CACHE[key]["G"]
    nodes, edges = ox.graph_to_gdfs(G)
    return json.loads(edges.to_json())


@app.get("/simulate-stream")
async def simulate_stream(
    hobli:        str   = Query(...),
    rainfall_mm:  float = Query(150.0),
    steps:        int   = Query(20),
    decay_factor: float = Query(0.5),
):
    """Stream flood simulation steps as SSE for the selected hobli."""
    key = norm_key(hobli)

    if key not in REGION_CACHE:
        raise HTTPException(
            status_code=400,
            detail=f"Region '{hobli}' not loaded. Call POST /load-region first."
        )

    cache_entry = REGION_CACHE[key]
    G_ref       = cache_entry["G"]
    drains      = cache_entry["drain_nodes"]
    lakes       = cache_entry["lake_nodes"]

    async def event_generator():
        sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)
        sim.initialize_from_drains(rainfall_mm)

        loop = asyncio.get_event_loop()

        for i in range(steps):
            await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
            impact    = await loop.run_in_executor(None, sim.calculate_flood_impact)
            flood_gdf = impact["flood_gdf"]
            roads_gdf = impact["roads_gdf"]

            step_data = {
                "step":          i + 1,
                "total":         steps,
                "flood_geojson": json.loads(flood_gdf.to_json()) if not flood_gdf.empty
                                 else {"type": "FeatureCollection", "features": []},
                "roads_geojson": json.loads(roads_gdf.to_json()) if not roads_gdf.empty
                                 else {"type": "FeatureCollection", "features": []},
            }
            yield f"data: {json.dumps(step_data)}\n\n"

        yield f"data: {json.dumps({'done': True, 'total': steps})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
