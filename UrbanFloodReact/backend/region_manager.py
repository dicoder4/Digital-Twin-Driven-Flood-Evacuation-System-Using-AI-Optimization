"""
region_manager.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Owns all mutable server state:
  - HOBLI_COORDS  : norm_key â†’ coord metadata
  - RAINFALL_DATA : norm_key â†’ list of rainfall records
  - REGION_CACHE  : norm_key â†’ {G, drain_nodes, lake_nodes}
  - REGIONS_TREE  : district â†’ taluk â†’ [hobli display names]

Provides:
  - initialise(data_dir) â€” called once in lifespan
  - get_region(hobli_key) â€” returns cached or downloads graph
  - norm_key()            â€” re-exported for endpoints
"""

from pathlib import Path
import pickle
import osmnx as ox
from shapely.geometry import Point, LineString, box, shape, mapping
from shapely.ops import unary_union

from coord_loader   import load_coords_from_json, norm_key  # noqa: F401 (re-export norm_key)
from rainfall_loader import load_rainfall_excels

# â”€â”€ Module-level state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
HOBLI_COORDS:  dict = {}
RAINFALL_DATA: dict = {}
REGION_CACHE:  dict = {}
REGIONS_TREE:  dict = {}

DATA_DIR  = Path(__file__).parent / "data"
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

URBAN_JSON = DATA_DIR / "hobli_coordinates_urban.json"
RURAL_JSON = DATA_DIR / "hobli_coordinates_rural.json"
METRO_KML = DATA_DIR / "bengaluru_rail_metro_lines.kml"
METRO_GEOJSON = DATA_DIR / "NammaMetro" / "metro-lines-stations.geojson"
METRO_QUERY_RADIUS_M = 5000


# â”€â”€ Initialise (called once at startup) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def initialise():
    """Load all coordinate maps and rainfall data, then build region tree."""
    print("Loading hobli coordinate map ")
    urban = load_coords_from_json(URBAN_JSON, "BENGALURU URBAN")
    rural = load_coords_from_json(RURAL_JSON, "BENGALURU RURAL")
    HOBLI_COORDS.update(urban)
    HOBLI_COORDS.update(rural)
    print(f"  {len(HOBLI_COORDS)} unique hoblis ({len(urban)} urban, {len(rural)} rural)")

    print("Loading rainfall data")
    load_rainfall_excels(DATA_DIR, norm_key, RAINFALL_DATA)

    print("Building regions tree")
    _build_regions_tree()


def _build_regions_tree():
    tree: dict[str, dict[str, list]] = {}

    for key, entries in RAINFALL_DATA.items():
        if not entries:
            continue
        # Skip hoblis that have no coordinate entry â€” they can't be loaded
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


# â”€â”€ Graph loader (lazy + disk-cached) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    center = (lat, lon)
    safe_key  = hobli_key.replace("/", "_").replace(" ", "_")
    graph_f   = CACHE_DIR / f"{safe_key}_graph.graphml"
    feat_f    = CACHE_DIR / f"{safe_key}_features.pkl"

    # 1. Graph
    if graph_f.exists():
        print(f"  [cache] Loading graph: {graph_f.name}")
        G = ox.load_graphml(str(graph_f))
    else:
        print(f"  [osmnx] Downloading graph for {coords['original_name']}")
        G = ox.graph_from_point((lat, lon), dist=2000, dist_type="bbox", network_type="drive")
        ox.save_graphml(G, str(graph_f))
        print(f"  [osmnx] Saved -> {graph_f.name}")

    # 2. Drains & lakes data (essential for physics)
    drain_nodes, lake_nodes = [], []
    metro_stations, metro_lines = [], []
    needs_update = False
    
    if feat_f.exists():
        print(f"  [cache] Loading features: {feat_f.name}")
        with open(feat_f, "rb") as f:
            saved = pickle.load(f)
            drain_nodes = saved.get("drains", [])
            lake_nodes  = saved.get("lakes", [])
            metro_stations = saved.get("metro", [])
            metro_lines = saved.get("metro_lines", [])
            #metro_lines = _load_metro_lines_from_geojson(center)
            
            # Handle metro_lines format - ensure it's a FeatureCollection
            if isinstance(metro_lines, dict) and metro_lines.get("type") == "FeatureCollection":
                pass  # Already a FeatureCollection
            elif isinstance(metro_lines, list):
                # Convert array to FeatureCollection
                metro_lines = {
                    "type": "FeatureCollection",
                    "features": metro_lines
                }
            
            # Sanitize cached data (in case it contains NaNs from previous versions)
            for m in metro_stations:
                if isinstance(m, dict):
                    m['name'] = _sanitize_val(m.get('name'))
                    m['line'] = _sanitize_val(m.get('line'))
                    m['colour'] = _sanitize_val(m.get('colour'))
            
            # Sanitize metro lines features
            if isinstance(metro_lines, dict) and metro_lines.get("type") == "FeatureCollection":
                for line in metro_lines.get("features", []):
                    if isinstance(line, dict) and 'properties' in line:
                        p = line['properties']
                        p['name'] = _sanitize_val(p.get('name'))
                        p['line'] = _sanitize_val(p.get('line'))
                        p['colour'] = _sanitize_val(p.get('colour'))
    else:
        try:
            from gis_terrain_loader import get_gis_hydrology_nodes
            drain_nodes, lake_nodes = get_gis_hydrology_nodes(G, lat, lon)
        except Exception as e:
            print(f"  [gis/warning] GIS hydrology failed: {e}. Falling back to standard OSM extraction.")
            center = (lat, lon)
            drain_nodes = _extract_drains(G, center)
            lake_nodes  = _extract_lakes(G, center)
        needs_update = True

    if needs_update:
        with open(feat_f, "wb") as f:
            pickle.dump({
                "drains": drain_nodes, 
                "lakes": lake_nodes,
                "metro": metro_stations,
                "metro_lines": metro_lines
            }, f)
        print(f"  [cache] Features saved -> {feat_f.name}")
        
    try:
        from gis_terrain_loader import enrich_graph_elevation, enrich_graph_roughness
        # This will download the SRTM DEM for the graph bounds and apply elevation to all nodes
        G = enrich_graph_elevation(G, lat, lon)
        # Apply Manning's roughness coefficient to edges based on highway tags
        G = enrich_graph_roughness(G)
    except Exception as e:
        print(f"  [gis/warning] Graph enrichment skipped: {e}")

    entry = {
        "G": G, 
        "drain_nodes": drain_nodes, 
        "lake_nodes": lake_nodes, 
        "metro_stations": metro_stations,
        "metro_lines": metro_lines
    }
    REGION_CACHE[hobli_key] = entry
    return entry


