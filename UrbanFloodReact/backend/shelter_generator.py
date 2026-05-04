"""
shelter_generator.py
────────────────────
Step 1 — Extract shelter candidates from OSM (with MongoDB cache).
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
import random
import uuid
import math
import traceback
import time
from typing import Optional

import osmnx as ox
from shapely.geometry import Point, shape
from shapely.ops import unary_union

import db

# ── Constants ──────────────────────────────────────────────────────────────────

SHELTER_TAGS = {
    "amenity": [
        "school", "hospital", "community_centre",
        "townhall", "police", "fire_station",
    ],
    "building": ["public"],
}

# Load Factors (m^2 per person) based on NBC 2016 India
LOAD_FACTORS_SQM_PER_PERSON: dict[str, float] = {
    "school":           4.0,   # Educational
    "hospital":         15.0,  # Healthcare IPD
    "community_centre": 1.4,   # Assembly / Lobbies
    "townhall":         1.4,   # Assembly / Lobbies
    "police":           10.0,  # Office
    "fire_station":     10.0,  # Office
    "public":           10.0,  # Office
}
DEFAULT_LOAD_FACTOR = 10.0
RANDOM_FALLBACK_COUNT = 6   # synthetic shelters if OSM is empty


# ── Step 1 + 3 + 4: Extract, assign capacity, attach to graph ─────────────────

def extract_shelter_candidates(G, lat: float, lon: float, hobli_key: str, dist: int = 2000) -> list[dict]:
    """
    Query OSM for shelter-like amenities within `dist` metres of (lat, lon).
    Attaches each to the nearest graph node.
    Results are disk-cached per hobli.

    On empty OSM result → returns synthetic random shelters on graph nodes.
    """
    # ── Cache hit (MongoDB) ────────────────────────────────────────────────────
    cached = db.get_shelter_cache(hobli_key)
    if cached is not None:
        print(f"  [shelters] MongoDB cache hit for '{hobli_key}'")
        return cached

    # ── OSM query ─────────────────────────────────────────────────────────────
    candidates = []
    print(f"  [DEBUG-OSM] Querrying OSM features at ({lat}, {lon}) with dist={dist}m")
    print(f"  [DEBUG-OSM] Tags: {SHELTER_TAGS}")
    try:
        start_t = time.time()
        gdf = ox.features_from_point((lat, lon), tags=SHELTER_TAGS, dist=dist)
        query_time = time.time() - start_t
        print(f"  [DEBUG-OSM] Query took {query_time:.2f}s. Returned {len(gdf)} features for {hobli_key}")

        if not gdf.empty:
            if 'amenity' in gdf.columns:
                print(f"  [DEBUG-OSM] Amenities found: {gdf['amenity'].value_counts().to_dict()}")
            if 'building' in gdf.columns:
                print(f"  [DEBUG-OSM] Buildings found: {gdf['building'].value_counts().to_dict()}")

        try:
            # Use submodule projection for newer OSMnx versions
            gdf_proj = ox.projection.project_gdf(gdf)
        except Exception as e:
            print(f"  [DEBUG-OSM] Projection failed (trying fallback): {e}")
            try:
                gdf_proj = ox.project_gdf(gdf)
            except Exception:
                print(f"  [DEBUG-OSM] All projection methods failed. Falling back to unprojected.")
                gdf_proj = gdf

        # ── Optional: Fetch building footprints to match points ────────────────
        bldg_polys = None
        try:
            print(f"  [DEBUG-OSM] Fetching building footprints to match Point markers...")
            gdf_bldgs = ox.features_from_point((lat, lon), tags={"building": True}, dist=dist)
            
            try:
                gdf_bldgs_proj = ox.projection.project_gdf(gdf_bldgs)
            except:
                gdf_bldgs_proj = ox.project_gdf(gdf_bldgs)

            bldg_polys = gdf_bldgs_proj[gdf_bldgs_proj.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            print(f"  [DEBUG-OSM] Loaded {len(bldg_polys)} building footprints for accurate area matching.")
        except Exception as e:
            print(f"  [DEBUG-OSM] Could not load building footprints: {e}")

        for (idx, row), (_, row_proj) in zip(gdf.iterrows(), gdf_proj.iterrows()):
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            # Calculate area in square meters from the projected geometry
            area_sqm = row_proj.geometry.area if row_proj.geometry and row_proj.geometry.geom_type != "Point" else 0.0

            # If it's a point, try to find the building footprint that contains it
            if area_sqm == 0.0 and bldg_polys is not None and row_proj.geometry.geom_type == "Point":
                # Find the intersecting building
                matches = bldg_polys[bldg_polys.geometry.contains(row_proj.geometry)]
                if not matches.empty:
                    area_sqm = matches.iloc[0].geometry.area
                    print(f"  [DEBUG-OSM] Point matched to footprint! Extracted Area: {area_sqm:.1f} m^2")


            # Use centroid for polygons/multipolygons
            pt = geom.centroid if geom.geom_type != "Point" else geom
            s_lat, s_lon = pt.y, pt.x

            # Determine amenity type and capacity
            amenity = str(row.get("amenity", "")).strip().lower()
            building = str(row.get("building", "")).strip().lower()
            stype = amenity if amenity and amenity != "nan" else building
            
            load_factor = LOAD_FACTORS_SQM_PER_PERSON.get(stype, DEFAULT_LOAD_FACTOR)
            
            # NBC 2016 Formula: Occupant Load = Usable Area / Load Factor
            # Assume 80% of footprint is usable area, and multiply by 1 level conservatively
            if area_sqm > 20.0:  # If it's a valid polygon with area
                usable_area = area_sqm * 0.8
                capacity = max(50, int(usable_area / load_factor))
                print(f"  [DEBUG-OSM] Shelter '{row.get('name','ID:'+str(idx))}' | Type: {stype} | Area: {area_sqm:.1f}m2 | LoadFactor: {load_factor} | NBC Cap: {capacity}")
            else:
                # Fallbacks for points or invalid polygons
                fallback_rules = {
                    "school": 2500, "hospital": 600, "community_centre": 1200,
                    "townhall": 2000, "police": 300, "fire_station": 300, "public": 1000
                }
                capacity = fallback_rules.get(stype, 1000)
                print(f"  [DEBUG-OSM] Shelter '{row.get('name','ID:'+str(idx))}' | Type: {stype} | No Area (Point) | Fallback Cap: {capacity}")

            name_raw = row.get("name", "")
            name = str(name_raw).strip() if name_raw and str(name_raw) != "nan" else _guess_name(stype)

            # Attach to nearest graph node
            try:
                node_id = ox.nearest_nodes(G, s_lon, s_lat)
                # GIS Enhancement: Attach real elevation to the shelter
                elevation = G.nodes[node_id].get('elevation', 0.0) if node_id in G.nodes else 0.0
                if elevation > 0:
                    print(f"  [gis] Shelter '{name}' tagged with elevation: {elevation:.1f}m")
            except Exception:
                node_id = None
                elevation = 0.0

            candidates.append({
                "id":       str(idx),
                "name":     name,
                "type":     stype or "building",
                "lat":      round(s_lat, 6),
                "lon":      round(s_lon, 6),
                "elevation": round(elevation, 1),
                "capacity": capacity,
                "node_id":  node_id,
            })

    except Exception as exc:
        print(f"  [shelters] OSM query failed: {exc}")

    # ── Fallback: synthetic shelters ──────────────────────────────────────────
    if not candidates:
        print(f"  [shelters] No OSM results — generating {RANDOM_FALLBACK_COUNT} synthetic shelters")
        candidates = _generate_synthetic_shelters(G, RANDOM_FALLBACK_COUNT)

    # ── Persist to MongoDB & return ────────────────────────────────────────────
    db.set_shelter_cache(hobli_key, candidates)
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
        # covers() is boundary-inclusive; prevents shelters on flood polygon edges
        # from being misclassified as safe.
        in_flood = flood_union is not None and flood_union.covers(pt)
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
    Return a set of node_ids where associated road risk is 'high'.
    """
    if not roads_geojson or not roads_geojson.get("features"):
        return set()
    
    high_risk_ids = set()
    for feat in roads_geojson["features"]:
        props = feat.get("properties", {})
        if props.get("risk") == "high":
            u = props.get("u_id")
            v = props.get("v_id")
            if u: high_risk_ids.add(u)
            if v: high_risk_ids.add(v)
            
    return high_risk_ids


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
            "capacity": 1000, # Default fallback capacity for synthetic shelters
            "node_id":  node_id,
            "synthetic": True,
        })
    return shelters
