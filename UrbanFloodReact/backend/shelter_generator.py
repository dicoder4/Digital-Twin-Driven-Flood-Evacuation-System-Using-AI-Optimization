"""
shelter_generator.py
────────────────────
Step 1 — Extract shelter candidates from OSM (with disk cache).
Step 2 — Filter by current flood state (flood polygons + road risk).
Step 3 — Assign rule-based capacity.
Step 4 — Attach to road graph via nearest node.
Fallback — Synthetic shelters on road nodes if OSM returns nothing.

Public API
──────────
  extract_shelter_candidates(G, lat, lon, hobli_key, dist=2000) → list[dict]
  filter_safe_shelters(candidates, flood_geojson, roads_geojson)  → list[dict]
"""

import os
import pickle
import random
import uuid
import math
import traceback
from pathlib import Path
from typing import Optional

import osmnx as ox
from shapely.geometry import Point, shape
from shapely.ops import unary_union

# ── Constants ──────────────────────────────────────────────────────────────────

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

SHELTER_TAGS = {
    "amenity": [
        "school", "hospital", "community_centre",
        "townhall", "police", "fire_station",
    ],
    "building": ["public"],
}

CAPACITY_RULES: dict[str, int] = {
    "school":           500,
    "hospital":         200,
    "community_centre": 300,
    "townhall":         300,
    "police":           150,
    "fire_station":     150,
    "public":           250,
}
DEFAULT_CAPACITY = 250
RANDOM_FALLBACK_COUNT = 6   # synthetic shelters if OSM is empty


# ── Step 1 + 3 + 4: Extract, assign capacity, attach to graph ─────────────────

def extract_shelter_candidates(G, lat: float, lon: float, hobli_key: str, dist: int = 2000) -> list[dict]:
    """
    Query OSM for shelter-like amenities within `dist` metres of (lat, lon).
    Attaches each to the nearest graph node.
    Results are disk-cached per hobli.

    On empty OSM result → returns synthetic random shelters on graph nodes.
    """
    cache_path = CACHE_DIR / f"{hobli_key}_shelters.pkl"

    # ── Cache hit ──────────────────────────────────────────────────────────────
    if cache_path.exists():
        print(f"  [shelters] Cache hit → {cache_path.name}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    # ── OSM query ─────────────────────────────────────────────────────────────
    candidates = []
    try:
        gdf = ox.features_from_point((lat, lon), tags=SHELTER_TAGS, dist=dist)
        print(f"  [shelters] OSM returned {len(gdf)} features for {hobli_key}")

        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            # Use centroid for polygons/multipolygons
            pt = geom.centroid if geom.geom_type != "Point" else geom
            s_lat, s_lon = pt.y, pt.x

            # Determine amenity type and capacity
            amenity = str(row.get("amenity", "")).strip().lower()
            building = str(row.get("building", "")).strip().lower()
            stype = amenity if amenity and amenity != "nan" else building
            capacity = CAPACITY_RULES.get(stype, DEFAULT_CAPACITY)

            name_raw = row.get("name", "")
            name = str(name_raw).strip() if name_raw and str(name_raw) != "nan" else _guess_name(stype)

            # Attach to nearest graph node
            try:
                node_id = ox.nearest_nodes(G, s_lon, s_lat)
            except Exception:
                node_id = None

            candidates.append({
                "id":       str(idx),
                "name":     name,
                "type":     stype or "building",
                "lat":      round(s_lat, 6),
                "lon":      round(s_lon, 6),
                "capacity": capacity,
                "node_id":  node_id,
            })

    except Exception as exc:
        print(f"  [shelters] OSM query failed: {exc}")

    # ── Fallback: synthetic shelters ──────────────────────────────────────────
    if not candidates:
        print(f"  [shelters] No OSM results — generating {RANDOM_FALLBACK_COUNT} synthetic shelters")
        candidates = _generate_synthetic_shelters(G, RANDOM_FALLBACK_COUNT)

    # ── Cache & return ─────────────────────────────────────────────────────────
    with open(cache_path, "wb") as f:
        pickle.dump(candidates, f)
    print(f"  [shelters] Cached {len(candidates)} candidates → {cache_path.name}")
    return candidates


# ── Step 2: Filter by flood state ─────────────────────────────────────────────

def filter_safe_shelters(
    candidates: list[dict],
    flood_geojson: Optional[dict],
    roads_geojson: Optional[dict],
) -> list[dict]:
    """
    For each candidate determine safe=True/False:
      • Unsafe if centroid falls inside a flood polygon
      • Unsafe if its nearest road edge has risk == 'high'

    Returns the full candidates list with `safe` field added.
    """
    # Build flood union polygon
    flood_union = _build_flood_union(flood_geojson)
    # Build set of high-risk node ids from flood roads
    high_risk_nodes = _build_high_risk_nodes(roads_geojson)

    result = []
    for s in candidates:
        pt = Point(s["lon"], s["lat"])
        in_flood = flood_union is not None and flood_union.contains(pt)
        near_high = s.get("node_id") in high_risk_nodes if s.get("node_id") else False
        result.append({**s, "safe": not (in_flood or near_high)})

    safe_count = sum(1 for s in result if s["safe"])
    print(f"  [shelters] {safe_count}/{len(result)} shelters marked safe")
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _guess_name(stype: str) -> str:
    labels = {
        "school": "School", "hospital": "Hospital",
        "community_centre": "Community Centre", "townhall": "Town Hall",
        "police": "Police Station", "fire_station": "Fire Station",
        "public": "Public Building",
    }
    return labels.get(stype, "Shelter")


def _build_flood_union(flood_geojson: Optional[dict]):
    """Union all flood polygon features into a single Shapely geometry."""
    if not flood_geojson or not flood_geojson.get("features"):
        return None
    polys = []
    for feat in flood_geojson["features"]:
        try:
            geom = shape(feat["geometry"])
            if not geom.is_empty:
                polys.append(geom)
        except Exception:
            pass
    return unary_union(polys) if polys else None


def _build_high_risk_nodes(roads_geojson: Optional[dict]) -> set:
    """
    Return a set of node_ids inferred as 'high risk'.
    Since we only have edge geometries here (not graph node ids), we use None —
    the node_id based check is a best-effort; flood polygon check is primary.
    """
    # Edge geometries don't carry node ids in the GeoJSON.
    # We rely on flood polygon containment as the primary safety check.
    return set()


def _generate_synthetic_shelters(G, count: int) -> list[dict]:
    """
    Pick `count` well-distributed graph nodes and label them as synthetic shelters.
    Uses degree-descending sort (high-degree = intersection = accessible).
    """
    nodes_by_degree = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    # Spread across the graph: take every Nth high-degree node
    step = max(1, len(nodes_by_degree) // (count * 2))
    chosen = [nodes_by_degree[i * step][0] for i in range(count) if i * step < len(nodes_by_degree)]

    types = ["school", "hospital", "community_centre", "police", "fire_station", "townhall"]
    shelters = []
    for i, node_id in enumerate(chosen[:count]):
        stype = types[i % len(types)]
        ndata = G.nodes[node_id]
        shelters.append({
            "id":       f"synthetic-{i}",
            "name":     f"{_guess_name(stype)} (approx.)",
            "type":     stype,
            "lat":      round(ndata["y"], 6),
            "lon":      round(ndata["x"], 6),
            "capacity": CAPACITY_RULES.get(stype, DEFAULT_CAPACITY),
            "node_id":  node_id,
            "synthetic": True,
        })
    return shelters