def extract_metro_data(hobli_key: str, include_rail: bool = False) -> dict:
    if hobli_key not in REGION_CACHE:
        raise ValueError(f"Region '{hobli_key}' must be loaded before extracting metro data.")
    
    entry = REGION_CACHE[hobli_key]
    coords = HOBLI_COORDS.get(hobli_key)
    lat, lon = coords["lat"], coords["lon"]
    center = (lat, lon)
    G = entry["G"]

    print(f"  [on-demand] Extracting Metro Network for {hobli_key} (Radius: 4,000m, include_rail={include_rail}) …")

    # 1. Extract stations (unchanged)
    metro_stations = _extract_metro_stations(G, center, include_rail=include_rail)

    # 2. Use authoritative GeoJSON for lines – this replaces all OSM line extraction and merging
    metro_lines = _load_metro_lines_from_geojson(center)

    # 3. Still enrich stations with line information (optional, but keeps station display accurate)
    #    We need a reference for station enrichment. Use the GeoJSON lines as the reference.
    if metro_lines.get("features"):
        print(f"  [metro] Using GeoJSON lines for station enrichment ({len(metro_lines['features'])} features)")
        # For compatibility, we can reuse the existing enrichment functions; they accept FeatureCollection.
        metro_stations = _enrich_station_lines_from_network(metro_stations, metro_lines)

    # Optional: Also apply CSV reference if you want (keep it for station line corrections)
    csv_label_reference, csv_station_line_map = _extract_namma_metro_reference_from_csv()
    metro_stations = _enrich_station_lines_from_dataset(metro_stations, csv_station_line_map)

    # Update memory cache
    entry["metro_stations"] = metro_stations
    entry["metro_lines"] = metro_lines

    # Update disk cache
    safe_key = hobli_key.replace("/", "_").replace(" ", "_")
    feat_f = CACHE_DIR / f"{safe_key}_features.pkl"
    
    # Ensure metro_lines is a FeatureCollection before storing
    metro_lines_to_store = metro_lines
    if isinstance(metro_lines, dict) and metro_lines.get("type") == "FeatureCollection":
        line_count = len(metro_lines.get("features", []))
    elif isinstance(metro_lines, list):
        line_count = len(metro_lines)
        metro_lines_to_store = {
            "type": "FeatureCollection",
            "features": metro_lines
        }
    else:
        line_count = 0
        metro_lines_to_store = {"type": "FeatureCollection", "features": []}
    
    print(f"  [on-demand] Storing {len(metro_stations)} stations and {line_count} line segments")

    with open(feat_f, "wb") as f:
        pickle.dump({
            "drains": entry.get("drain_nodes", []),
            "lakes": entry.get("lake_nodes", []),
            "metro": metro_stations,
            "metro_lines": metro_lines_to_store
        }, f)
    print(f"  [on-demand] Features updated on disk -> {feat_f.name}")

    return entry

# def extract_metro_data(hobli_key: str, include_rail: bool = False) -> dict:
#     """
#     On-demand heavy OSMnx extraction for metro stations and lines.
#     Updates the regional cache and persistent disk feature file.
#     """
#     if hobli_key not in REGION_CACHE:
#         raise ValueError(f"Region '{hobli_key}' must be loaded before extracting metro data.")
    
#     entry = REGION_CACHE[hobli_key]
    
#     # We now skip the early return to ensure the new "Smart Sniffer" 
#     # can repair existing cache files that have missing line/color info.

#     coords = HOBLI_COORDS.get(hobli_key)
#     lat, lon = coords["lat"], coords["lon"]
#     center = (lat, lon)
#     G = entry["G"]

#     print(f"  [on-demand] Extracting Metro Network for {hobli_key} (Radius: 4,000m, include_rail={include_rail}) …")
#     metro_stations = _extract_metro_stations(G, center, include_rail=include_rail)

#     csv_label_reference, csv_station_line_map = _extract_namma_metro_reference_from_csv()
#     kml_label_reference = _extract_metro_lines_from_kml(center, include_rail=include_rail)

#     # MERGE CSV (metro lines) + KML (metro + railway lines) for comprehensive coverage
#     label_reference_features = []
    
#     if isinstance(csv_label_reference, dict) and csv_label_reference.get("features"):
#         label_reference_features.extend(csv_label_reference.get("features", []))
#         print(f"  [metro] Added {len(csv_label_reference.get('features', []))} CSV metro features")
    
#     if isinstance(kml_label_reference, dict) and kml_label_reference.get("features"):
#         kml_features = kml_label_reference.get("features", [])
#         label_reference_features.extend(kml_features)
#         print(f"  [metro] Added {len(kml_features)} KML features")
#     elif isinstance(kml_label_reference, list) and len(kml_label_reference) > 0:
#         label_reference_features.extend(kml_label_reference)
#         print(f"  [metro] Added {len(kml_label_reference)} KML features (as list)")
    
#     label_reference = {
#         "type": "FeatureCollection",
#         "features": label_reference_features
#     }
#     print(f"  [metro] Total label reference features: {len(label_reference_features)}")

#     metro_lines = _extract_metro_lines(center, include_rail=include_rail, label_reference_lines=label_reference)
#     metro_lines = _merge_full_line_reference_segments(metro_lines, label_reference)
    
