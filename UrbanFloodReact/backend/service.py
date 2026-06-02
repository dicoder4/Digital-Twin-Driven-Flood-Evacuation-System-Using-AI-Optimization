"""
service.py — Business logic for Urban Flood Digital Twin
────────────────────────────────────────────────────────
Following MVC architecture: This is the Service layer handling logic
between the API (Controller) and the Data/Simulators (Model).
"""

import asyncio
import json
import os
import math
import time as _time_module
from datetime import datetime
from collections import defaultdict
import numpy as np
import pandas as pd
import osmnx as ox
from fastapi import HTTPException

def _ts() -> str:
    """Return a short HH:MM:SS timestamp for debug logs."""
    return datetime.now().strftime('[%H:%M:%S]')

# Relative imports from the backend package
from region_manager import (
    get_region, norm_key,
    HOBLI_COORDS, RAINFALL_DATA, REGIONS_TREE, REGION_CACHE,
)
from flood_simulator import UrbanFloodSimulator
from generate_people import get_population
from shelter_generator import extract_shelter_candidates, filter_safe_shelters
from evacuation_ga import GeneticEvacuationPlanner
from aco import ACOEvacuationPlanner
from pso import PSOEvacuationPlanner

# ── Algorithm factory ────────────────────────────────────────────────────────
_PLANNER_MAP = {
    "ga":  GeneticEvacuationPlanner,
    "aco": ACOEvacuationPlanner,
    "pso": PSOEvacuationPlanner,
}

def _get_planner_class(algorithm: str):
    """Return the planner class for the given algorithm key (case-insensitive)."""
    key = algorithm.lower().strip()
    if key == "all":
        # Fallback to ACO if 'all' leaks into single simulation path
        return ACOEvacuationPlanner
    if key not in _PLANNER_MAP:
        raise ValueError(f"Unknown algorithm '{algorithm}'. Choose from: {list(_PLANNER_MAP.keys())}")
    return _PLANNER_MAP[key]


def _metro_status_from_score(score: float, previous_status: str | None = None) -> str:
    """Map a continuous risk score to safe/caution/unsafe with hysteresis margins."""
    low_threshold = 0.20
    high_threshold = 0.50
    margin = 0.04

    if previous_status == "safe":
        if score < low_threshold + margin:
            return "safe"
    elif previous_status == "unsafe":
        if score > high_threshold - margin:
            return "unsafe"

    if score >= high_threshold:
        return "unsafe"
    if score >= low_threshold:
        return "caution"
    return "safe"


def _k_hop_nodes(graph, source_node, max_hops: int = 2) -> list:
    """Return unique nodes up to max_hops from source (BFS)."""
    if source_node not in graph:
        return []
    visited = {source_node}
    frontier = {source_node}
    for _ in range(max_hops):
        next_frontier = set()
        for node in frontier:
            for nb in graph.neighbors(node):
                if nb not in visited:
                    visited.add(nb)
                    next_frontier.add(nb)
        if not next_frontier:
            break
        frontier = next_frontier
    return list(visited)


def _collect_metro_reports(sim: UrbanFloodSimulator, metro_stations: list, center_lat: float, center_lon: float, update_history: bool = True) -> list:
    """
    Build metro station risk reports using:
      - distance from hobli centre (exclude stations >2km)
      - snapping distance to graph (safe if >50m)
      - local neighbourhood flood depths (2-hop proxy)
      - access viability near station
      - temporal EMA smoothing
    """
    if not hasattr(sim, "_metro_status_history"):
        sim._metro_status_history = {}

    reports = []
    graph = sim.G

    for station in metro_stations:
        station_name = station.get("name") or "Unknown Station"
        station_line = station.get("line")
        station_key = str(station.get("id") or f"{station_name}::{station_line or ''}")
        station_lat = station.get("lat")
        station_lon = station.get("lon")

        # --- 1. Distance to hobli centre ---
        dist_km = _haversine_distance(center_lat, center_lon, station_lat, station_lon)
        if dist_km > 2.0:   # outside 2km simulation radius
            reports.append({
                "id": station.get("id", station_key),
                "name": station_name,
                "lat": station_lat,
                "lon": station_lon,
                "line": station_line,
                "colour": station.get("colour"),
                "transport_type": station.get("transport_type", "metro"),
                "flooded": False,
                "status": "safe",
                "risk_score": 0.0,
                "max_depth_m": 0.0,
                "mean_depth_m": 0.0,
                "access_viability": 1.0,
                "confidence": "high",
                "confidence_reason": "outside simulation radius",
            })
            continue

        # --- 2. Snap to graph with distance limit ---
        node_id = station.get("node_id")
        snap_dist = None
        if node_id is not None and node_id in graph:
            # Use existing node_id, but verify it's close enough
            node_lat = graph.nodes[node_id]['y']
            node_lon = graph.nodes[node_id]['x']
            snap_dist = _haversine_distance(station_lat, station_lon, node_lat, node_lon) * 1000  # convert to meters
        else:
            # Snap anew
            try:
                node_id, snap_dist_m = ox.nearest_nodes(graph, station_lon, station_lat, return_dist=True)
                snap_dist = snap_dist_m
            except Exception:
                node_id = None
                snap_dist = None

        if node_id is None or node_id not in graph or (snap_dist is not None and snap_dist > 50):
            reports.append({
                "id": station.get("id", station_key),
                "name": station_name,
                "lat": station_lat,
                "lon": station_lon,
                "line": station_line,
                "colour": station.get("colour"),
                "transport_type": station.get("transport_type", "metro"),
                "flooded": False,
                "status": "safe",
                "risk_score": 0.0,
                "max_depth_m": 0.0,
                "mean_depth_m": 0.0,
                "access_viability": 1.0,
                "confidence": "medium",
                "confidence_reason": f"station too far from road network ({snap_dist:.1f}m)",
            })
            continue

        # --- 3. Proceed with neighbourhood analysis ---
        neighborhood_nodes = _k_hop_nodes(graph, node_id, max_hops=2)
        depths = [float(graph.nodes[n].get("water_depth", 0.0)) for n in neighborhood_nodes]

        if not depths:
            depths = [0.0]

        max_depth = max(depths)
        mean_depth = sum(depths) / max(len(depths), 1)

        if station_lat is not None and station_lon is not None and neighborhood_nodes:
            nearest = sorted(
                neighborhood_nodes,
                key=lambda n: (graph.nodes[n].get("y", station_lat) - station_lat) ** 2
                + (graph.nodes[n].get("x", station_lon) - station_lon) ** 2,
            )[:3]
        else:
            nearest = neighborhood_nodes[:3]

        if nearest:
            accessible = sum(1 for n in nearest if float(graph.nodes[n].get("water_depth", 0.0)) <= 0.20)
            access_viability = accessible / len(nearest)
        else:
            access_viability = 0.0

        raw_score = min(1.0, (0.55 * max_depth) + (0.35 * mean_depth) + (0.10 * (1.0 - access_viability)))
                # DEBUG: for Konankunte Cross
        if station_name == "Konanakunte Cross":
            print(f"[DEBUG] {station_name}: snap_dist={snap_dist:.1f}m, "
                  f"max_depth={max_depth:.3f}m, mean_depth={mean_depth:.3f}m, "
                  f"access_viability={access_viability:.2f}, raw_score={raw_score:.3f}")
            print(f"  neighborhood nodes: {neighborhood_nodes[:5]}")
            for n in neighborhood_nodes[:5]:
                print(f"    node {n}: depth={graph.nodes[n].get('water_depth', 0):.3f}m")

        history = sim._metro_status_history.get(station_key, {})
        previous_ema = float(history.get("ema_score", raw_score))
        ema_score = 0.5 * previous_ema + 0.5 * raw_score if history else raw_score
        previous_status = history.get("status")
        status = _metro_status_from_score(ema_score, previous_status=previous_status)

        confidence = "high"
        confidence_reason = "dense local neighbourhood available"
        if len(neighborhood_nodes) < 4:
            confidence = "medium"
            confidence_reason = "limited neighbourhood sample"
        if snap_dist is not None and snap_dist > 30:
            confidence = "medium"
            confidence_reason = f"snap distance {snap_dist:.1f}m"

        if update_history:
            sim._metro_status_history[station_key] = {
                "ema_score": ema_score,
                "status": status,
            }

        reports.append({
            "id": station.get("id", station_key),
            "name": station_name,
            "lat": station_lat,
            "lon": station_lon,
            "line": station_line,
            "colour": station.get("colour"),
            "transport_type": station.get("transport_type", "metro"),
            "flooded": status == "unsafe",
            "status": status,
            "risk_score": round(ema_score, 3),
            "max_depth_m": round(max_depth, 3),
            "mean_depth_m": round(mean_depth, 3),
            "access_viability": round(access_viability, 3),
            "confidence": confidence,
            "confidence_reason": confidence_reason,
        })

    return reports

async def get_all_regions():
    """Return the hierarchy tree of regions."""
    return REGIONS_TREE

async def get_hobli_population(hobli_name: str):
    """Business logic to fetch and format population data."""
    key = norm_key(hobli_name)
    data = get_population(key)
    if data:
        return {
            "hobli":            hobli_name,
            "total_population": data["total"],
            "male":             data["male"],
            "female":           data["female"],
            "matched_wards":    data["matched_wards"],
            "taluk":            data.get("taluk", ""),
            "source":           "csv",
        }
    return {
        "hobli":            hobli_name,
        "total_population": 0,
        "male":             0,
        "female":           0,
        "matched_wards":    [],
        "taluk":            "",
        "source":           "none",
    }

async def process_load_region(hobli_name: str):
    """Handle coordinate retrieval and graph lazy-loading."""
    key = norm_key(hobli_name)
    coords = HOBLI_COORDS.get(key)
    if not coords:
        raise HTTPException(status_code=404, detail=f"Hobli '{hobli_name}' not in coordinate map.")

    try:
        loop = asyncio.get_event_loop()
        # 1) Offload CPU-bound graph loading to executor
        await loop.run_in_executor(None, get_region, key)
    except ConnectionError as e:
        # Overpass API unreachable — clear message for the user
        print(f"[ERROR] Overpass API unreachable for '{key}': {e}")
        raise HTTPException(
            status_code=503,
            detail=f"This region hasn't been cached yet and the map data server "
                   f"is temporarily unreachable. Please try again in a few minutes, "
                   f"or contact the administrator to pre-cache this region."
        )
    except Exception as e:
        print(f"[ERROR] Graph loading failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to load graph: {e}")

    # 2) Metro extraction — non-fatal; if Overpass is unreachable the region
    #    still loads with its road network and cached data.
    metro_lines = {"type": "FeatureCollection", "features": []}
    metro_stations = []
    try:
        from region_manager import extract_metro_data, REGION_CACHE as _RC
        metro_entry = await loop.run_in_executor(None, extract_metro_data, key, True)
        metro_lines = metro_entry.get("metro_lines", metro_lines)
        metro_stations = metro_entry.get("metro_stations", metro_stations)
    except Exception as e:
        print(f"[WARN] Metro extraction failed (non-fatal, returning region without metro): {e}")
        # Try to get whatever is already in the in-memory cache
        cached_entry = _RC.get(key, {}) if '_RC' in dir() else {}
        metro_stations = cached_entry.get("metro_stations", [])
        metro_lines = cached_entry.get("metro_lines", metro_lines)
    
    # Ensure metro_lines is a FeatureCollection
    if isinstance(metro_lines, dict) and metro_lines.get("type") == "FeatureCollection":
        print(f"[metro] Returning {len(metro_lines.get('features', []))} line segments")
    elif isinstance(metro_lines, list):
        print(f"[metro] Converting metro_lines array to FeatureCollection ({len(metro_lines)} features)")
        metro_lines = {"type": "FeatureCollection", "features": metro_lines}
    else:
        print(f"[metro] WARNING: Unexpected metro_lines format: {type(metro_lines)}")
        metro_lines = {"type": "FeatureCollection", "features": []}

    return {
        "status":   "loaded",
        "hobli":    hobli_name,
        "lat":      coords["lat"],
        "lon":      coords["lon"],
        "district": coords["district"],
        "metro_stations": metro_stations,
        "metro_lines": metro_lines,
    }

