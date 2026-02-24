"""
region_manager.py
─────────────────
Owns all mutable server state:
  - HOBLI_COORDS  : norm_key → coord metadata
  - RAINFALL_DATA : norm_key → list of rainfall records
  - REGION_CACHE  : norm_key → {G, drain_nodes, lake_nodes}
  - REGIONS_TREE  : district → taluk → [hobli display names]

Provides:
  - initialise(data_dir) — called once in lifespan
  - get_region(hobli_key) — returns cached or downloads graph
  - norm_key()            — re-exported for endpoints
"""

from pathlib import Path
import pickle
import osmnx as ox
from shapely.geometry import Point, LineString

from coord_loader   import load_coords_from_json, norm_key  # noqa: F401 (re-export norm_key)
from rainfall_loader import load_rainfall_excels

# ── Module-level state ─────────────────────────────────────────────────────────
HOBLI_COORDS:  dict = {}
RAINFALL_DATA: dict = {}
REGION_CACHE:  dict = {}
REGIONS_TREE:  dict = {}

DATA_DIR  = Path(__file__).parent / "data"
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

URBAN_JSON = DATA_DIR / "hobli_coordinates_urban.json"
RURAL_JSON = DATA_DIR / "hobli_coordinates_rural.json"


# ── Initialise (called once at startup) ────────────────────────────────────────
def initialise():
    """Load all coordinate maps and rainfall data, then build region tree."""
    print("Loading hobli coordinate maps …")
    urban = load_coords_from_json(URBAN_JSON, "BENGALURU URBAN")
    rural = load_coords_from_json(RURAL_JSON, "BENGALURU RURAL")
    HOBLI_COORDS.update(urban)
    HOBLI_COORDS.update(rural)
    print(f"  {len(HOBLI_COORDS)} unique hoblis ({len(urban)} urban, {len(rural)} rural)")

    print("Loading rainfall data …")
    load_rainfall_excels(DATA_DIR, norm_key, RAINFALL_DATA)

    print("Building regions tree …")
    _build_regions_tree()


def _build_regions_tree():
    tree: dict[str, dict[str, list]] = {}

    for key, entries in RAINFALL_DATA.items():
        if not entries:
            continue
        # Skip hoblis that have no coordinate entry — they can't be loaded
        if key not in HOBLI_COORDS:
            continue
        e        = entries[0]
        district = e.get("district") or "Unknown"
        taluk    = e.get("taluk")    or "Unknown"
        display  = HOBLI_COORDS[key].get("original_name", key)

        tree.setdefault(district, {}).setdefault(taluk, [])
        if display not in tree[district][taluk]:
            tree[district][taluk].append(display)

    for dist in tree:
        for tal in tree[dist]:
            tree[dist][tal].sort()
        tree[dist] = dict(sorted(tree[dist].items()))

    REGIONS_TREE.clear()
    REGIONS_TREE.update(dict(sorted(tree.items())))

    total = sum(len(h) for d in tree.values() for h in d.values())
    print(f"  Tree: {len(tree)} districts, {total} hoblis")


# ── Graph loader (lazy + disk-cached) ─────────────────────────────────────────
def get_region(hobli_key: str) -> dict:
    """
    Return {G, drain_nodes, lake_nodes} for the given normalised hobli key.
    Downloads from OSMnx on first call, then caches in memory and on disk.
    """
    if hobli_key in REGION_CACHE:
        return REGION_CACHE[hobli_key]

    coords = HOBLI_COORDS.get(hobli_key)
    if not coords:
        raise ValueError(f"No coordinates for hobli key '{hobli_key}'")

    lat, lon  = coords["lat"], coords["lon"]
    safe_key  = hobli_key.replace("/", "_").replace(" ", "_")
    graph_f   = CACHE_DIR / f"{safe_key}_graph.graphml"
    feat_f    = CACHE_DIR / f"{safe_key}_features.pkl"

    # 1. Graph
    if graph_f.exists():
        print(f"  [cache] Loading graph: {graph_f.name}")
        G = ox.load_graphml(str(graph_f))
    else:
        print(f"  [osmnx] Downloading graph for {coords['original_name']} …")
        G = ox.graph_from_point((lat, lon), dist=2000, dist_type="bbox", network_type="drive")
        ox.save_graphml(G, str(graph_f))
        print(f"  [osmnx] Saved → {graph_f.name}")

    # 2. Drains & lakes
    drain_nodes, lake_nodes = [], []
    if feat_f.exists():
        print(f"  [cache] Loading features: {feat_f.name}")
        with open(feat_f, "rb") as f:
            saved       = pickle.load(f)
            drain_nodes = saved.get("drains", [])
            lake_nodes  = saved.get("lakes", [])
    else:
        center = (lat, lon)
        drain_nodes = _extract_drains(G, center)
        lake_nodes  = _extract_lakes(G, center)
        with open(feat_f, "wb") as f:
            pickle.dump({"drains": drain_nodes, "lakes": lake_nodes}, f)
        print(f"  [cache] Features saved → {feat_f.name}")

    entry = {"G": G, "drain_nodes": drain_nodes, "lake_nodes": lake_nodes}
    REGION_CACHE[hobli_key] = entry
    return entry


def _extract_drains(G, center):
    try:
        ww = ox.features_from_point(
            center,
            tags={"waterway": ["drain", "stream", "ditch", "canal"]},
            dist=2000,
        )
        if not ww.empty:
            cxs = ww.geometry.centroid.x.tolist()
            cys = ww.geometry.centroid.y.tolist()
            dn  = ox.nearest_nodes(G, cxs, cys)
            nodes = list(dn) if hasattr(dn, "__iter__") else [dn]
            print(f"    Drains: {len(nodes)} nodes")
            return nodes
    except Exception as e:
        print(f"    [warn] Drains: {e}")
    return []


def _extract_lakes(G, center):
    try:
        lake_tags = {
            "natural": "water",
            "water":   ["lake", "pond", "reservoir"],
            "landuse": ["reservoir", "basin"],
        }
        lakes = ox.features_from_point(center, tags=lake_tags, dist=2000)
        points = []
        if not lakes.empty:
            for _, row in lakes.iterrows():
                g = row.geometry
                if g.geom_type in ("Polygon", "MultiPolygon"):
                    polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
                    for poly in polys:
                        ext = poly.exterior
                        n   = max(5, int(ext.length / 0.0002))
                        points += [
                            (ext.interpolate(i / n, normalized=True).x,
                             ext.interpolate(i / n, normalized=True).y)
                            for i in range(n)
                        ]
                else:
                    points.append((g.centroid.x, g.centroid.y))
        if points:
            points = list(set(points))
            ln     = ox.nearest_nodes(G, [p[0] for p in points], [p[1] for p in points])
            nodes  = list(ln) if hasattr(ln, "__iter__") else [ln]
            print(f"    Lakes: {len(nodes)} nodes")
            return nodes
    except Exception as e:
        print(f"    [warn] Lakes: {e}")
    return []