#     # Log what we have after merge
#     if isinstance(metro_lines, dict) and metro_lines.get("features"):
#         total_features = len(metro_lines.get("features", []))
#         metro_count_lines = sum(1 for f in metro_lines.get("features", []) if f.get("properties", {}).get("transport_type") == "metro")
#         railway_count_lines = sum(1 for f in metro_lines.get("features", []) if f.get("properties", {}).get("transport_type") == "railway")
#         print(f"  [metro] After merge: {total_features} total features ({metro_count_lines} metro, {railway_count_lines} railway)")
    
#     label_source = label_reference if isinstance(label_reference, dict) and label_reference.get("features") else metro_lines
#     print(f"  [metro] Enriching {len(metro_stations)} stations with line data from {type(label_source)} source")
#     metro_stations = _enrich_station_lines_from_network(metro_stations, label_source)
#     metro_stations = _enrich_station_lines_from_dataset(metro_stations, csv_station_line_map)
    
#     # Log enrichment results
#     metro_count = sum(1 for s in metro_stations if s.get("transport_type") == "metro")
#     railway_count = sum(1 for s in metro_stations if s.get("transport_type") == "railway")
#     print(f"  [on-demand] Station enrichment complete: {metro_count} metro, {railway_count} railway stations")
    
#     # Update memory cache
#     entry["metro_stations"] = metro_stations
#     entry["metro_lines"] = metro_lines

#     # Update disk cache
#     safe_key = hobli_key.replace("/", "_").replace(" ", "_")
#     feat_f = CACHE_DIR / f"{safe_key}_features.pkl"
    
#     # Ensure metro_lines is a FeatureCollection before storing
#     metro_lines_to_store = metro_lines
#     if isinstance(metro_lines, dict) and metro_lines.get("type") == "FeatureCollection":
#         line_count = len(metro_lines.get("features", []))
#     elif isinstance(metro_lines, list):
#         line_count = len(metro_lines)
#         metro_lines_to_store = {
#             "type": "FeatureCollection",
#             "features": metro_lines
#         }
#     else:
#         line_count = 0
#         metro_lines_to_store = {"type": "FeatureCollection", "features": []}
    
#     print(f"  [on-demand] Storing {len(metro_stations)} stations and {line_count} line segments")
    
#     with open(feat_f, "wb") as f:
#         pickle.dump({
#             "drains": entry.get("drain_nodes", []),
#             "lakes": entry.get("lake_nodes", []),
#             "metro": metro_stations,
#             "metro_lines": metro_lines_to_store
#         }, f)
#     print(f"  [on-demand] Features updated on disk -> {feat_f.name}")
    
#     return entry


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

def _sanitize_val(v):
    """Convert pandas/numpy NaN to None for JSON compliance."""
    import pandas as pd
    if pd.isna(v):
        return None
    return v


def _looks_non_operational(text: str) -> bool:
    txt = _text(text)
    blocked_tokens = [
        "under construction", "construction", "u/c", "proposed",
        "corridor package",
    ]
    return any(t in txt for t in blocked_tokens)


def _looks_project_label(text: str) -> bool:
    txt = _text(text)
    if not txt:
        return False
    return ("phase" in txt or "reach" in txt) and ("line" not in txt)


def _text(v) -> str:
    return str(v).lower().strip() if v is not None else ""


def _station_key(name: str) -> str:
    s = _text(name)
    return "".join(ch for ch in s if ch.isalnum())


def _hex_to_colour_token(hex_value: str) -> str:
    value = _text(hex_value).replace("#", "")
    if value in {"7e22ce", "8b5cf6"}:
        return "purple"
    if value in {"16a34a", "059669", "22c55e"}:
        return "green"
    if value in {"ca8a04", "eab308", "f59e0b"}:
        return "yellow"
    if value in {"2563eb", "3b82f6"}:
        return "blue"
    if value in {"db2777", "ec4899"}:
        return "pink"
    return None


def _extract_namma_metro_reference_from_csv():
    """
    Build full-line reference geometry + station->line lookup from
    `data/NammaMetro/*.csv`.
    """
    import csv

    namma_dir = DATA_DIR / "NammaMetro"
    network_csv = namma_dir / "bengaluru_metro_network.csv"
    stations_csv = namma_dir / "bengaluru_metro_stations.csv"

    if not network_csv.exists() or not stations_csv.exists():
        return {"type": "FeatureCollection", "features": []}, {}

    try:
        with open(network_csv, newline="", encoding="utf-8") as f:
            network_rows = list(csv.DictReader(f))

        with open(stations_csv, newline="", encoding="utf-8") as f:
            station_rows = list(csv.DictReader(f))

        station_line_map = {}
        for row in station_rows:
            station_name = _sanitize_val(row.get("station_name"))
            line_name = _sanitize_val(row.get("line"))
            if not station_name or not line_name:
                continue
            if "red" in _text(line_name):
                continue
            
            key = _station_key(station_name)
            if key in station_line_map:
                # Add if not already present in the semicolon-separated list
                if line_name not in station_line_map[key]:
                    station_line_map[key] = f"{station_line_map[key]}; {line_name}"
            else:
                station_line_map[key] = line_name

        indexed = {}
        for row in network_rows:
            line_name = _sanitize_val(row.get("line"))
            station_code = _sanitize_val(row.get("station_code"))
            if not line_name or not station_code:
                continue
            if "red" in _text(line_name):
                continue
            indexed[(_text(line_name), str(station_code).strip().upper())] = row

            station_name = _sanitize_val(row.get("station_name"))
            if station_name:
                key = _station_key(station_name)
                if key in station_line_map:
                    if line_name not in station_line_map[key]:
                        station_line_map[key] = f"{station_line_map[key]}; {line_name}"
                else:
                    station_line_map[key] = line_name

        features = []
        for row in network_rows:
            line_name = _sanitize_val(row.get("line"))
            station_code = _sanitize_val(row.get("station_code"))
            next_station_code = _sanitize_val(row.get("next_station_code"))

            if not line_name or not station_code or not next_station_code:
                continue
            if str(next_station_code).strip().upper() in {"NULL", "NONE", "NAN", ""}:
                continue
            if "red" in _text(line_name):
                continue

            key = (_text(line_name), str(next_station_code).strip().upper())
            next_row = indexed.get(key)
            if not next_row:
                continue

            try:
                lat1 = float(row.get("latitude"))
                lon1 = float(row.get("longitude"))
                lat2 = float(next_row.get("latitude"))
                lon2 = float(next_row.get("longitude"))
            except Exception:
                continue

            colour = _hex_to_colour_token(row.get("line_color") or next_row.get("line_color"))
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon1, lat1], [lon2, lat2]],
                },
                "properties": {
                    "name": _sanitize_val(line_name),
                    "line": _sanitize_val(line_name),
                    "colour": _sanitize_val(colour),
                    "transport_type": "metro",
                    "source": "nammametro_csv",
                    "visibility": "always"
                },
            })

        return {"type": "FeatureCollection", "features": features}, station_line_map
    except Exception as e:
        print(f"    [gis/warn] NammaMetro/Railway CSV reference load failed: {e}")
        return {"type": "FeatureCollection", "features": []}, {}