def _haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance in kilometers between two points."""
    R = 6371  # Earth radius in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2) * math.sin(dLat / 2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon / 2) * math.sin(dLon / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def _resolve_road_name(nid, G, max_depth=3):
    """
    Traverse the graph from nid up to max_depth levels to find a readable road name.
    Useful for unnamed residential junctions that connect to named roads nearby.
    """
    from collections import deque
    queue = deque([(nid, 0)])
    visited = {nid}
    names = set()

    while queue:
        curr, depth = queue.popleft()

        # Check incident edges for names
        try:
            # MultiDiGraph usually stores names on edges
            edge_iter = G.edges(curr, data=True)
            for _, _, edata in edge_iter:
                nm = edata.get('name')
                if nm:
                    if isinstance(nm, list): names.update(nm)
                    else: names.add(nm)
            
            # For directed graphs, check incoming too
            if hasattr(G, 'in_edges'):
                for _, _, edata in G.in_edges(curr, data=True):
                    nm = edata.get('name')
                    if nm:
                         if isinstance(nm, list): names.update(nm)
                         else: names.add(nm)
        except Exception:
            pass

        # Stop as soon as we've found some names at this depth
        if names:
            break

        # Move to neighbors if we haven't found a name yet
        if depth < max_depth:
            try:
                # Treat directed graph as undirected for name search
                succs = list(G.successors(curr)) if hasattr(G, 'successors') else []
                preds = list(G.predecessors(curr)) if hasattr(G, 'predecessors') else []
                for neighbor in set(succs + preds):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))
            except Exception:
                pass

    # Prefer shorter, cleaner names (road names beat highway codes)
    # Filter out common abbreviations of highway codes
    clean = [n for n in names if n and len(n) > 2 and not n.startswith(('NH', 'SH', 'MDR', 'KA'))]
    
    if clean:
        return sorted(clean, key=len)[0]   # shortest meaningful name
    if names:
        return sorted(list(names), key=len)[0]
    return None

async def fetch_resources(location: str):
    """
    Look up IDRN resources for the given location string.
    If no matches found (or location is 'Unknown'), return default set (Bengaluru).
    """
    try:
        # Load activity mapping from MongoDB if not already in memory
        if not hasattr(fetch_resources, "activity_map"):
            fetch_resources.activity_map = {}
            from db import get_resource_definitions
            data = get_resource_definitions()
            for activity, categories in data.items():
                for cat_name, items in categories.items():
                    for item in items:
                        item_name = item.get("name", "").lower() if isinstance(item, dict) else str(item).lower()
                        fetch_resources.activity_map[item_name] = activity

        # Load resource DataFrames from MongoDB if not already in memory
        if not hasattr(fetch_resources, "cache") or fetch_resources.cache is None or fetch_resources.cache.empty:
            from db import get_logistics_df, get_tactical_df, get_idrn_df
            dfs = []
            try:
                cdf_log = get_logistics_df()
                cdf_log["Category"] = "Logistics"
                dfs.append(cdf_log)
                cdf_tac = get_tactical_df()
                if "Category" not in cdf_tac.columns:
                    cdf_tac["Category"] = "Tactical"
                dfs.append(cdf_tac)
            except Exception:
                dfs.append(get_idrn_df())

            if dfs:
                df = pd.concat(dfs, ignore_index=True).fillna("N/A")
                fetch_resources.cache = df
            else:
                return []
        else:
            df = fetch_resources.cache

        # Get target coordinates for distance calculation
        target_lat, target_lon = 12.9716, 77.5946 # Default Bengaluru
        norm_loc = norm_key(location)
        
        if norm_loc in HOBLI_COORDS:
             coords = HOBLI_COORDS[norm_loc]
             if isinstance(coords, dict):
                 target_lat, target_lon = coords.get('lat'), coords.get('lon')
             else:
                 target_lat, target_lon = coords[0], coords[1]
        
        # Calculate distances
        t_lat, t_lon = float(target_lat), float(target_lon)
        filtered = df.copy()
        distances, cats = [], []
        
        for idx, row in filtered.iterrows():
            try:
                r_lat = float(str(row.get("Latitude", "0")).replace(',', '').strip() or 0)
                r_lon = float(str(row.get("Longitude", "0")).replace(',', '').strip() or 0)
                
                if r_lat == 0 or r_lon == 0:
                    d = 99999.0
                else:
                    d = _haversine_distance(t_lat, t_lon, r_lat, r_lon)
                
                distances.append(d)
                if d < 5.0: cats.append("Immediate")
                elif d < 15.0: cats.append("Extended")
                else: cats.append("Distant")
            except:
                distances.append(99999.0)
                cats.append("Distant")
        
        filtered['temp_dist'] = distances
        filtered['dist_cat'] = cats
        filtered = filtered.sort_values('temp_dist', ascending=True)
        
        results = []
        for idx, row in filtered.iterrows():
            item_name = str(row.get("Item Name", "Unknown Item"))
            dist_val = row['temp_dist']
            dist_str = f"{dist_val:.1f} km" if dist_val < 90000 else "N/A"
            activity_cat = fetch_resources.activity_map.get(item_name.lower(), "General Resource")
            
            results.append({
                "item": item_name,
                "item_code": str(row.get("Item Code", "")),
                "qty": str(row.get("Quantity", "N/A")), 
                "source": str(row.get("Department", "Unknown Source")),
                "contact": str(row.get("Contact Name", "")),
                "phone": str(row.get("Phone", "")),
                "distance": dist_str,
                "distance_val": dist_val,
                "category_distance": row['dist_cat'],
                "type": str(row.get("Category", "Other")),
                "activity": activity_cat,
                "address": str(row.get("Address", "N/A"))
            })
        return results
    except Exception as e:
        print(f"[ERROR] Service fetch_resources: {e}")
        return []

async def fetch_rainfall_records(hobli_name: str):
    """Retrieve and sort rainfall records."""
    key = norm_key(hobli_name)
    entries = RAINFALL_DATA.get(key)
    if not entries:
        raise HTTPException(status_code=404, detail=f"No rainfall data for '{hobli_name}'.")

    try:
        sorted_entries = sorted(
            entries,
            key=lambda e: pd.to_datetime(e["date"], dayfirst=True),
        )
    except Exception:
        sorted_entries = entries

    return {"hobli": hobli_name, "count": len(sorted_entries), "records": sorted_entries}

async def fetch_map_geojson(hobli_name: str):
    """Retrieve graph and convert to GeoJSON."""
    key = norm_key(hobli_name)
    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli_name}' not loaded.")
    
    G = REGION_CACHE[key]["G"]
    # ox.graph_to_gdfs returns (nodes, edges)
    _, edges = ox.graph_to_gdfs(G)
    return json.loads(edges.to_json())

# ─────────────────────────────────────────────────────────────────────────────
# Shelter Suggestion Engine
# ─────────────────────────────────────────────────────────────────────────────

def _compute_shelter_suggestions(at_risk_nodes: list, safe_shelters: list, G, final_evacuation_plan: list) -> list:
    """
    When evacuation coverage is incomplete, identify geographic clusters of
    unassigned at-risk nodes and suggest new shelter locations in nearby
    non-flooded areas.

    Generates ENOUGH suggestions to cover ALL unassigned people — no arbitrary
    cap. Each cluster gets exactly one shelter sized to cover its population.

    Returns a tuple (suggestions_list, genuinely_unreachable_count).
    """
    if not at_risk_nodes:
        return [], 0

    # ── 1. Determine which node groups were NOT assigned a shelter ─────────
    assigned_node_ids = {move['from_node'] for move in final_evacuation_plan}
    unassigned = [
        node for node in at_risk_nodes
        if node['id'] not in assigned_node_ids
    ]

    if not unassigned:
        return [], 0

    total_deficit = sum(n['pop'] for n in unassigned)
    print(f"  [SHELTER-SUGGEST] {len(unassigned)} unassigned groups | "
          f"total deficit={total_deficit:,} | will generate shelters until fully covered")

    # ── 2. Compute region center for compass-direction naming ─────────────
    all_lats = [n['lat'] for n in at_risk_nodes]
    all_lons = [n['lon'] for n in at_risk_nodes]
    region_center_lat = sum(all_lats) / len(all_lats)
    region_center_lon = sum(all_lons) / len(all_lons)

    def _compass(c_lat, c_lon):
        """Return cardinal/intercardinal direction label from region center."""
        dlat = c_lat - region_center_lat
        dlon = c_lon - region_center_lon
        # 8-point compass
        angle = math.degrees(math.atan2(dlon, dlat))  # 0=N, 90=E, -90=W
        directions = [
            (22.5,  'North'),    (67.5,  'Northeast'), (112.5, 'East'),
            (157.5, 'Southeast'),(180.1, 'South'),
        ]
        neg_dirs = [
            (-22.5, 'North'),   (-67.5, 'Northwest'), (-112.5, 'West'),
            (-157.5, 'Southwest'), (-180.1, 'South'),
        ]
        if angle >= 0:
            for threshold, label in directions:
                if angle <= threshold:
                    return label
            return 'South'
        else:
            for threshold, label in neg_dirs:
                if angle >= threshold:
                    return label
            return 'South'

    # ── 3. Filter genuinely unreachable vs serviceable ────────────────────────
    import networkx as nx
    wadable_nodes = {
        nid for nid, data in G.nodes(data=True)
        if data.get('water_depth', 0.0) <= 0.15
    }
    
    # NEW: Filter EDGES as well. An edge is only traversable if its depth is safe.
    wadable_edges = []
    for u, v, k, data in G.edges(data=True, keys=True):
        if u in wadable_nodes and v in wadable_nodes:
            # Check edge-specific depth if it exists
            if data.get('water_depth', 0.0) <= 0.15:
                wadable_edges.append((u, v, k))
                
    # Build a graph of TRULY walkable paths (no submerged bridges/dips)
    wadable_subgraph = G.edge_subgraph(wadable_edges).to_undirected()
    
    node_to_component = {}
    component_driest_node = {}
    component_nodes = {}
    
    for i, comp in enumerate(nx.connected_components(wadable_subgraph)):
        comp_list = list(comp)
        component_nodes[i] = comp_list
        # Find the safest node in this island
        driest_n = min(comp_list, key=lambda n: G.nodes[n].get('water_depth', 0.0))
        component_driest_node[i] = driest_n
        for n in comp_list:
            node_to_component[n] = i

    genuinely_unreachable_count = 0
    serviceable_unassigned = []
    SNAP_RADIUS_DEG = 0.003  # ~300m — must match service.py classification

    all_wadable_list = list(wadable_nodes)
    if all_wadable_list:
        wadable_coords = np.array([
            [G.nodes[n]['y'], G.nodes[n]['x']] for n in all_wadable_list
        ])
        for node in unassigned:
            nid = node['id']
            comp_id = node_to_component.get(nid)

            if comp_id is None:
                # Node is on flooded ground — snap to nearest dry component (same as service.py)
                p = np.array([node['lat'], node['lon']])
                dist_sq = np.sum((wadable_coords - p) ** 2, axis=1)
                if np.min(dist_sq) <= SNAP_RADIUS_DEG ** 2:
                    nearest_dry_nid = all_wadable_list[int(np.argmin(dist_sq))]
                    comp_id = node_to_component.get(nearest_dry_nid)

            if comp_id is not None:
                node['comp_id'] = comp_id
                serviceable_unassigned.append(node)
            else:
                genuinely_unreachable_count += node['pop']
    else:
        for node in unassigned:
            genuinely_unreachable_count += node['pop']

    if not serviceable_unassigned:
        return [], genuinely_unreachable_count

    # ── 4. Cluster serviceable nodes by (Island Component, Geographic Cell) ─
    # Smaller 0.008° grid (~880 m) — tighter clusters = more accurate capacity
    GRID_SIZE = 0.008
    clusters: dict = {}
    for node in serviceable_unassigned:
        cell = (round(node['lat'] / GRID_SIZE), round(node['lon'] / GRID_SIZE))
        cluster_key = (node['comp_id'], cell)
        if cluster_key not in clusters:
            clusters[cluster_key] = {'nodes': [], 'total_pop': 0, 'comp_id': node['comp_id']}
        clusters[cluster_key]['nodes'].append(node)
        clusters[cluster_key]['total_pop'] += node['pop']

    def _approx_dist_deg(lat1, lon1, lat2, lon2):
        return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)

    # (Function _resolve_road_name moved to top level for reuse)

    existing_shelter_coords = [(s['lat'], s['lon']) for s in safe_shelters]
    used_dry_nodes = set()          # avoid re-suggesting the exact same spot
    suggestions = []
    zone_counters = {}              # compass_direction → sequential counter

    # Process clusters largest-first so biggest deficits get addressed first
    sorted_clusters = sorted(clusters.items(), key=lambda x: -x[1]['total_pop'])

    for cluster_key, info in sorted_clusters:
        comp_id = info['comp_id']
        nodes = info['nodes']
        deficit_pop = info['total_pop']

        # Cluster centroid
        c_lat = sum(n['lat'] for n in nodes) / len(nodes)
        c_lon = sum(n['lon'] for n in nodes) / len(nodes)

        # Compass direction for this cluster
        direction = _compass(c_lat, c_lon)
        zone_counters[direction] = zone_counters.get(direction, 0) + 1
        zone_num = zone_counters[direction]
        zone_label = f"{direction} Zone {zone_num}"

        best_nid = None
        
        # ── Find best shelter node in THIS component ────────────────────
        import osmnx as ox
        
        # Strategy A: 'Hyper-local' — Search for safest junction within 500m for realistic placement
        try:
            # We want nodes that are within ~0.005 degrees (~500m) of the cluster center
            # and MUST be in the same reachable component.
            local_candidates = [
                n for n in component_nodes[comp_id]
                if _approx_dist_deg(c_lat, c_lon, G.nodes[n]['y'], G.nodes[n]['x']) < 0.005
            ]
            if local_candidates:
                # Pick the driest one in the local radius
                best_nid = min(local_candidates, key=lambda n: G.nodes[n].get('water_depth', 0.0))
        except:
            pass

        # Strategy B: Fallback to component-wide driest if no local nodes found
        if best_nid is None:
            comp_n_list = component_nodes[comp_id]
            t_depth = G.nodes[component_driest_node[comp_id]].get('water_depth', 0.0)
            
            # Nodes in this island that are as dry as the driest one
            cand_nodes = [n for n in comp_n_list if G.nodes[n].get('water_depth', 0.0) <= t_depth + 0.02]
            
            cand_sorted = sorted(
                cand_nodes,
                key=lambda n: _approx_dist_deg(c_lat, c_lon, G.nodes[n]['y'], G.nodes[n]['x'])
            )
            for cand in cand_sorted:
                if cand not in used_dry_nodes:
                    best_nid = cand
                    break
            if best_nid is None and cand_sorted:
                best_nid = cand_sorted[0]
            elif best_nid is None:
                best_nid = component_driest_node[comp_id]
            
        best_lat = G.nodes[best_nid]['y']
        best_lon = G.nodes[best_nid]['x']

        if best_nid:
            used_dry_nodes.add(best_nid)

        # ── Name resolution ───────────────────────────────────────────────
        road_name = _resolve_road_name(best_nid, G) if best_nid else None

        if road_name:
            area_name = f"{zone_label} · {road_name}"
        else:
            # Compass zone is always meaningful — no lat/lon fallback
            area_name = f"Emergency Shelter — {zone_label}"

        # Nearest existing shelter distance
        nearest_shelter_dist_km = min(
            _haversine_distance(c_lat, c_lon, sl, so)
            for sl, so in existing_shelter_coords
        ) if existing_shelter_coords else 0.0

        # Buffer to 2.5x to guarantee 100% evacuation even with small clustering gaps
        suggested_cap = int(math.ceil(deficit_pop * 2.5))

        if deficit_pop > 500 or nearest_shelter_dist_km > 2.0:
            priority = 'high'
        elif deficit_pop > 100:
            priority = 'medium'
        else:
            priority = 'low'

        suggestions.append({
            'lat':                best_lat,
            'lon':                best_lon,
            'area_name':          area_name,
            'deficit_population': deficit_pop,
            'suggested_capacity': suggested_cap,
            'nearest_shelter_km': round(nearest_shelter_dist_km, 2),
            'reason': (
                f"{len(nodes)} at-risk group(s) with {deficit_pop:,} people have no shelter. "
                f"Nearest existing shelter is {nearest_shelter_dist_km:.1f} km away."
            ),
            'priority': priority,
        })

    # ── 5. Verify total coverage ──────────────────────────────────────────
    covered = sum(s['suggested_capacity'] for s in suggestions)
    print(f"  [SHELTER-SUGGEST] {len(suggestions)} new shelter(s) suggested | "
          f"total suggested cap={covered:,} vs deficit={total_deficit:,}")

    # Sort highest-deficit first — no arbitrary cap; caller gets all of them
    suggestions.sort(key=lambda x: -x['deficit_population'])
    return suggestions, genuinely_unreachable_count


# Global cache to persist state for Incremental Stateful Re-runs.
# This prevents "stealing" of newly generated emergency shelter capacity by 
# people who were already successfully evacuated in the first run.
SIMULATION_SESSION_CACHE = {
    "pinned_routes": []
}

# Global cache to share state between Compare mode and Analyze mode
# to prevent re-running flood simulations and to reuse the first execution.
COMPARE_ANALYSIS_CACHE = {}

def _reconstruct_chromosome(decoded_plan, at_risk, safe_shelters) -> list[int]:
    """Reconstruct an assignment chromosome array from a decoded evacuation plan."""
    n_r = len(at_risk)
    chromosome = [-1] * n_r   # -1 = unassigned
    for move in decoded_plan:
        origin_id = move.get("from_node")
        for idx, node in enumerate(at_risk):
            if node["id"] == origin_id:
                shelter_id = move.get("to_shelter")
                for j, sh in enumerate(safe_shelters):
                    if sh["id"] == shelter_id:
                        chromosome[idx] = j
                        break
                break
    return chromosome


async def run_simulation_generator(hobli: str, rainfall_mm: float, steps: int, decay_factor: float, evacuation_mode: bool = False, use_traffic: bool = False, algorithm: str = "ga", population: int | None = None, extra_shelters: list | None = None, mode: str = "progressive"):
    """Generator for SSE simulation stream."""
    import time
    loop = asyncio.get_event_loop()
    key = norm_key(hobli)
    if key not in REGION_CACHE:
        try:
            await loop.run_in_executor(None, get_region, key)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Region '{hobli}' not loaded: {e}")

    entry = REGION_CACHE[key]
    G_ref = entry["G"]
    drains = entry["drain_nodes"]
    lakes = entry["lake_nodes"]

    sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)

    # Mode selection
    if mode == "progressive":
        sim.set_progressive_rainfall(rainfall_mm, steps)
    else:
        sim.initialize_from_drains(rainfall_mm)

    # 1. Distribute population on nodes
    if population is not None:
        total_pop = population
    else:
        pop_data = await get_hobli_population(hobli)
        total_pop = pop_data.get("total_population", 0)

    # Scale population if in evacuation mode (1% test)
    if evacuation_mode:
        total_pop = max(1, total_pop // 100)
        print(f"{_ts()}  [service] Evacuation Mode ON: scaling population to {total_pop}")

    sim.distribute_population(total_pop)

    # 2. Pre-fetch shelters (OSM candidates), then merge any synthetic suggested shelters
    shelter_resp = await fetch_shelters(hobli)
    all_shelters = shelter_resp["shelters"]

    if extra_shelters:
        G_snap = REGION_CACHE[key]["G"]
        import osmnx as ox
        for idx, es in enumerate(extra_shelters):
            try:
                node_id = ox.distance.nearest_nodes(G_snap, es['lon'], es['lat'])
            except Exception:
                node_id = None
            synthetic = {
                "id":       f"suggested_{idx + 1}",
                "name":     es.get('area_name', f"Suggested Shelter {idx + 1}"),
                "type":     "synthetic",
                "lat":      es['lat'],
                "lon":      es['lon'],
                "capacity": int(es.get('suggested_capacity', 500)),
                "node_id":  node_id,
                "safe":     True,   # backend confirmed it's on a dry node
            }
            all_shelters.append(synthetic)
            print(f"  [RERUN] Injected synthetic shelter '{synthetic['name']}' cap={synthetic['capacity']} node={node_id}")


    # ── Streaming loop: flood physics only, no GA ─────────────────────────
    metro_stations = entry.get("metro_stations", [])

    coords = HOBLI_COORDS.get(key, {})
    center_lat = coords.get("lat")
    center_lon = coords.get("lon")
    
    for i in range(steps):
        # Check abort flag
        import main as main_module
        if main_module._sim_abort:
            logger.info(f"[SIMULATE] Simulation aborted by user at step {i+1}/{steps}")
            yield f"data: {json.dumps({'done': True, 'aborted': True, 'error': 'Simulation stopped by user'})}\n\n"
            return

        await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
        impact = await loop.run_in_executor(None, sim.calculate_flood_impact)

        _collect_metro_reports(sim, metro_stations, center_lat, center_lon, update_history=True)
        flood_gdf = impact["flood_gdf"]
        roads_gdf = impact["roads_gdf"]

        step_data = {
            "step":          i + 1,
            "total":         steps,
            "flood_geojson": json.loads(flood_gdf.to_json()) if not flood_gdf.empty
                             else {"type": "FeatureCollection", "features": []},
            "roads_geojson": json.loads(roads_gdf.to_json()) if not roads_gdf.empty
                             else {"type": "FeatureCollection", "features": []},
            "evacuation_plan": [],   # empty during streaming — shown only at end
        }
        yield f"data: {json.dumps(step_data)}\n\n"

    # ── Post-simulation: run GA once with final flood state ───────────────
    final_evacuation_plan = []
    ga_execution_time = 0.0
    best_fitness = 0.0

    algo_label = algorithm.upper()
    print(f"\n{_ts()} {'='*56}")
    print(f"{_ts()}  [{algo_label}] evacuation_mode = {evacuation_mode} (controls pop scaling only)")
    print(f"{_ts()}  [{algo_label}] all_shelters count = {len(all_shelters)}")

    # Algorithm always runs — evacuation_mode only affects 1% pop scaling above
    # Recalculate final flood impact for shelter safety classification
    final_impact = await loop.run_in_executor(None, sim.calculate_flood_impact)
    final_flood_gdf = final_impact["flood_gdf"]
    final_roads_gdf = final_impact["roads_gdf"]
    final_flood_geojson = (
        json.loads(final_flood_gdf.to_json()) if not final_flood_gdf.empty else None
    )
    final_roads_geojson = (
        json.loads(final_roads_gdf.to_json()) if not final_roads_gdf.empty else None
    )
    print(f"{_ts()}  [DEBUG] final flood features = {len(final_flood_geojson['features']) if final_flood_geojson else 0}")

    # Filter shelters: only truly safe shelters are eligible for evacuation
    shelters_with_safety = filter_safe_shelters(all_shelters, final_flood_geojson, final_roads_geojson)
    
    # CRITICAL FIX: Ensure synthetic shelters (suggested for reruns) are always treated as safe.
    # The suggestion engine already picked the best available dry/wadable spot for them.
    for s in shelters_with_safety:
        if s.get("type") == "synthetic":
            s["safe"] = True

    safe_shelters = [s for s in shelters_with_safety if s["safe"]]
    safe_count = len(safe_shelters)
    print(f"{_ts()}  [DEBUG] safe shelters after filter = {safe_count} / {len(shelters_with_safety)}")
    for s in shelters_with_safety[:5]:
        print(f"{_ts()}    shelter: {s['name']} | safe={s['safe']} | cap={s['capacity']} | node_id={s.get('node_id')}")

    if not safe_shelters:
        print(f"{_ts()}  [DEBUG] WARNING: no safe shelters available — evacuation routing will be skipped")

    at_risk = sim.get_at_risk_nodes(depth_threshold_m=0.05)
    print(f"{_ts()}  [DEBUG] at_risk nodes = {len(at_risk)}")

    # Diagnostic: check sample depths and populations
    sample_nodes = list(sim.G.nodes())[:5]
    node_depths_sample = {n: round(sim.G.nodes[n].get('water_depth', 0), 3) for n in sample_nodes}
    pop_sample = {n: sim.node_populations.get(n, 0) for n in sample_nodes}
    print(f"{_ts()}  [DEBUG] sample node depths: {node_depths_sample}")
    print(f"{_ts()}  [DEBUG] sample node pops:   {pop_sample}")
    print(f"{_ts()}  [DEBUG] total_pop distributed: {sum(sim.node_populations.values())}")

    # Track total at-risk population BEFORE GA runs (for accurate remaining count)
    total_at_risk_before_ga = sum(pop for _, pop in at_risk)
    print(f"{_ts()}  [DEBUG] total at-risk pop before GA = {total_at_risk_before_ga}")

    # ── Reachability Classification (Serviceable vs Genuinely Stranded) ───────
    import networkx as nx
    wadable_nodes = {
        nid for nid, data in sim.G.nodes(data=True)
        if data.get('water_depth', 0.0) <= 0.15
    }
    wadable_edges = [
        (u, v, k) for u, v, k, data in sim.G.edges(data=True, keys=True)
        if u in wadable_nodes and v in wadable_nodes and data.get('water_depth', 0.0) <= 0.15
    ]
    wadable_subgraph = sim.G.edge_subgraph(wadable_edges).to_undirected()
    serviceable_nids = set(wadable_subgraph.nodes())

    # Snap-based reachability: even if a node is flooded (depth > 0.15m),
    # the person can wade to the nearest dry road IF it's within ~300m.
    # Only classify as truly "Stranded" if no dry road exists within that radius.
    SNAP_RADIUS_DEG = 0.003   # ~300m in degrees latitude
    genuinely_unreachable_count = 0
    stranded_nids = set()

    all_wadable_list = list(wadable_nodes)
    if all_wadable_list:
        wadable_coords = np.array([
            [sim.G.nodes[n]['y'], sim.G.nodes[n]['x']] for n in all_wadable_list
        ])
        for nid, pop in at_risk:
            if nid in serviceable_nids:
                continue  # already on dry walkable ground
            # Flooded node — check if a dry road is within snap radius
            p = np.array([sim.G.nodes[nid]['y'], sim.G.nodes[nid]['x']])
            dist_sq = np.sum((wadable_coords - p) ** 2, axis=1)
            if np.min(dist_sq) > SNAP_RADIUS_DEG ** 2:
                # No dry road within radius → genuinely stranded, needs boat rescue
                stranded_nids.add(nid)
                genuinely_unreachable_count += pop
            # else: can wade to dry road → leave as serviceable (not in stranded_nids)
    else:
        # Total catastrophe — no dry land anywhere
        for nid, pop in at_risk:
            stranded_nids.add(nid)
            genuinely_unreachable_count += pop

    print(f"{_ts()}  [DEBUG] Stranded population (Needs Rescue): {genuinely_unreachable_count:,}")


    planner_instance = None  # sentinel for traffic geojson extraction
    pressure_points = []
    
    # ── STATEFUL RE-RUN LOGIC ───────────────────────────────────────────────
    is_rerun = bool(extra_shelters is not None and len(extra_shelters) > 0)

    used_capacity = {}
    pinned_node_ids = set()
    
    if is_rerun:
        for route in SIMULATION_SESSION_CACHE["pinned_routes"]:
            uid = route.get('from_node')
            sid = route.get('to_shelter')
            p = route.get('pop', 0)
            used_capacity[sid] = used_capacity.get(sid, 0) + p
            pinned_node_ids.add(uid)

        # Deduct capacity consumed by people evacuated in the previous run
        deduct_count = 0
        pinned_pop = sum(r.get('pop', 0) for r in SIMULATION_SESSION_CACHE["pinned_routes"])
        print(f"{_ts()}  [STATE] Re-run detected. Pinning {len(SIMULATION_SESSION_CACHE['pinned_routes'])} routes ({pinned_pop:,} people).")
        
        for s in safe_shelters:
            sid = s.get('id')
            if sid in used_capacity:
                used = used_capacity[sid]
                s['capacity'] = max(0, s['capacity'] - used)
                deduct_count += 1
        print(f"{_ts()}  [STATE] Adjusted capacity for {deduct_count} existing safe shelters.")
    else:
        # Reset cache on a fresh run
        SIMULATION_SESSION_CACHE["pinned_routes"] = []

    initial_evacuated_count = sim.total_evacuated
    at_risk_formatted = []  # initialised here — used later for shelter suggestions
    if at_risk and safe_shelters:
        for nid, pop in at_risk:
            # Skip physically stranded people. Only deploy AI on serviceable locations.
            if nid in stranded_nids:
                continue
            # If stateful re-run, skip people who were successfully assigned previously
            if is_rerun and nid in pinned_node_ids:
                continue
            at_risk_formatted.append(
                {"id": nid, "pop": pop, "lat": sim.G.nodes[nid]["y"], "lon": sim.G.nodes[nid]["x"]}
            )
        
        print(f"{_ts()}  [{algo_label}] Running {algo_label}: {len(at_risk_formatted)} at-risk groups → {len(safe_shelters)} shelters")


        ga_start = time.time()
        try:
            # Scale parameters based on problem size for speed
            n_risk = len(at_risk_formatted)
            gens   = max(15, min(60, 3000 // max(n_risk, 1)))
            pop_sz = min(60, max(20, n_risk * 2))
            print(f"{_ts()}  [{algo_label}] Params: pop_size/n_particles/n_ants={pop_sz}, iterations/generations={gens}")

            PlannerClass = _get_planner_class(algorithm)

            # ── Run init + evolution in executor ───────────────────────────────
            # IMPORTANT: PlannerClass.__init__ does Dijkstra precompute AND TomTom
            # traffic fetching (100 HTTP requests via ThreadPoolExecutor). If called
            # directly in the async event loop it blocks the SSE stream.
            # Wrapping BOTH init and run() in a single executor call keeps the loop free.
            def _init_and_run():
                instance = PlannerClass(
                    at_risk_formatted, safe_shelters, sim.G,
                    pop_size=pop_sz, generations=gens,
                    n_ants=pop_sz, iterations=gens,
                    n_particles=pop_sz,
                    use_tomtom_traffic=use_traffic,
                )
                routes = instance.run()
                return instance, routes

            planner_instance, new_routes = await loop.run_in_executor(None, _init_and_run)

            # Recombine pinned routes from previous runs with the newly generated routes
            if is_rerun:
                final_evacuation_plan = new_routes + SIMULATION_SESSION_CACHE["pinned_routes"]
                new_pop = sum(r.get('pop', 0) for r in new_routes)
                pinned_pop = sum(r.get('pop', 0) for r in SIMULATION_SESSION_CACHE["pinned_routes"])
                print(f"{_ts()}  [STATE] Combined: {len(new_routes)} new routes + {len(SIMULATION_SESSION_CACHE['pinned_routes'])} pinned = {len(final_evacuation_plan)} total.")
            else:
                final_evacuation_plan = new_routes
                
            # Update the global cache for subsequent consecutive re-runs
            SIMULATION_SESSION_CACHE["pinned_routes"] = final_evacuation_plan

            ga_execution_time = round(time.time() - ga_start, 2)
            print(f"{_ts()}  [{algo_label}] complete: {len(final_evacuation_plan)} total combined routes in {ga_execution_time}s")
            best_fitness = round(getattr(planner_instance, 'best_fitness', 0.0), 1)
            print(f"{_ts()}  [{algo_label}] best_fitness = {best_fitness}")

            # Calculate pressure points (converging routes / bottlenecks)
            pressure_points = planner_instance.calculate_pressure_points(final_evacuation_plan)
            print(f"{_ts()}  [{algo_label}] extracted {len(pressure_points)} pressure junctures")

        except Exception as e:
            import traceback
            print(f"{_ts()}  [DEBUG] *** {algo_label} EXCEPTION: {e} ***")
            traceback.print_exc()
            ga_execution_time = round(time.time() - ga_start, 2)
            pressure_points = []

        # Update shelter occupancy from GA result
        for move in final_evacuation_plan:
            sim.shelter_occupancy[move["to_shelter"]] = (
                sim.shelter_occupancy.get(move["to_shelter"], 0) + move["pop"]
            )
            sim.total_evacuated += move["pop"]
        print(f"{_ts()}  [DEBUG] total_evacuated = {sim.total_evacuated}")
    else:
        print(f"{_ts()}  [DEBUG] *** BLOCKED: at_risk and/or safe_shelters is empty — {algo_label} skipped ***")
    # Final Outcome Verification Logs
    # total_at_risk_before_ga includes EVERYONE who needs a home (Serviceable + Stranded)
    current_request_evacuated = sim.total_evacuated - initial_evacuated_count
    
    # The true 'At Risk (Cap)' are those who didn't get evacuated but ARE within a wadable component.
    # Since we don't have the global 'unassigned' list easily here, we derive it:
    at_risk_cap = max(0, total_at_risk_before_ga - current_request_evacuated - genuinely_unreachable_count)
    
    print(f"{_ts()}  [DEBUG] FINAL CONSISTENCY CHECK:")
    print(f"{_ts()}    - Total Evacuated: {sim.total_evacuated:,}")
    print(f"{_ts()}    - At Risk (Cap):   {at_risk_cap:,}")
    print(f"{_ts()}    - Stranded:        {genuinely_unreachable_count:,} (Needs Rescue)")
    print(f"{_ts()}    ----------------------------------------")
    print(f"{_ts()}    - Verification Sum: {sim.total_evacuated + at_risk_cap + genuinely_unreachable_count:,}")
    print(f"{_ts()} ========================================================\n")


    # Build shelter reports with fill percentage
    shelter_reports = [
        {
            "id":       s["id"],
            "name":     s.get("name", s["id"]),
            "type":     s.get("type", "unknown"),
            "occupancy": sim.shelter_occupancy.get(s["id"], 0),
            "capacity":  s["capacity"],
            "safe":      s.get("safe", True),
            "occupancy_pct": round(
                min(sim.shelter_occupancy.get(s["id"], 0) / max(s["capacity"], 1) * 100, 100), 1
            ),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
        }
        for s in shelters_with_safety
    ]

    # Correctly compute at-risk remaining: pre-GA count minus what GA evacuated
    total_assigned = sim.total_evacuated
    at_risk_remaining = max(0, total_at_risk_before_ga - total_assigned)

    # Extract traffic layer data (only if traffic was used and planner ran)
    traffic_geojson = None
    traffic_segment_count = 0
    if use_traffic and planner_instance is not None:
        try:
            traffic_geojson = planner_instance.get_traffic_geojson()
            traffic_segment_count = getattr(planner_instance, '_traffic_segment_count', 0)
        except Exception:
            pass

    # ── Compute shelter suggestions when coverage is incomplete ─────────────
    shelter_suggestions = []
    if at_risk_remaining > 0 and at_risk_formatted:
        shelter_suggestions, _ignored = _compute_shelter_suggestions(
            at_risk_formatted, safe_shelters, sim.G, final_evacuation_plan
        )
        print(f"{_ts()}  [SHELTER-SUGGEST] {len(shelter_suggestions)} suggestion(s) generated")


    final_report = {
        "done":      True,
        "total":     steps,
        "algorithm": algorithm.upper(),
        "evacuation_plan":      final_evacuation_plan,
        "traffic_geojson":      traffic_geojson,
        "traffic_segment_count": traffic_segment_count,
        "summary": {
            "simulation_location":     hobli,
            "total_evacuated":         total_assigned,
            "total_at_risk_remaining": at_risk_remaining,
            "genuinely_unreachable":   genuinely_unreachable_count,
            "total_at_risk_initial":   total_at_risk_before_ga,
            "simulation_population":   total_pop,
            "success_rate_pct":        round(
                total_assigned / max(total_at_risk_before_ga, 1) * 100, 1
            ),
            "rainfall_mm":             rainfall_mm,
            "algorithm":               algorithm.upper(),
            "ga_execution_time":       ga_execution_time,
            "best_fitness":            best_fitness,
            "avg_distance_per_person": round(
                best_fitness / max(total_at_risk_before_ga, 1), 1
            ),
            "shelter_reports":         shelter_reports,
            "pressure_points":         pressure_points,
            "shelter_suggestions":     shelter_suggestions,
            "metro_reports": _collect_metro_reports(sim, metro_stations,  center_lat, center_lon,update_history=True),
            "metro_lines": entry.get("metro_lines", []),
        },
    }
    try:
        yield f"data: {json.dumps(final_report)}\n\n"
    except (TypeError, ValueError):
        # traffic_geojson serialization failed — send without it
        final_report["traffic_geojson"] = None
        yield f"data: {json.dumps(final_report)}\n\n"




async def fetch_shelters(hobli_name: str) -> dict:
    """
    Extract shelter candidates for the hobli (OSM-queried, disk-cached).
    Safety evaluation happens on the frontend using live simulation state.
    """
    key = norm_key(hobli_name)

    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli_name}' not loaded.")

    entry  = REGION_CACHE[key]
    G      = entry["G"]
    coords = HOBLI_COORDS.get(key, {})
    lat    = coords.get("lat", G.nodes[list(G.nodes())[0]]["y"])
    lon    = coords.get("lon", G.nodes[list(G.nodes())[0]]["x"])

    loop = asyncio.get_event_loop()
    candidates = await loop.run_in_executor(
        None, extract_shelter_candidates, G, lat, lon, key
    )

    return {
        "hobli":    hobli_name,
        "total":    len(candidates),
        "shelters": candidates,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Compare generator — flood ONCE, then run GA + ACO + PSO in parallel
# ─────────────────────────────────────────────────────────────────────────────

async def run_compare_generator(
    hobli: str,
    rainfall_mm: float,
    steps: int,
    decay_factor: float,
    evacuation_mode: bool = False,
    use_traffic: bool = False,
    population: int | None = None,
    extra_shelters: list | None = None,
    mode: str = "instant",
):
    """
    SSE generator for compare mode:
      1. Flood simulation runs exactly once (same physics frames as single mode).
      2. After the last flood step, GA / ACO / PSO are initialised in parallel
         using a ThreadPoolExecutor. GA's costly Dijkstra + TomTom setup is used
         as a shared_setup for ACO and PSO, so the heavy precompute only happens once.
      3. Yields a single final 'compare_done' frame with all three results.
    """
    import time
    import concurrent.futures
    loop = asyncio.get_event_loop()

    if not hobli or hobli.strip() == "[object Object]":
        raise HTTPException(status_code=400, detail="Invalid hobli name '[object Object]'. Please reload region.")
    key = norm_key(hobli)
    if key not in REGION_CACHE:
        try:
            await loop.run_in_executor(None, get_region, key)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Region '{hobli}' not loaded: {e}")

    entry  = REGION_CACHE[key]
    G_ref  = entry["G"]
    drains = entry["drain_nodes"]
    lakes  = entry["lake_nodes"]

    sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)
    # Mode selection
    if mode == "progressive":
        sim.set_progressive_rainfall(rainfall_mm, steps)
    else:
        sim.initialize_from_drains(rainfall_mm)

    # Population
    if population is not None:
        total_pop = population
    else:
        pop_data  = await get_hobli_population(hobli)
        total_pop = pop_data.get("total_population", 0)
    if evacuation_mode:
        total_pop = max(1, total_pop // 100)
        print(f"{_ts()}  [compare] Evacuation Mode ON: scaling population to {total_pop}")
    sim.distribute_population(total_pop)

    # Shelters
    shelter_resp = await fetch_shelters(hobli)
    all_shelters = shelter_resp["shelters"]

    if extra_shelters:
        G_snap = REGION_CACHE[key]["G"]
        import osmnx as _ox_compare
        for idx, es in enumerate(extra_shelters):
            try:
                node_id = _ox_compare.distance.nearest_nodes(G_snap, es['lon'], es['lat'])
            except Exception:
                node_id = None
            synthetic = {
                "id":       f"suggested_{idx + 1}",
                "name":     es.get('area_name', f"Suggested Shelter {idx + 1}"),
                "type":     "synthetic",
                "lat":      es['lat'],
                "lon":      es['lon'],
                "capacity": int(es.get('suggested_capacity', 500)),
                "node_id":  node_id,
                "safe":     True,
            }
            all_shelters.append(synthetic)
            print(f"  [COMPARE RERUN] Injected synthetic shelter '{synthetic['name']}' cap={synthetic['capacity']}")


    # Extract center coordinates for metro reports
    coords = HOBLI_COORDS.get(key, {})
    center_lat = coords.get("lat")
    center_lon = coords.get("lon")

    # ── Phase 1: stream flood steps (identical to single-algo mode) ──────────
    metro_stations = entry.get("metro_stations", [])
    print(f"{_ts()}  [compare] Starting flood simulation ({steps} steps)")
    for i in range(steps):
        await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
        impact    = await loop.run_in_executor(None, sim.calculate_flood_impact)

        # Keep temporal metro status history warm at each step
        _collect_metro_reports(sim, metro_stations,  center_lat, center_lon,update_history=True)
        flood_gdf = impact["flood_gdf"]
        roads_gdf = impact["roads_gdf"]

        step_data = {
            "step":           i + 1,
            "total":          steps,
            "flood_geojson":  json.loads(flood_gdf.to_json()) if not flood_gdf.empty
                              else {"type": "FeatureCollection", "features": []},
            "roads_geojson":  json.loads(roads_gdf.to_json()) if not roads_gdf.empty
                              else {"type": "FeatureCollection", "features": []},
            "evacuation_plan": [],
        }
        yield f"data: {json.dumps(step_data)}\n\n"

    print(f"{_ts()}  [compare] Flood complete — computing final state")

    # ── Phase 2: final flood state & shelter classification ──────────────────
    final_impact      = await loop.run_in_executor(None, sim.calculate_flood_impact)
    final_flood_gdf   = final_impact["flood_gdf"]
    final_roads_gdf   = final_impact["roads_gdf"]
    final_flood_geojson = (
        json.loads(final_flood_gdf.to_json()) if not final_flood_gdf.empty else None
    )
    final_roads_geojson = (
        json.loads(final_roads_gdf.to_json()) if not final_roads_gdf.empty else None
    )

    shelters_with_safety = filter_safe_shelters(all_shelters, final_flood_geojson, final_roads_geojson)
    
    # CRITICAL FIX: Ensure synthetic shelters are always treated as safe in compare mode too
    for s in shelters_with_safety:
        if s.get("type") == "synthetic":
            s["safe"] = True

    safe_shelters        = [s for s in shelters_with_safety if s["safe"]]
    if not safe_shelters:
        print(f"{_ts()}  [compare] WARNING: no safe shelters available — planner execution will be skipped")

    at_risk = sim.get_at_risk_nodes(depth_threshold_m=0.05)

    total_at_risk_initial = sum(pop for _, pop in at_risk)
    print(f"{_ts()}  [compare] at_risk groups={len(at_risk)} | total_pop={total_at_risk_initial} | safe_shelters={len(safe_shelters)}")

    # ── Phase 3: run all three planners in parallel ──────────────────────────
    compare_results = {}

    if not at_risk or not safe_shelters:
        print(f"{_ts()}  [compare] BLOCKED: no at_risk or no safe_shelters — skipping planners")
    else:
        at_risk_formatted = [
            {"id": nid, "pop": pop, "lat": sim.G.nodes[nid]["y"], "lon": sim.G.nodes[nid]["x"]}
            for nid, pop in at_risk
        ]
        n_risk = len(at_risk_formatted)
        gens   = max(15, min(60, 3000 // max(n_risk, 1)))
        pop_sz = min(60, max(20, n_risk * 2))
        print(f"{_ts()}  [compare] Params: pop_sz={pop_sz}, gens={gens}")

        compare_start = time.time()

        # ── Step 3a: Initialise GA first (fetches TomTom traffic once if needed) ──
        # GA.__init__ calls _update_graph_with_tomtom_traffic() which writes
        # traffic_time/free_flow_time onto sim.G edges, then runs Dijkstra.
        # ACO and PSO receive ga_instance as shared_setup so they SKIP both
        # the traffic fetch AND the Dijkstra precompute entirely.
        print(f"{_ts()}  [compare] Initialising GA (traffic fetch + Dijkstra)…")

        def _init_ga():
            t0     = time.time()
            PClass = _get_planner_class("ga")
            instance = PClass(
                at_risk_formatted, safe_shelters, sim.G,
                pop_size=pop_sz, generations=gens,
                use_tomtom_traffic=use_traffic,   # ← traffic fetched HERE (once)
                shared_setup=None,
            )
            print(f"{_ts()}  [GA] init done (traffic+Dijkstra) in {round(time.time()-t0,2)}s")
            return instance

        ga_instance = await loop.run_in_executor(None, _init_ga)

        # ── Step 3b: Now run all three planners in parallel threads ─────────────
        # GA runs its evolution; ACO + PSO skip init (shared_setup) and go
        # straight to their own evolution loops.

        def _run_planner(algo_key: str, shared):
            """ACO / PSO only — always receives ga_instance as shared_setup."""
            label  = algo_key.upper()
            t0     = time.time()
            PClass = _get_planner_class(algo_key)
            try:
                # Skip traffic fetch + Dijkstra — reuse GA's pre-computed matrices
                instance = PClass(
                    at_risk_formatted, safe_shelters, sim.G,
                    pop_size=pop_sz, generations=gens,
                    n_ants=pop_sz, iterations=gens,
                    n_particles=pop_sz,
                    use_tomtom_traffic=False,   # traffic already on sim.G from GA init
                    shared_setup=shared,
                )
                plan     = instance.run()
                fitness  = round(getattr(instance, "best_fitness", 0.0), 1)
                elapsed  = round(time.time() - t0, 2)
                print(f"{_ts()}  [{label}] done: {len(plan)} routes | fitness={fitness} | {elapsed}s")
                return algo_key, plan, fitness, elapsed, instance
            except Exception as exc:
                import traceback
                print(f"{_ts()}  [{label}] EXCEPTION: {exc}")
                traceback.print_exc()
                return algo_key, [], 0.0, round(time.time() - t0, 2), None

        # GA runner: just call .run() on the already-initialised instance
        def _run_ga():
            label = "GA"
            t0    = time.time()
            try:
                plan    = ga_instance.run()
                fitness = round(getattr(ga_instance, "best_fitness", 0.0), 1)
                elapsed = round(time.time() - t0, 2)
                print(f"{_ts()}  [GA] evolution done: {len(plan)} routes | fitness={fitness} | {elapsed}s")
                return "ga", plan, fitness, elapsed, ga_instance
            except Exception as exc:
                import traceback
                print(f"{_ts()}  [GA] EXCEPTION: {exc}")
                traceback.print_exc()
                return "ga", [], 0.0, round(time.time() - t0, 2), None

        print(f"{_ts()}  [compare] Launching GA (evolution) + ACO + PSO in parallel threads")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(_run_ga),                            # GA — pre-inited, runs evolution
                pool.submit(_run_planner, "aco", ga_instance),  # ACO — reuses GA matrices
                pool.submit(_run_planner, "pso", ga_instance),  # PSO — reuses GA matrices
            ]
            planner_results = {}
            for fut in concurrent.futures.as_completed(futures):
                algo_key, plan, fitness, elapsed, instance = fut.result()
                planner_results[algo_key] = (plan, fitness, elapsed, instance)

        total_compare_time = round(time.time() - compare_start, 2)
        print(f"{_ts()}  [compare] All planners finished in {total_compare_time}s total")

        # ── Build per-algo result dicts (same shape as frontend expects) ──────
        for algo_key, (plan, fitness, elapsed, instance) in planner_results.items():
            # Compute occupancy independently per algo
            shelter_occ: dict = {}
            total_evac  = 0
            for move in plan:
                shelter_occ[move["to_shelter"]] = shelter_occ.get(move["to_shelter"], 0) + move["pop"]
                total_evac += move["pop"]

            at_risk_remaining = max(0, total_at_risk_initial - total_evac)

            shelter_reports = [
                {
                    "id":           s["id"],
                    "name":         s.get("name", s["id"]),
                    "type":         s.get("type", "unknown"),
                    "occupancy":     shelter_occ.get(s["id"], 0),
                    "capacity":      s["capacity"],
                    "safe":          s.get("safe", True),
                    "occupancy_pct": round(
                        min(shelter_occ.get(s["id"], 0) / max(s["capacity"], 1) * 100, 100), 1
                    ),
                }
                for s in shelters_with_safety
            ]

            traffic_geojson       = None
            traffic_segment_count = 0
            if use_traffic and instance is not None:
                try:
                    traffic_geojson       = instance.get_traffic_geojson()
                    traffic_segment_count = getattr(instance, "_traffic_segment_count", 0)
                except Exception:
                    pass

            # Shelter suggestions per algo (based on that algo's plan)
            algo_suggestions = []
            genuinely_unreachable = 0
            if at_risk_remaining > 0:
                algo_suggestions, genuinely_unreachable = _compute_shelter_suggestions(
                    at_risk_formatted, safe_shelters, sim.G, plan
                )
            
            pressure_points = []
            if instance is not None:
                try:
                    pressure_points = instance.calculate_pressure_points(plan)
                except Exception as e:
                    print(f"Error calculating pressure points: {e}")

            compare_results[algo_key] = {
                "evacuation_plan":       plan,
                "traffic_geojson":       traffic_geojson,
                "traffic_segment_count": traffic_segment_count,
                "summary": {
                    "total_evacuated":         total_evac,
                    "total_at_risk_remaining": at_risk_remaining,
                    "genuinely_unreachable":   genuinely_unreachable,
                    "total_at_risk_initial":   total_at_risk_initial,
                    "simulation_population":   total_pop,
                    "success_rate_pct":        round(total_evac / max(total_at_risk_initial, 1) * 100, 1),
                    "rainfall_mm":             rainfall_mm,
                    "algorithm":               algo_key.upper(),
                    "ga_execution_time":       elapsed,
                    "best_fitness":            fitness,
                    "avg_distance_per_person": round(fitness / max(total_at_risk_initial, 1), 1),
                    "shelter_reports":         shelter_reports,
                    "shelter_suggestions":     algo_suggestions,
                    "pressure_points":         pressure_points,
                    "metro_reports":           _collect_metro_reports(sim, metro_stations, center_lat, center_lon, update_history=True),
                    "metro_lines": entry.get("metro_lines", []),
                },
            }

    # ── Populate Cache for Analysis Mode ─────────────
    # Cache the complete flood setup: flooded graph, at_risk, safe_shelters,
    # shared Dijkstra instance, and the first-run results per algorithm.
    # Analysis mode reuses all of this so it never re-runs the flood simulation
    # or the expensive Dijkstra/traffic precompute.
    if at_risk and safe_shelters:
        COMPARE_ANALYSIS_CACHE.clear()
        COMPARE_ANALYSIS_CACHE["hobli"] = hobli
        COMPARE_ANALYSIS_CACHE["at_risk"] = at_risk_formatted
        COMPARE_ANALYSIS_CACHE["safe_shelters"] = safe_shelters
        COMPARE_ANALYSIS_CACHE["shared_instance"] = ga_instance
        # Snapshot the flooded graph (node water depths already propagated onto sim.G)
        COMPARE_ANALYSIS_CACHE["sim_G"] = sim.G
        COMPARE_ANALYSIS_CACHE["results"] = {}
        
        for algo_key, (plan, fitness, elapsed, instance) in planner_results.items():
            if instance:
                chromosome = _reconstruct_chromosome(plan, at_risk_formatted, safe_shelters)
                try:
                    breakdown = instance._fitness_breakdown(chromosome)
                except Exception as e:
                    print(f"{_ts()}  [compare] Breakdown failed for {algo_key}: {e}")
                    breakdown = {
                        "distance_score": 0, "time_score": 0,
                        "capacity_penalty": 0, "terrain_penalty": 0,
                        "unassigned_penalty": 0,
                        "total_fitness": fitness
                    }
                COMPARE_ANALYSIS_CACHE["results"][algo_key] = {
                    "fitness": fitness,
                    "history": getattr(instance, 'fitness_history', []),
                    "plan": plan,
                    "breakdown": breakdown
                }
        print(f"{_ts()}  [compare] COMPARE_ANALYSIS_CACHE populated: "
              f"hobli={hobli}, at_risk={len(at_risk_formatted)}, "
              f"safe_shelters={len(safe_shelters)}, algos={list(COMPARE_ANALYSIS_CACHE['results'].keys())}")

    # ── Phase 4: emit the single compare_done frame ──────────────────────────
    final_frame = {
        "compare_done": True,
        "total":        steps,
        "results":      compare_results,   # { "ga": {...}, "aco": {...}, "pso": {...} }
    }
    try:
        yield f"data: {json.dumps(final_frame)}\n\n"
    except (TypeError, ValueError):
        # Strip traffic geojson if serialisation fails
        for v in final_frame["results"].values():
            v["traffic_geojson"] = None
        yield f"data: {json.dumps(final_frame)}\n\n"

async def fetch_metro_stations(hobli_name: str) -> dict:
    """
    Return cached metro stations and lines for the given hobli.
    """
    # 1. Ensure region is loaded
    key = norm_key(hobli_name)
    if key not in REGION_CACHE:
        await process_load_region(hobli_name)
    
    # 2. Return cached metro network already loaded during /load-region click
    entry = REGION_CACHE.get(key, {})
    
    stations = entry.get("metro_stations", [])
    lines = entry.get("metro_lines", [])
    
    return {
        "hobli": hobli_name,
        "total": len(stations),
        "stations": stations,
        "lines": lines
    }

# ─────────────────────────────────────────────────────────────────────────────
# Advanced Algorithm Analysis (Convergence, Stability, Diversity)
# ─────────────────────────────────────────────────────────────────────────────

def _calculate_convergence_speed(history: list) -> float:
    """Find the iteration index where fitness first reaches 95% of its final improvement.
    
    Returns:
      - len(history) if no improvement occurred (algorithm never converged beyond seed)
      - iteration index (1-based) where 95% of improvement was achieved
      - len(history) if 95% threshold was never reached
    """
    if not history: return 1
    start_f = history[0]
    end_f = history[-1]
    total_gain = start_f - end_f
    if total_gain <= 0:
        # No improvement at all — the algorithm never converged beyond its
        # initial seed.  Return full iteration count (= "used all iterations
        # without improving"), NOT 1 which would misleadingly suggest
        # instant convergence.
        return len(history)
    
    target = start_f - (0.95 * total_gain)
    for i, f in enumerate(history):
        if f <= target:
            return i + 1
    return len(history)

def _calculate_path_diversity(plan: list) -> float:
    """Calculate the diversity of routes based on unique edge usage."""
    all_edges = []
    for route in plan:
        path = route.get("path_nodes", [])
        # Create a list of edges (pairs of adjacent nodes)
        edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
        all_edges.extend(edges)
    
    if not all_edges: return 1.0
    unique_edges = set(all_edges)
    # Diversity = Unique Edges / Total Edge Instances
    return round(len(unique_edges) / len(all_edges), 3)

async def run_advanced_analysis_generator(
    hobli: str, rainfall_mm: float, steps: int, decay_factor: float,
    population: int | None = None, use_traffic: bool = False,
    iterations_override: int | None = None,
):
    """
    Runs GA, ACO, and PSO 5 times each to calculate Stochastic Stability (Mean/StdDev).
    Also yields convergence and diversity metrics.

    Performance: Uses shared_setup pattern from compare mode so Dijkstra precompute
    and optional TomTom traffic only happen ONCE (via the first GA init), then all
    subsequent planner instances reuse those matrices.
    """
    import time
    import numpy as np
    import concurrent.futures
    loop = asyncio.get_event_loop()
    key = norm_key(hobli)
    
    # ── Hook into the global COMPARE_ANALYSIS_CACHE ──
    use_cache = False
    if COMPARE_ANALYSIS_CACHE.get("hobli") == hobli and COMPARE_ANALYSIS_CACHE.get("shared_instance") is not None:
        use_cache = True

    if use_cache:
        at_risk = COMPARE_ANALYSIS_CACHE["at_risk"]
        safe_shelters = COMPARE_ANALYSIS_CACHE["safe_shelters"]
        shared_instance = COMPARE_ANALYSIS_CACHE["shared_instance"]
        # Use the cached flooded graph (water depths already propagated by compare mode)
        sim_G = COMPARE_ANALYSIS_CACHE.get("sim_G", shared_instance.G)
        n_risk = len(at_risk)
        pop_sz = shared_instance.pop_size

        if iterations_override and iterations_override > 0:
            gens = iterations_override
        else:
            gens = shared_instance.generations

        print(f"{_ts()} [Analysis] Using cached flood state and Dijkstra setup from Compare mode.")
        yield f"data: {json.dumps({'analysis_progress': True, 'message': f'Using cached flood setup ({n_risk} at-risk nodes)...', 'step': 0, 'total': 3})}\n\n"
    else:
        # 1. Setup Simulation (same as compare mode)
        if key not in REGION_CACHE:
            try:
                await loop.run_in_executor(None, get_region, key)
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Region not loaded: {e}'})}\n\n"
                return

        entry = REGION_CACHE[key]
        sim = UrbanFloodSimulator(entry["G"].copy(), entry["drain_nodes"], entry["lake_nodes"])
        sim.initialize_from_drains(rainfall_mm)
        sim_G = sim.G
        
        if population is not None: 
            total_pop = population
        else: 
            pop_data = await get_hobli_population(hobli)
            total_pop = pop_data.get("total_population", 0)
        
        # Use full population to introduce realistic capacity stress
        sim.distribute_population(total_pop)
        
        shelter_resp = await fetch_shelters(hobli)
        safe_shelters = [s for s in shelter_resp["shelters"]] # Assume safe for analysis
        
        # Use fewer steps for analysis (progressive but faster) — half user steps, min 5
        analysis_steps = max(5, steps // 2)
        yield f"data: {json.dumps({'analysis_progress': True, 'message': f'Simulating flood ({analysis_steps} progressive steps)...', 'step': 0, 'total': 3})}\n\n"

        def _run_flood():
            for _ in range(analysis_steps):
                sim.propagate_flood_step(decay_factor)
        await loop.run_in_executor(None, _run_flood)
        
        at_risk_raw = sim.get_at_risk_nodes(depth_threshold_m=0.05)
        at_risk = [{"id": n, "pop": p, "lat": sim.G.nodes[n]["y"], "lon": sim.G.nodes[n]["x"]} for n, p in at_risk_raw]

        if not at_risk or not safe_shelters:
            yield f"data: {json.dumps({'error': 'No at-risk population or shelters'})}\n\n"
            return

        # ── Shared setup: initialise one GA instance for Dijkstra + optional TomTom ──
        # All 15 subsequent runs reuse this instance's precomputed matrices.
        n_risk = len(at_risk)
        if iterations_override and iterations_override > 0:
            gens = iterations_override  # Deep analysis: user-requested iteration count
        else:
            gens = max(30, min(60, 3000 // max(n_risk, 1)))   # adaptive iteration count
        pop_sz = min(60, max(30, n_risk * 2))
        print(f"{_ts()} [Analysis] Params: pop_sz={pop_sz}, gens={gens}, at_risk={n_risk}, override={'Yes' if iterations_override else 'No'}")

        yield f"data: {json.dumps({'analysis_progress': True, 'message': f'Building road network ({n_risk} at-risk nodes)...', 'step': 0, 'total': 3})}\n\n"

        def _init_shared():
            PClass = _get_planner_class("ga")
            return PClass(
                at_risk, safe_shelters, sim.G,
                pop_size=pop_sz, generations=gens,
                use_tomtom_traffic=use_traffic,
                shared_setup=None,
            )

        shared_instance = await loop.run_in_executor(None, _init_shared)
        print(f"{_ts()} [Analysis] Shared Dijkstra setup complete")

    # 2. Stability Runs (3 runs per algorithm — fast but statistically sufficient)
    n_runs = 3
    results = {"ga": [], "aco": [], "pso": []}
    
    def _single_run(algo_key, shared, run_idx):
        """
        Run one algorithm instance with ±5% noise on the distance matrix.
        
        Each run_idx produces a unique perturbation of the shared Dijkstra 
        distances, simulating real-world uncertainty in flood depth measurements.
        This forces each run to explore a different region of the solution space,
        producing meaningful variance across the 5 stability runs.
        
        IMPORTANT: After the run, fitness and breakdown are re-evaluated on the
        ORIGINAL (un-perturbed) matrices so that reported values are comparable
        across runs and don't inflate with higher iteration counts.
        """
        PClass = _get_planner_class(algo_key)
        planner = PClass(at_risk, safe_shelters, sim_G,
                        pop_size=pop_sz, generations=gens,
                        n_ants=pop_sz, iterations=gens,
                        n_particles=pop_sz,
                        use_tomtom_traffic=False,
                        shared_setup=shared)

        # ── Save original matrices BEFORE perturbation ────────────────────
        original_dist = planner.dist_matrix.copy()
        original_time = planner.time_matrix.copy()

        # ── Add ±5% Gaussian noise to distance matrix ────────────────────
        # Each (algo, run_idx) pair gets a unique seed for reproducibility.
        rng = np.random.RandomState(seed=hash((algo_key, run_idx)) % (2**31))
        noise = rng.normal(loc=1.0, scale=0.05, size=planner.dist_matrix.shape)
        noise = np.clip(noise, 0.90, 1.10)  # cap at ±10% to avoid extremes
        planner.dist_matrix = planner.dist_matrix * noise
        # Time matrix gets correlated but not identical noise
        time_noise = rng.normal(loc=1.0, scale=0.03, size=planner.time_matrix.shape)
        time_noise = np.clip(time_noise, 0.93, 1.07)
        planner.time_matrix = planner.time_matrix * time_noise
        # Recompute the greedy chromosome from the perturbed distances
        planner._greedy_chromosome = planner._compute_greedy_chromosome()
        # ─────────────────────────────────────────────────────────────────

        decoded_plan = planner.run()

        # ── Reconstruct assignment chromosome from the plan ──
        n_r = len(at_risk)
        chromosome = [-1] * n_r   # -1 = unassigned
        for move in decoded_plan:
            origin_id = move.get("from_node")
            # find index of origin node in at_risk list
            for idx, node in enumerate(at_risk):
                if node["id"] == origin_id:
                    # find shelter index in safe_shelters list
                    shelter_id = move.get("to_shelter")
                    for j, sh in enumerate(safe_shelters):
                        if sh["id"] == shelter_id:
                            chromosome[idx] = j
                            break
                    break

        # ── Re-evaluate fitness & breakdown on ORIGINAL matrices ─────────
        # The planner's best_fitness was computed against perturbed distances,
        # which inflates the reported value (especially with many iterations).
        # Restore original matrices so the score is fair and comparable.
        planner.dist_matrix = original_dist
        planner.time_matrix = original_time

        fair_fitness = planner._fitness(chromosome)

        try:
            breakdown = planner._fitness_breakdown(chromosome)
        except Exception as e:
            print(f"  [Analysis] Breakdown failed for {algo_key}: {e}")
            breakdown = {
                "distance_score": 0, "time_score": 0,
                "capacity_penalty": 0, "terrain_penalty": 0,
                "unassigned_penalty": 0,
                "total_fitness": fair_fitness
            }

        return algo_key, fair_fitness, planner.fitness_history, decoded_plan, breakdown

    print(f"{_ts()} [Analysis] Starting stability test ({n_runs} runs × 3 algorithms, gens={gens}, noise=±5%)...")
    analysis_data = {}

    # ── Progressive streaming: run each algorithm's runs sequentially in
    #    a background thread, yield results as each algorithm completes ──
    algo_order = ["ga", "aco", "pso"]
    algo_labels = {"ga": "Genetic Algorithm", "aco": "Ant Colony Opt.", "pso": "Particle Swarm"}

    for algo_idx, algo in enumerate(algo_order):
        # Progress: starting this algorithm
        yield f"data: {json.dumps({'analysis_progress': True, 'message': f'Running {algo_labels[algo]} ({algo_idx+1}/3)...', 'algo': algo, 'step': algo_idx+1, 'total': 3})}\n\n"

        # Run remaining iterations concurrently to save massive time
        def _run_algo_batch(algo_key):
            batch = []
            runs_to_do = []
            if use_cache and algo_key in COMPARE_ANALYSIS_CACHE.get("results", {}):
                cached = COMPARE_ANALYSIS_CACHE["results"][algo_key]
                batch.append(cached)
                runs_to_do = list(range(1, n_runs))
            else:
                runs_to_do = list(range(n_runs))
                
            if not runs_to_do:
                return batch
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(runs_to_do)) as pool:
                futs = [pool.submit(_single_run, algo_key, shared_instance, ri) for ri in runs_to_do]
                for fut in concurrent.futures.as_completed(futs):
                    _, fitness, history, plan, breakdown = fut.result()
                    batch.append({"fitness": fitness, "history": history, "plan": plan, "breakdown": breakdown})
            return batch

        algo_results = await loop.run_in_executor(None, _run_algo_batch, algo)
        results[algo] = algo_results

        # Aggregate metrics for this algorithm immediately
        fitnesses = [r["fitness"] for r in algo_results]
        histories = [r["history"] for r in algo_results]
        plans = [r["plan"] for r in algo_results]

        mean_fit = np.mean(fitnesses)
        std_fit = np.std(fitnesses)
        stability = max(0, 1.0 - (std_fit / mean_fit)) if mean_fit > 0 else 0
        avg_conv = np.mean([_calculate_convergence_speed(h) for h in histories])
        avg_div = np.mean([_calculate_path_diversity(p) for p in plans])

        min_len = min(len(h) for h in histories) if histories else 0
        if min_len > 0:
            trimmed = [h[:min_len] for h in histories]
            avg_history = np.mean(trimmed, axis=0).tolist()
        else:
            avg_history = histories[0] if histories else []

        analysis_data[algo] = {
            "mean_fitness": round(float(mean_fit), 1),
            "std_dev": round(float(std_fit), 2),
            "stability_score": round(float(stability), 3),
            "convergence_speed": round(float(avg_conv), 1),
            "path_diversity": round(float(avg_div), 3),
            "fitness_history": avg_history,
            "breakdown": algo_results[0]["breakdown"]
        }

        # Stream this algorithm's result immediately so the UI can render it
        yield f"data: {json.dumps({'algo_result': True, 'algo': algo, 'metrics': {algo: analysis_data[algo]}})}\n\n"
        print(f"{_ts()}   [{algo.upper()}] done: Mean={analysis_data[algo]['mean_fitness']}, "
              f"Stability={analysis_data[algo]['stability_score']}, Conv={analysis_data[algo]['convergence_speed']}")

    # Final payload with all metrics
    final_payload = {
        "analysis_done": True,
        "metrics": analysis_data,
        "location": hobli,
        "timestamp": datetime.now().isoformat()
    }
    
    print(f"\n{_ts()} [ANALYSIS COMPLETE] Location: {hobli}")
    for algo, data in analysis_data.items():
        print(f"  - {algo.upper()}: Mean Fit={data['mean_fitness']}, StdDev={data['std_dev']}, "
              f"Stability={data['stability_score']}, Conv={data['convergence_speed']}, "
              f"Diversity={data['path_diversity']}")
    
    yield f"data: {json.dumps(final_payload)}\n\n"


async def run_scenario_analysis_generator(
    hobli: str, steps: int, decay_factor: float,
    population: int | None = None, use_traffic: bool = False,
):
    """
    Runs GA, ACO, and PSO across three flood scenarios (Low, Medium, High).
    Evaluates routing efficiency, success rate, and pressure points for each scenario.
    """
    import time
    import concurrent.futures
    loop = asyncio.get_event_loop()
    key = norm_key(hobli)

    if key not in REGION_CACHE:
        try:
            await loop.run_in_executor(None, get_region, key)
        except Exception as e:
            yield f"data: {json.dumps({'error': f'Region not loaded: {e}'})}\n\n"
            return

    entry = REGION_CACHE[key]
    
    if population is not None: 
        total_pop = population
    else: 
        pop_data = await get_hobli_population(hobli)
        total_pop = pop_data.get("total_population", 0)
        
    shelter_resp = await fetch_shelters(hobli)
    all_shelters = [s for s in shelter_resp["shelters"]]
    
    scenarios = [
        {"name": "low", "label": "Low (50mm)", "rainfall_mm": 50.0},
        {"name": "medium", "label": "Medium (150mm)", "rainfall_mm": 150.0},
        {"name": "high", "label": "High (250mm)", "rainfall_mm": 250.0}
    ]
    
    analysis_data = {
        "low": {},
        "medium": {},
        "high": {}
    }
    
    # We do NOT use COMPARE_ANALYSIS_CACHE because the flood setup is different for each scenario.
    
    # Send initial progress
    payload_start = {
        'analysis_progress': True, 
        'message': 'Starting scenario analysis across 3 flood levels...', 
        'step': 0, 
        'total': 3
    }
    yield f"data: {json.dumps(payload_start)}\n\n"
    
    for s_idx, scenario in enumerate(scenarios):
        payload_scenario = {
            'analysis_progress': True, 
            'message': f"Running {scenario['label']} Scenario...", 
            'scenario': scenario['name'], 
            'step': s_idx + 1, 
            'total': 3
        }
        yield f"data: {json.dumps(payload_scenario)}\n\n"
        
        sim = UrbanFloodSimulator(entry["G"].copy(), entry["drain_nodes"], entry["lake_nodes"])
        # The user requested to use progressive flood mode itself
        sim.set_progressive_rainfall(scenario["rainfall_mm"], steps)
        sim_G = sim.G
        sim.distribute_population(total_pop)
        
        # User requested progressive flood mode: run the full steps loop
        def _run_flood():
            for _ in range(steps):
                sim.propagate_flood_step(decay_factor)
        await loop.run_in_executor(None, _run_flood)
        
        at_risk_raw = sim.get_at_risk_nodes(depth_threshold_m=0.05)
        at_risk = [{"id": n, "pop": p, "lat": sim.G.nodes[n]["y"], "lon": sim.G.nodes[n]["x"]} for n, p in at_risk_raw]
        
        if not at_risk or not all_shelters:
            print(f"[{scenario['name']}] Skipping due to no at_risk or shelters")
            for algo in ["ga", "aco", "pso"]:
                analysis_data[scenario["name"]][algo] = None
            continue
            
        n_risk = len(at_risk)
        gens = max(20, min(50, 2000 // max(n_risk, 1)))
        pop_sz = min(50, max(20, n_risk * 2))
        
        def _init_shared():
            PClass = _get_planner_class("ga")
            return PClass(
                at_risk, all_shelters, sim.G,
                pop_size=pop_sz, generations=gens,
                use_tomtom_traffic=use_traffic,
                shared_setup=None,
            )

        shared_instance = await loop.run_in_executor(None, _init_shared)
        
        def _single_algo_run(algo_key):
            t0 = time.time()
            PClass = _get_planner_class(algo_key)
            planner = PClass(at_risk, all_shelters, sim_G,
                            pop_size=pop_sz, generations=gens,
                            n_ants=pop_sz, iterations=gens,
                            n_particles=pop_sz,
                            use_tomtom_traffic=False,
                            shared_setup=shared_instance)
            decoded_plan = planner.run()
            elapsed = round(time.time() - t0, 2)
            
            # Reconstruct assignment chromosome
            n_r = len(at_risk)
            chromosome = [-1] * n_r
            for move in decoded_plan:
                origin_id = move.get("from_node")
                for idx, node in enumerate(at_risk):
                    if node["id"] == origin_id:
                        shelter_id = move.get("to_shelter")
                        for j, sh in enumerate(all_shelters):
                            if sh["id"] == shelter_id:
                                chromosome[idx] = j
                                break
                        break
                        
            fair_fitness = planner._fitness(chromosome)
            try:
                breakdown = planner._fitness_breakdown(chromosome)
            except:
                breakdown = {"total_fitness": fair_fitness}
                
            total_evacuated = sum(move["pop"] for move in decoded_plan)
            # Use sum of population of at_risk nodes to calculate success rate accurately relative to the group needing evacuation.
            total_at_risk_pop = sum(n["pop"] for n in at_risk)
            success_rate = round(total_evacuated / max(total_at_risk_pop, 1) * 100, 1)
            
            pressure_points_count = 0
            total_bottleneck_load = 0
            if hasattr(planner, "calculate_pressure_points"):
                try:
                    # Use top_n=9999 to get ALL pressure points, not just top 5
                    all_pp = planner.calculate_pressure_points(decoded_plan, top_n=9999)
                    pressure_points_count = len(all_pp)
                    total_bottleneck_load = sum(p["total_evacuees"] for p in all_pp)
                except:
                    pass

            return {
                "algorithm": algo_key,
                "fitness": round(fair_fitness, 1),
                "execution_time": elapsed,
                "total_evacuated": total_evacuated,
                "total_at_risk_pop": total_at_risk_pop,
                "success_rate_pct": success_rate,
                "pressure_points_count": pressure_points_count,
                "total_bottleneck_load": total_bottleneck_load,
                "breakdown": breakdown
            }
        
        # Run algos concurrently for this scenario
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(_single_algo_run, algo) for algo in ["ga", "aco", "pso"]]
            for fut in concurrent.futures.as_completed(futs):
                res = fut.result()
                analysis_data[scenario["name"]][res["algorithm"]] = res
                
        # Emit partial scenario result
        payload_result = {
            'scenario_result': True, 
            'scenario': scenario['name'], 
            'metrics': analysis_data[scenario['name']]
        }
        yield f"data: {json.dumps(payload_result)}\n\n"
        
    # Rank summation to find best overall algorithm
    # We want MIN fitness, MIN execution_time, MAX success_rate_pct, MIN total_bottleneck_load
    total_ranks = {"ga": 0, "aco": 0, "pso": 0}
    valid_algos = ["ga", "aco", "pso"]
    
    for scenario_name, algos in analysis_data.items():
        if not all(algos.get(a) for a in valid_algos):
            continue
            
        fitness_ranked = sorted(valid_algos, key=lambda a: algos[a]["fitness"])
        time_ranked = sorted(valid_algos, key=lambda a: algos[a]["execution_time"])
        success_ranked = sorted(valid_algos, key=lambda a: algos[a]["success_rate_pct"], reverse=True)
        pressure_ranked = sorted(valid_algos, key=lambda a: algos[a]["total_bottleneck_load"])
        
        for a in valid_algos:
            rank_score = (fitness_ranked.index(a) * 3) + (time_ranked.index(a) * 1) + (success_ranked.index(a) * 2) + (pressure_ranked.index(a) * 1)
            total_ranks[a] += rank_score
            
    best_overall = min(total_ranks.keys(), key=lambda k: total_ranks[k]) if any(total_ranks.values()) else "N/A"

    final_payload = {
        "scenario_analysis_done": True,
        "metrics": analysis_data,
        "location": hobli,
        "best_overall_algorithm": best_overall,
        "algorithm_scores": total_ranks,
        "timestamp": datetime.now().isoformat()
    }
    
    yield f"data: {json.dumps(final_payload)}\n\n"