def _enrich_station_lines_from_dataset(stations, station_line_map):
    if not stations or not station_line_map:
        return stations

    for station in stations:
        if station.get("transport_type", "metro") != "metro":
            continue
        key = _station_key(station.get("name"))
        dataset_line = station_line_map.get(key)
        if not dataset_line:
            continue
        station["line"] = _sanitize_val(dataset_line)
        station["colour"] = _sanitize_val(_normalize_metro_colour(dataset_line, None))

    return stations


def _looks_bus_related(text: str) -> bool:
    txt = _text(text)
    return any(k in txt for k in ["bmtc", "bus stop", "bus station", "bus stand", "tram"])


def _looks_non_transit_place(text: str) -> bool:
    txt = _text(text)
    return any(k in txt for k in ["police station", "hospital", "school", "college", "temple"])


def _is_metro_station_row(row, name: str, row_str: str) -> bool:
    railway = _text(row.get("railway"))
    station = _text(row.get("station"))
    route = _text(row.get("route"))
    operator = _text(row.get("operator"))
    network = _text(row.get("network"))
    name_text = _text(name)
    text = _text(f"{name} {row_str}")

    if _looks_bus_related(name_text) or _looks_non_transit_place(name_text):
        return False

    if railway in {"subway", "light_rail"}:
        return True
    if station in {"subway", "light_rail"}:
        return True
    if route in {"subway", "light_rail"}:
        return True
    if "bmrcl" in text or "namma metro" in text:
        return True
    if "metro station" in text:
        return True
    if "metro" in operator or "metro" in network:
        return True
    return False


def _is_rail_station_row(row, name: str, row_str: str) -> bool:
    railway = _text(row.get("railway"))
    station = _text(row.get("station"))
    name_text = _text(name)
    text = _text(f"{name} {row_str}")

    if _looks_bus_related(name_text) or _looks_non_transit_place(name_text):
        return False

    if railway in {"station", "halt"}:
        return True
    if station == "train":
        return True
    if "railway station" in text or "rail gate" in text:
        return True
    return False


def _is_metro_line_row(row, row_str: str) -> bool:
    railway = _text(row.get("railway"))
    operator = _text(row.get("operator"))
    network = _text(row.get("network"))
    name = _text(row.get("name"))
    text = _text(row_str)

    if _looks_bus_related(text) or _looks_non_transit_place(name):
        return False
    if railway in {"subway", "light_rail", "monorail"}:
        return True
    if "bmrcl" in text or "namma metro" in text:
        return True
    if "metro" in text and "railway" not in text:
        return True
    if "metro" in operator or "metro" in network:
        return True
    return False


def _is_rail_line_row(row, row_str: str) -> bool:
    railway = _text(row.get("railway"))
    name = _text(row.get("name"))
    text = _text(row_str)

    if _looks_bus_related(text) or _looks_non_transit_place(name):
        return False

    if railway in {"rail", "narrow_gauge", "preserved"}:
        return True
    if "railway" in text and "metro" not in text:
        return True
    if "indian railways" in text or "southern railway" in text:
        return True
    return False

def _classify_kml_line_name(line_name_str):
    """
    Classify metro line from explicit KML line-name text.
    Keep this strict and dataset-driven (no station-name guessing).
    Returns (line_name, colour) tuple, or (None, None) if color label absent.
    """
    name_l = _text(line_name_str)

    if "purple" in name_l:
        return "Purple Line", "purple"
    if "green" in name_l:
        return "Green Line", "green"
    if "yellow" in name_l:
        return "Yellow Line", "yellow"
    if "blue" in name_l:
        return "Blue Line", "blue"
    if "pink" in name_l:
        return "Pink Line", "pink"
    if "red" in name_l:
        return "Red Line", "red"
    return None, None


def _normalize_metro_colour(line_name, colour_name):
    """Normalize colour token used by frontend map styling."""
    colour = _text(colour_name)
    if colour in {"purple", "green", "yellow", "blue", "pink", "red", "railway"}:
        return colour

    line_txt = _text(line_name)
    if "purple" in line_txt:
        return "purple"
    if "green" in line_txt:
        return "green"
    if "yellow" in line_txt:
        return "yellow"
    if "blue" in line_txt:
        return "blue"
    if "pink" in line_txt:
        return "pink"
    if "red" in line_txt:
        return "red"
    return "unknown"


def _is_generic_station_line(line_name):
    if not line_name:
        return True
    line_str = str(line_name).strip().lower()
    return line_str in {"namma metro", "metro", "unknown", "unknown line", "line"}


def _is_generic_kml_label(line_name):
    line_str = _text(line_name)
    if not line_str:
        return True
    if line_str in {"namma metro", "unknown line", "unknown", "line"}:
        return True
    return ("reach" in line_str) or ("phase" in line_str) or ("ug" in line_str)


def _extract_feature_candidates(feature_collection, transport_type="metro"):
    if isinstance(feature_collection, dict) and feature_collection.get("type") == "FeatureCollection":
        features = feature_collection.get("features", [])
    elif isinstance(feature_collection, list):
        features = feature_collection
    else:
        return []

    candidates = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties", {}) or {}
        if transport_type and props.get("transport_type", "metro") != transport_type:
            continue
        coords = (feature.get("geometry", {}) or {}).get("coordinates", [])
        if not coords or len(coords) < 2:
            continue
        try:
            geom = LineString(coords)
        except Exception:
            continue
        line_name = _sanitize_val(props.get("line") or props.get("name") or "Unknown Line")
        if "red line" in _text(line_name):
            continue
        colour = _sanitize_val(_normalize_metro_colour(line_name, props.get("colour")))
        candidates.append((geom, line_name, colour))
    return candidates


def _enrich_osm_line_labels_from_reference(osm_line_features, reference_lines):
    """Assign OSM metro/railway line labels from nearest KML reference line geometry."""
    if not osm_line_features:
        return osm_line_features

    # Extract both metro and railway candidates from reference
    metro_candidates = _extract_feature_candidates(reference_lines, transport_type="metro")
    railway_candidates = _extract_feature_candidates(reference_lines, transport_type="railway")
    
    specific_metro_candidates = [c for c in metro_candidates if not _is_generic_kml_label(c[1])]
    if specific_metro_candidates:
        metro_candidates = specific_metro_candidates
    
    if not metro_candidates and not railway_candidates:
        return osm_line_features

    for feature in osm_line_features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties", {}) or {}
        transport_type = props.get("transport_type", "metro")
        
        # Process both metro and railway
        if transport_type not in ("metro", "railway"):
            continue

        coords = (feature.get("geometry", {}) or {}).get("coordinates", [])
        if not coords or len(coords) < 2:
            continue
        try:
            geom = LineString(coords)
        except Exception:
            continue

        # Select appropriate candidates based on transport type
        candidates = metro_candidates if transport_type == "metro" else railway_candidates
        
        best_line = None
        best_dist = float("inf")
        for ref_geom, ref_line_name, ref_colour in candidates:
            dist = geom.distance(ref_geom)
            if dist < best_dist:
                best_dist = dist
                best_line = (ref_line_name, ref_colour)

        # ~220m threshold around Bengaluru in degree units.
        if best_line and best_dist <= 0.002:
            props["line"] = _sanitize_val(best_line[0])
            props["name"] = _sanitize_val(best_line[0])
            props["colour"] = _sanitize_val(best_line[1])

    return osm_line_features


def _merge_full_line_reference_segments(osm_feature_collection, reference_feature_collection):
    """
    Keep OSM geometry as primary, and append reference geometry portions not already in OSM.
    Prevents duplications at intersections by computing the geometric difference.
    """
    if not (isinstance(osm_feature_collection, dict) and osm_feature_collection.get("type") == "FeatureCollection"):
        return osm_feature_collection
    if not (isinstance(reference_feature_collection, dict) and reference_feature_collection.get("type") == "FeatureCollection"):
        return osm_feature_collection

    osm_features = list(osm_feature_collection.get("features", []))
    ref_features = list(reference_feature_collection.get("features", []))

    # Index OSM geometry by line name for efficient clipping
    osm_line_geoms = {} # line_name_norm -> list of shapely geoms
    active_lines_metro = set()
    active_lines_railway = set()
    
    # Process OSM features to build union sets
    for feature in osm_features:
        props = (feature or {}).get("properties", {}) or {}
        transport_type = props.get("transport_type", "metro")
        line_name = _text(props.get("line") or props.get("name"))
        
        if not line_name or "red line" in line_name:
            continue
            
        if transport_type == "metro":
            if not _is_generic_kml_label(line_name):
                active_lines_metro.add(line_name)
        elif transport_type == "railway":
            active_lines_railway.add(line_name)

        # For geometry clipping
        geom_dict = feature.get("geometry")
        if geom_dict and geom_dict.get("type") == "LineString":
            try:
                s_geom = shape(geom_dict)
                osm_line_geoms.setdefault(line_name, []).append(s_geom)
            except Exception:
                continue

    # Pre-compute unions per line for clipping reference geometry
    osm_unions = {}
    for name, geoms in osm_line_geoms.items():
        try:
            osm_unions[name] = unary_union(geoms)
        except Exception:
            continue

    merged = list(osm_features) # Keep all OSM features as primary
    tol = 0.00005 # ~5m tolerance for snapping

    for feature in ref_features:
        props = (feature or {}).get("properties", {}) or {}
        transport_type = props.get("transport_type", "metro")
        line_name = _text(props.get("line") or props.get("name"))

        if transport_type == "metro":
            if line_name not in active_lines_metro:
                continue
        elif transport_type == "railway":
            if line_name not in active_lines_railway:
                continue
        else:
            continue

        ref_geom_dict = feature.get("geometry")
        if not ref_geom_dict or ref_geom_dict.get("type") != "LineString":
            continue

        try:
            ref_geom = shape(ref_geom_dict)
            
            # CLIP: If OSM already has some of this line, only add the difference
            if line_name in osm_unions:
                union_geom = osm_unions[line_name]
                # Buffered difference to remove overlapping segments
                clipped = ref_geom.difference(union_geom.buffer(tol))
                
                if clipped.is_empty:
                    continue
                
                # If it's a MultiLineString, add each part separately
                parts = []
                if clipped.geom_type == 'MultiLineString':
                    parts = list(clipped.geoms)
                elif clipped.geom_type == 'LineString':
                    parts = [clipped]
                
                for part in parts:
                    if part.length < 0.0001: # Skip tiny fragments (~10m)
                        continue
                    new_f = {
                        "type": "Feature",
                        "geometry": mapping(part),
                        "properties": {
                            **props, 
                            "source": f"{props.get('source', 'ref')}_clipped"
                        }
                    }
                    merged.append(new_f)
            else:
                # No OSM geometry for this line yet, add as is
                merged.append(feature)
                
        except Exception as e:
            print(f"  [merge/warn] Geometry processing failed for {line_name}: {e}")
            # Fallback to original feature if clipping fails
            merged.append(feature)

    return {
        "type": "FeatureCollection",
        "features": merged,
    }


def _enrich_station_lines_from_network(stations, metro_lines):
    """Fill station line/colour from nearest metro/railway line geometry when station labels are generic."""
    if not stations:
        return stations
    
    # Extract both metro AND railway line candidates
    metro_candidate_lines = _extract_feature_candidates(metro_lines, transport_type="metro")
    railway_candidate_lines = _extract_feature_candidates(metro_lines, transport_type="railway")
    
    print(f"    [enrich] Metro candidates: {len(metro_candidate_lines)}, Railway candidates: {len(railway_candidate_lines)}")
    
    # For metro: prefer specific line names over generic labels
    metro_specific = [c for c in metro_candidate_lines if not _is_generic_kml_label(c[1])]
    if metro_specific:
        metro_candidate_lines = metro_specific

    metro_reference_line_names = {(_text(line_name)) for _, line_name, _ in metro_candidate_lines if _text(line_name)}
    railway_reference_line_names = {(_text(line_name)) for _, line_name, _ in railway_candidate_lines if _text(line_name)}
    
    print(f"    [enrich] Metro lines available: {metro_reference_line_names}")
    print(f"    [enrich] Railway lines available: {railway_reference_line_names}")

    for station in stations:
        transport_type = station.get("transport_type", "metro")
        lat = station.get("lat")
        lon = station.get("lon")
        if lat is None or lon is None:
            continue

        point = Point(lon, lat)
        
        if transport_type == "metro":
            # Process metro stations with metro lines
            if not metro_candidate_lines:
                continue
                
            best_line = None
            best_dist = float("inf")

            for geom, line_name, colour in metro_candidate_lines:
                dist = geom.distance(point)
                if dist < best_dist:
                    best_dist = dist
                    best_line = (line_name, colour)

            current_line = _sanitize_val(station.get("line"))
            current_line_norm = _text(current_line)
            should_override = (
                _is_generic_station_line(current_line)
                or (current_line_norm not in metro_reference_line_names)
            )

            # Approx ~220m in degrees near Bengaluru.
            if should_override and best_line and best_dist <= 0.002:
                station["line"] = _sanitize_val(best_line[0])
                station["colour"] = _sanitize_val(best_line[1])
        
        elif transport_type == "railway":
            # Process railway stations with railway lines
            if not railway_candidate_lines:
                print(f"    [enrich] WARNING: Station '{station.get('name')}' is railway but no railway lines found!")
                continue
                
            best_line = None
            best_dist = float("inf")

            for geom, line_name, colour in railway_candidate_lines:
                dist = geom.distance(point)
                if dist < best_dist:
                    best_dist = dist
                    best_line = (line_name, colour)

            current_line = _sanitize_val(station.get("line"))
            current_line_norm = _text(current_line)
            
            # For railways, always override generic "Indian Railways" with specific track names
            should_override = (
                current_line_norm == "indian railways"
                or _is_generic_station_line(current_line)
                or (current_line_norm not in railway_reference_line_names)
            )

            # Approx ~220m in degrees near Bengaluru.
            if should_override and best_line and best_dist <= 0.002:
                print(f"    [enrich] Railway station '{station.get('name')}': {current_line} → {best_line[0]} (dist={best_dist:.4f})")
                station["line"] = _sanitize_val(best_line[0])
                station["colour"] = _sanitize_val(best_line[1])
            elif best_line:
                print(f"    [enrich] Railway station '{station.get('name')}': keeping {current_line} (no override needed, dist={best_dist:.4f})")
            else:
                print(f"    [enrich] Railway station '{station.get('name')}': NO matching line found!")

    return stations

def _extract_metro_stations(G, center, include_rail=False):
    try:
        print(f"    [gis] Scanning for Stations in {METRO_QUERY_RADIUS_M:,}m radius of {center}...")
        tags = {
            'railway': ['station', 'halt', 'subway', 'light_rail'],
            'station': ['subway', 'light_rail', 'train']
        }
        try:
            stations = ox.features_from_point(center, tags=tags, dist=METRO_QUERY_RADIUS_M)
        except Exception as e:
            # Handle newer OSMnx versions that throw InsufficientResponseError for no results
            if "No matching features" in str(e) or "InsufficientResponseError" in type(e).__name__:
                print(f"    [gis] OSMnx found no stations in this area.")
                return []
            raise e
        
        if stations.empty:
            print(f"    [gis] OSMnx returned ZERO features for tags: {tags}")
            return []
            
        print(f"    [gis] OSMnx returned {len(stations)} raw features. Filtering for Metro...")
        metro_data = []
        for idx, row in stations.iterrows():
            name = row.get('name')
            if not name or not isinstance(name, str):
                continue

            geom_type = getattr(row.geometry, 'geom_type', '')
            if geom_type in ('LineString', 'MultiLineString'):
                continue

            if _looks_project_label(name):
                continue
                
            # Bengaluru Metro / rail classification
            row_str = str(row).lower()
            station_operational_text = " ".join([
                _text(name),
                _text(row.get('description')),
                _text(row.get('note')),
                _text(row.get('construction')),
                _text(row.get('proposed')),
                _text(row.get('opening_date')),
            ])
            if _looks_non_operational(station_operational_text):
                continue
            is_metro = _is_metro_station_row(row, name, row_str)
            is_railway = (not is_metro) and _is_rail_station_row(row, name, row_str)
            
            if not is_metro and not is_railway:
                continue
            if is_railway and not include_rail:
                continue

            # Extract lat/lon from geometry
            point = row.geometry.centroid
            # Snap to road network
            node_id = ox.nearest_nodes(G, point.x, point.y)
            
            # Categorize
            transport_type = 'metro' if is_metro else 'railway'

            # Smart Sniffing for Namma Metro
            line_name, colour = None, None
            if transport_type == 'metro':
                # For stations: do not infer by station name.
                # Keep OSM tag if present; KML spatial cross-check enriches later.
                line_name = _sanitize_val(row.get('line') or row.get('route') or row.get('network') or 'Unknown Line')
                colour = _normalize_metro_colour(line_name, None)
            else:
                line_name = _sanitize_val(row.get('line') or row.get('route') or row.get('name') or "Indian Railways")
                colour = 'railway'

            metro_data.append({
                "id": str(idx),
                "name": _sanitize_val(name),
                "lat": point.y,
                "lon": point.x,
                "node_id": int(node_id),
                "line": _sanitize_val(line_name),
                "colour": _sanitize_val(colour),
                "transport_type": transport_type
            })
            
        print(f"    [gis] SUCCESS: Extracted {len(metro_data)} Namma Metro/Railway Stations.")
        
        # Log breakdown
        metro_count = sum(1 for m in metro_data if m.get("transport_type") == "metro")
        rail_count = sum(1 for m in metro_data if m.get("transport_type") == "railway")
        print(f"      └─ Metro: {metro_count}, Railway: {rail_count}")
        if rail_count > 0:
            print(f"      └─ Railway stations: {[m.get('name') for m in metro_data if m.get('transport_type') == 'railway'][:5]}")
        
        return metro_data
    except Exception as e:
        import traceback
        print(f"    [gis/error] Metro extraction failed: {e}")
        traceback.print_exc()
        return []

def _extract_metro_lines(center, include_rail=False, label_reference_lines=None):
    """Extract metro railway geometries as GeoJSON features."""
    try:
        print(f"    [gis] Scanning for Metro Lines in {METRO_QUERY_RADIUS_M:,}m radius of {center}...")
        tags = {
            'railway': ['subway', 'light_rail', 'rail'],
            'route': ['subway', 'light_rail', 'train']
        }
        try:
            features = ox.features_from_point(center, tags=tags, dist=METRO_QUERY_RADIUS_M)
        except Exception as e:
            # Handle newer OSMnx versions that throw InsufficientResponseError for no results
            if "No matching features" in str(e) or "InsufficientResponseError" in type(e).__name__:
                print(f"    [gis] OSMnx found no metro lines in this area.")
                if isinstance(label_reference_lines, dict) and label_reference_lines.get("type") == "FeatureCollection":
                    return label_reference_lines
                return {"type": "FeatureCollection", "features": []}
            raise e
        
        if features.empty:
            print(f"    [gis] OSMnx returned ZERO line features for tags: {tags}")
            # Still check KML as fallback
            if isinstance(label_reference_lines, dict) and label_reference_lines.get("type") == "FeatureCollection":
                print(f"    [gis] Using KML fallback with {len(label_reference_lines.get('features', []))} features")
                return label_reference_lines
            return {"type": "FeatureCollection", "features": []}

        # Filter for LineStrings only
        lines = features[features.geometry.type == 'LineString']
        metro_lines = []
        
        for idx, row in lines.iterrows():
            name = row.get('name')
            row_str = str(row).lower()

            if _looks_non_operational(row_str):
                continue
            if _looks_project_label(name):
                continue
            
            # Extract all Metro/Rail geometries; visibility property controls UI rendering
            is_metro = _is_metro_line_row(row, row_str)
            is_railway = (not is_metro) and _is_rail_line_row(row, row_str)
            
            if not is_metro and not is_railway:
                continue

            transport_type = 'metro' if is_metro else 'railway'

            # Smart Sniffing for Namma Metro
            line_name, colour = None, None
            if transport_type == 'metro':
                # Tracks from OSM; labels are enriched from KML reference later.
                line_name = _sanitize_val(row.get('line') or row.get('route') or row.get('network') or name or 'Unknown Line')
                colour = _normalize_metro_colour(line_name, None)
            else:
                line_name = _sanitize_val(row.get('line') or row.get('route') or name or "Railway Track")
                colour = 'railway'

            # Convert geometry to list of [lon, lat]
            coords = list(row.geometry.coords)
            
            metro_lines.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coords
                },
                "properties": {
                    "name": _sanitize_val(line_name if transport_type == 'metro' else name),
                    "line": _sanitize_val(line_name),
                    "colour": _sanitize_val(colour),
                    "transport_type": transport_type,
                    "visibility": "station_only" if transport_type == "railway" else "always"
                }
            })
            
        if label_reference_lines:
            metro_lines = _enrich_osm_line_labels_from_reference(metro_lines, label_reference_lines)

        # Log breakdown
        metro_line_count = sum(1 for f in metro_lines if f.get("properties", {}).get("transport_type") == "metro")
        rail_line_count = sum(1 for f in metro_lines if f.get("properties", {}).get("transport_type") == "railway")
        print(f"    [gis] SUCCESS: Extracted {len(metro_lines)} Namma Metro/Railway Line segments from OSM (labels via KML).")
        print(f"      └─ Metro lines: {metro_line_count}, Railway lines: {rail_line_count}")
        
        return {"type": "FeatureCollection", "features": metro_lines}
    except Exception as e:
        print(f"    [gis/error] Metro line extraction failed: {e}")
        return {"type": "FeatureCollection", "features": []}


def _extract_metro_lines_from_kml(center, include_rail=False):
    """Try extracting metro lines from local KML before falling back to OSM."""
    if not METRO_KML.exists():
        return []

    try:
        import geopandas as gpd
        import math

        lat, lon = center
        radius_m = METRO_QUERY_RADIUS_M
        delta_lat = radius_m / 111320.0
        delta_lon = radius_m / (111320.0 * max(math.cos(math.radians(lat)), 0.2))
        query_bbox = box(lon - delta_lon, lat - delta_lat, lon + delta_lon, lat + delta_lat)

        lines_gdf = gpd.read_file(METRO_KML)
        if lines_gdf.empty:
            return []

        lines_gdf = lines_gdf[lines_gdf.geometry.notnull()]
        if lines_gdf.empty:
            return []

        # First pass: classify all rows and remember metro line names touching query bbox.
        classified_rows = []
        in_range_metro_line_names = set()
        for idx, row in lines_gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            name = _sanitize_val(row.get("Name") or row.get("name") or row.get("Name 1") or row.get("NAME") or "")
            desc = _sanitize_val(row.get("Description") or row.get("description") or "")
            row_str = f"{name} {desc}".lower()

            if _looks_non_operational(row_str):
                continue
            if _looks_project_label(name):
                continue

            is_metro = (
                ('bmrcl' in row_str)
                or ('namma metro' in row_str)
                or ('metro' in row_str and 'railway' not in row_str and not _looks_bus_related(row_str))
                or ('reach' in row_str)
                or ('phase' in row_str)
                or ('subway' in row_str)
                or ('light_rail' in row_str)
            )
            is_railway = (not is_metro) and ('railway' in row_str or 'train' in row_str or 'rail' in row_str)

            if not is_metro and not is_railway:
                continue

            transport_type = 'metro' if is_metro else 'railway'
            if transport_type == 'metro':
                line_name, colour = _classify_kml_line_name(name)
                if not line_name:
                    # Keep dataset-native label text for later spatial propagation.
                    line_name = _sanitize_val(name or row.get("line") or row.get("Line") or row.get("route") or "Unknown Line")
                    colour = _normalize_metro_colour(line_name, None)
                else:
                    colour = _normalize_metro_colour(line_name, colour)

                if "red line" in _text(line_name):
                    continue

                if geom.intersects(query_bbox):
                    in_range_metro_line_names.add(str(line_name).strip().lower())
            else:
                line_name, colour = (name or "Railway Track"), 'railway'

            classified_rows.append({
                "geom": geom,
                "name": name,
                "line_name": line_name,
                "colour": colour,
                "transport_type": transport_type,
                "is_in_bbox": bool(geom.intersects(query_bbox)),
            })

        if not classified_rows:
            return []

        # Propagate explicit color-line labels (Purple/Green/Blue/etc.) to nearby
        # generic KML segments (Reach/Phase/UG) using geometry proximity.
        metro_seed_rows = []
        for item in classified_rows:
            if item["transport_type"] != "metro":
                continue
            if not _is_generic_kml_label(item["line_name"]):
                metro_seed_rows.append(item)

        if metro_seed_rows:
            for item in classified_rows:
                if item["transport_type"] != "metro":
                    continue
                if not _is_generic_kml_label(item["line_name"]):
                    continue

                best = None
                best_dist = float("inf")
                for seed in metro_seed_rows:
                    dist = item["geom"].distance(seed["geom"])
                    if dist < best_dist:
                        best_dist = dist
                        best = seed

                # ~220m threshold for connected KML corridor segments.
                if best is not None and best_dist <= 0.002:
                    item["line_name"] = best["line_name"]
                    item["colour"] = best["colour"]

        metro_lines = []
        for item in classified_rows:
            geom = item["geom"]
            transport_type = item["transport_type"]
            line_name = item["line_name"]
            colour = item["colour"]
            name = item["name"]

            # For metro: include full geometry for any line that touches this region.
            # For railway: also include full geometry to ensure complete line rendering
            if transport_type == 'metro':
                if str(line_name).strip().lower() not in in_range_metro_line_names:
                    continue
            else:
                # For railway: if it touches the query box, include the FULL line geometry
                if not item["is_in_bbox"]:
                    continue
                # But we'll include the complete geometry, not just the bbox portion

            if geom.geom_type == 'LineString':
                geoms = [geom]
            elif geom.geom_type == 'MultiLineString':
                geoms = list(geom.geoms)
            else:
                continue

            for part in geoms:
                coords = list(part.coords)
                if len(coords) < 2:
                    continue
                metro_lines.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    },
                    "properties": {
                        "name": line_name if transport_type == 'metro' else name,
                        "line": _sanitize_val(line_name),
                        "colour": _sanitize_val(colour),
                        "transport_type": transport_type,
                        "visibility": "station_only" if transport_type == "railway" else "always"
                    }
                })

        print(f"    [gis] KML extracted {len(metro_lines)} lines")
        return {
            "type": "FeatureCollection",
            "features": metro_lines
        }
    except Exception as e:
        print(f"    [gis/warn] KML metro extraction failed: {e}. Falling back to OSM.")
        return {"type": "FeatureCollection", "features": []}


def _load_metro_lines_from_geojson(center):
    """Load metro lines from authoritative GeoJSON, using description for colour detection."""
    if not METRO_GEOJSON.exists():
        return {"type": "FeatureCollection", "features": []}

    import json

    with open(METRO_GEOJSON) as f:
        data = json.load(f)

    features = []
    for feature in data.get("features", []):
        props = feature["properties"]
        line_name_raw = props.get("Name", "")
        description = props.get("description", "")
        combined = f"{line_name_raw} {description}".strip()

        # Classify using both name and description to detect colour
        line_name_display, colour = _classify_kml_line_name(combined)
        if not line_name_display:
            # Fallback: still try to normalize colour from the combined string
            line_name_display = line_name_raw
            colour = _normalize_metro_colour(combined, None)

        features.append({
            "type": "Feature",
            "geometry": feature["geometry"],
            "properties": {
                "name": line_name_display,
                "line": line_name_display,
                "colour": colour,
                "transport_type": "metro",
                "source": "bmrcl_geojson"
            }
        })

    return {"type": "FeatureCollection", "features": features}

