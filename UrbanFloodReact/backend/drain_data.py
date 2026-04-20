"""
drain_data.py
─────────────
Standalone module for loading, validating, and spatially filtering
storm-water drain data for the Bengaluru flood Digital Twin.

Design:
  - Data-source agnostic: currently reads an IoT-style CSV; the loader
    can be swapped for GIS / sensor APIs without changing downstream code.
  - All public functions return plain Python dicts/lists (JSON-serialisable).
  - Spatial math uses Haversine (geodetically correct for Bengaluru-scale).

CSV schema handled (test_drains.csv / future real data):
  Required : drain_id, latitude, longitude
  Optional : sensor_id, location_name, measure_type, timestamp,
             water_level_cm, flow_index, rainfall_mm, battery_v,
             status, alert_sent, width_m, depth_m, capacity_factor,
             condition, drain_type
"""

import csv
import math
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("drain_data")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(_ch)

# ── Configurable parameters ──────────────────────────────────────────────────
# Maximum radius (metres) within which a drain influences a graph node.
# Realistic value for open channels / rajakaluve in Bengaluru (50-200 m).
DRAIN_INFLUENCE_RADIUS_M: float = 200.0

# Maximum drainage capacity factor applied per step.
# 1.0 = drain removes 100 % of eligible water; 0.3 = removes 30 %.
MAX_DRAIN_CAPACITY_FACTOR: float = 0.30

# Penalty factor for blocked / overflowing drains.
# Values > 1.0 mean the drain *adds* water (overflow).
BLOCKED_DRAIN_OVERFLOW_FACTOR: float = 1.15

# Weight of elevation difference between node and drain in capacity calc.
DRAIN_ELEVATION_WEIGHT: float = 0.4

# Default drain dimensions when CSV lacks geometry columns.
DEFAULT_DRAIN_WIDTH_M: float = 1.5
DEFAULT_DRAIN_DEPTH_M: float = 1.0

# Earth radius for Haversine (km).
_EARTH_RADIUS_KM: float = 6371.0

# ── CSV column sets ──────────────────────────────────────────────────────────
REQUIRED_COLUMNS = {"drain_id", "latitude", "longitude"}
OPTIONAL_COLUMNS = {
    "sensor_id", "location_name", "measure_type", "timestamp",
    "water_level_cm", "flow_index", "rainfall_mm", "battery_v",
    "status", "alert_sent", "width_m", "depth_m", "capacity_factor",
    "condition", "drain_type",
}

# Default CSV path (relative to this file).
_DATA_DIR = Path(__file__).parent / "data"
DEFAULT_CSV_PATH = _DATA_DIR / "test_drains.csv"


# ── Internal model ───────────────────────────────────────────────────────────
@dataclass
class DrainSegment:
    """Unified internal representation of a storm-water drain segment."""
    drain_id: str
    lat: float
    lon: float
    location_name: str = ""
    drain_type: str = "unknown"        # rajakaluve / storm_drain / canal / …
    width_m: float = DEFAULT_DRAIN_WIDTH_M
    depth_m: float = DEFAULT_DRAIN_DEPTH_M
    capacity_factor: float = 1.0       # 0–1; 1 = fully functional
    condition: str = "unknown"         # good / fair / poor / blocked
    status: str = "normal"             # normal / warning / critical
    water_level_cm: float = 0.0        # latest sensor reading
    flow_index: float = 0.0            # 0–1 dimensionless velocity proxy
    sensor_ids: List[str] = field(default_factory=list)
    reading_count: int = 0             # how many sensor rows contributed
    geometry_points: List[Tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Haversine ────────────────────────────────────────────────────────────────
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS-84 points."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Loader ───────────────────────────────────────────────────────────────────
def load_drain_data(csv_path: Optional[str] = None) -> List[DrainSegment]:
    """
    Load drain segments from a CSV file.

    The CSV may be an IoT time-series (multiple rows per drain_id).
    Rows are grouped by drain_id; sensor readings are aggregated
    (latest timestamp wins for status; max for water_level).

    Returns an empty list (with warning) if the file is missing / empty.
    """
    path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH

    if not path.exists():
        logger.warning("Drain CSV not found at %s — continuing without drain data.", path)
        return []

    # ── 1. Read raw rows ─────────────────────────────────────────────────
    raw_rows: List[dict] = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                logger.warning("Drain CSV has no header row: %s", path)
                return []

            # Validate schema
            header_set = {c.strip().lower() for c in reader.fieldnames}
            missing = REQUIRED_COLUMNS - header_set
            if missing:
                logger.error(
                    "Drain CSV missing required columns %s. Found: %s",
                    missing, header_set,
                )
                return []

            logger.info("Drain CSV schema OK — required: %s, optional present: %s",
                        REQUIRED_COLUMNS,
                        OPTIONAL_COLUMNS & header_set)

            for row in reader:
                # Normalise keys to lowercase stripped
                row = {k.strip().lower(): v.strip() if isinstance(v, str) else v
                       for k, v in row.items() if k is not None}
                raw_rows.append(row)
    except Exception as exc:
        logger.error("Failed to read drain CSV %s: %s", path, exc)
        return []

    # Filter out completely empty rows (blank lines in CSV)
    raw_rows = [r for r in raw_rows if r.get("drain_id")]

    if not raw_rows:
        logger.warning("Drain CSV loaded but contains zero valid rows.")
        return []

    logger.info("Loaded %d raw drain rows from %s", len(raw_rows), path.name)

    # ── 2. Group by drain_id ─────────────────────────────────────────────
    groups: Dict[str, List[dict]] = {}
    skipped = 0
    for row in raw_rows:
        drain_id = row.get("drain_id", "").strip()
        if not drain_id:
            skipped += 1
            continue
        try:
            lat = float(row.get("latitude", 0))
            lon = float(row.get("longitude", 0))
            if lat == 0.0 or lon == 0.0:
                raise ValueError("zero coords")
        except (ValueError, TypeError):
            skipped += 1
            logger.debug("Skipping row with invalid coordinates: drain_id=%s", drain_id)
            continue

        groups.setdefault(drain_id, []).append(row)

    if skipped:
        logger.warning("Skipped %d rows with missing/invalid drain_id or coordinates.", skipped)

    # ── 3. Aggregate into DrainSegment ───────────────────────────────────
    drains: List[DrainSegment] = []
    for drain_id, rows in groups.items():
        # Use first row for static fields, aggregate sensors
        ref = rows[0]
        lat = float(ref["latitude"])
        lon = float(ref["longitude"])

        # Latest status (by timestamp if available, else last row)
        sorted_rows = sorted(rows, key=lambda r: r.get("timestamp", ""))
        latest = sorted_rows[-1]

        # Max water level across readings
        water_levels = []
        flow_indices = []
        sensor_ids = set()
        for r in rows:
            sid = r.get("sensor_id", "")
            if sid:
                sensor_ids.add(sid)
            try:
                wl = float(r.get("water_level_cm") or 0)
                if wl > 0:
                    water_levels.append(wl)
            except (ValueError, TypeError):
                pass
            try:
                fi = float(r.get("flow_index") or 0)
                if fi > 0:
                    flow_indices.append(fi)
            except (ValueError, TypeError):
                pass

        max_wl = max(water_levels) if water_levels else 0.0
        avg_fi = sum(flow_indices) / len(flow_indices) if flow_indices else 0.0

        # Condition inference from status
        raw_status = (latest.get("status") or "normal").lower().strip()
        if raw_status in ("critical",):
            condition = "poor"
            capacity_fac = 0.3        # severely blocked / overflowing
        elif raw_status in ("warning",):
            condition = "fair"
            capacity_fac = 0.6
        else:
            condition = "good"
            capacity_fac = 1.0

        # Override with explicit columns if present
        try:
            capacity_fac = float(ref.get("capacity_factor") or capacity_fac)
        except (ValueError, TypeError):
            pass

        seg = DrainSegment(
            drain_id=drain_id,
            lat=lat,
            lon=lon,
            location_name=ref.get("location_name", ""),
            drain_type=ref.get("drain_type", "storm_drain"),
            width_m=_safe_float(ref.get("width_m"), DEFAULT_DRAIN_WIDTH_M),
            depth_m=_safe_float(ref.get("depth_m"), DEFAULT_DRAIN_DEPTH_M),
            capacity_factor=min(1.0, max(0.0, capacity_fac)),
            condition=condition,
            status=raw_status,
            water_level_cm=max_wl,
            flow_index=avg_fi,
            sensor_ids=list(sensor_ids),
            reading_count=len(rows),
            geometry_points=[(lat, lon)],   # point for now; line when GIS data arrives
        )
        drains.append(seg)

    logger.info(
        "Normalised %d unique drain segments from %d groups.",
        len(drains), len(groups),
    )
    for d in drains:
        logger.debug(
            "  Drain %s @ (%.4f, %.4f) — %s, capacity=%.2f, wl=%.1fcm, sensors=%s",
            d.drain_id, d.lat, d.lon, d.condition,
            d.capacity_factor, d.water_level_cm, d.sensor_ids,
        )
    return drains


# ── Spatial filtering ────────────────────────────────────────────────────────
def filter_drains_by_radius(
    drains: List[DrainSegment],
    center_lat: float,
    center_lon: float,
    radius_km: float = 2.0,
) -> List[DrainSegment]:
    """
    Return only drains whose coordinates fall within ``radius_km`` of
    ``(center_lat, center_lon)`` using Haversine distance.

    Justification: the test dataset has point-based drain locations, so
    point-in-radius is the correct spatial predicate. When real data
    arrives with LineString geometries, this should be upgraded to
    line-intersects-buffer (e.g. Shapely ``geometry.intersects(buffer)``).
    """
    if not drains:
        return []

    filtered = []
    for d in drains:
        dist = haversine_km(center_lat, center_lon, d.lat, d.lon)
        if dist <= radius_km:
            filtered.append(d)
            logger.debug(
                "  ✓ Drain %s at %.2f km from center — included.",
                d.drain_id, dist,
            )
        else:
            logger.debug(
                "  ✗ Drain %s at %.2f km from center — excluded (> %.1f km).",
                d.drain_id, dist, radius_km,
            )

    logger.info(
        "Spatial filter: %d / %d drains within %.1f km of (%.4f, %.4f).",
        len(filtered), len(drains), radius_km, center_lat, center_lon,
    )
    return filtered


# ── Derived metrics for graph nodes ──────────────────────────────────────────
def compute_drain_influence_metrics(
    drains: List[DrainSegment],
    G,  # networkx MultiDiGraph
) -> Dict[str, Any]:
    """
    Compute per-node drain influence metrics and attach them to the graph.

    Returns a summary dict and mutates ``G`` by setting node attributes:
      - ``nearest_drain_dist_m``  : distance to closest drain (metres)
      - ``drainage_capacity``     : 0–1 factor (higher = better drainage)
      - ``ponding_risk``          : 0–1 score (higher = worse)
      - ``drain_elevation_diff``  : elevation of node minus drain elevation

    The metrics are used by ``flood_simulator.py`` to modulate water depth
    during each propagation step.
    """
    if not drains or G is None or len(G.nodes) == 0:
        logger.info("No drains or empty graph — drain influence metrics skipped.")
        return {"drain_count": 0, "nodes_influenced": 0}

    influence_radius_km = DRAIN_INFLUENCE_RADIUS_M / 1000.0
    nodes_influenced = 0
    drain_locs = [(d.lat, d.lon, d.capacity_factor, d.condition, d.status,
                    d.water_level_cm, d.drain_id) for d in drains]

    for node_id, data in G.nodes(data=True):
        n_lat = data.get("y", 0.0)
        n_lon = data.get("x", 0.0)
        n_elev = data.get("elevation", 0.0)

        best_dist_km = float("inf")
        best_drain = None

        for d_lat, d_lon, d_cap, d_cond, d_status, d_wl, d_id in drain_locs:
            dist = haversine_km(n_lat, n_lon, d_lat, d_lon)
            if dist < best_dist_km:
                best_dist_km = dist
                best_drain = (d_cap, d_cond, d_status, d_wl, d_lat, d_lon, d_id)

        best_dist_m = best_dist_km * 1000.0

        if best_drain is None or best_dist_m > DRAIN_INFLUENCE_RADIUS_M:
            # Too far from any drain — no influence
            G.nodes[node_id]["nearest_drain_dist_m"] = best_dist_m
            G.nodes[node_id]["drainage_capacity"] = 0.0
            G.nodes[node_id]["ponding_risk"] = 0.5   # neutral baseline
            G.nodes[node_id]["drain_elevation_diff"] = 0.0
            continue

        nodes_influenced += 1
        d_cap, d_cond, d_status, d_wl, d_lat, d_lon, d_id = best_drain

        # ── Distance decay: linear falloff from drain to influence edge ──
        proximity_factor = max(0.0, 1.0 - (best_dist_m / DRAIN_INFLUENCE_RADIUS_M))

        # ── Elevation difference ─────────────────────────────────────────
        # Positive diff = node is higher than drain → gravity assists drainage.
        # We approximate drain elevation as the nearest-node elevation minus
        # a small offset (drains are typically in depressions/along roads).
        drain_elev_approx = n_elev - 1.0  # assume drain is ~1m lower than surface
        elev_diff = n_elev - drain_elev_approx
        elev_factor = min(1.0, max(0.0, elev_diff / 5.0))  # normalise to 0–1

        # ── Capacity: combines drain condition + proximity + elevation ────
        # A fully functional drain at close range with downhill slope gets
        # the maximum capacity factor.
        drainage_capacity = (
            d_cap
            * proximity_factor
            * (1.0 - DRAIN_ELEVATION_WEIGHT + DRAIN_ELEVATION_WEIGHT * elev_factor)
        )
        drainage_capacity = min(MAX_DRAIN_CAPACITY_FACTOR, max(0.0, drainage_capacity))

        # ── Ponding risk ─────────────────────────────────────────────────
        # High risk if drain is blocked/overflowing AND the node is nearby.
        if d_cond in ("poor", "blocked") or d_status == "critical":
            ponding_risk = 0.7 + 0.3 * proximity_factor
        elif d_cond == "fair" or d_status == "warning":
            ponding_risk = 0.4 + 0.2 * proximity_factor
        else:
            # Good drain nearby → low ponding risk
            ponding_risk = max(0.0, 0.3 - 0.3 * proximity_factor)

        G.nodes[node_id]["nearest_drain_dist_m"] = round(best_dist_m, 1)
        G.nodes[node_id]["drainage_capacity"] = round(drainage_capacity, 4)
        G.nodes[node_id]["ponding_risk"] = round(ponding_risk, 3)
        G.nodes[node_id]["drain_elevation_diff"] = round(elev_diff, 2)

    # ── Compute area-level summary ───────────────────────────────────────
    # Rough simulation area in km² (π r² with radius = 2 km)
    area_km2 = math.pi * 4.0  # 2 km radius → ~12.57 km²
    drain_density = len(drains) / area_km2 if area_km2 > 0 else 0.0

    avg_spacing_m = 0.0
    if len(drains) > 1:
        dists = []
        for i, d1 in enumerate(drains):
            for d2 in drains[i + 1:]:
                dists.append(haversine_km(d1.lat, d1.lon, d2.lat, d2.lon) * 1000)
        avg_spacing_m = sum(dists) / len(dists) if dists else 0.0

    summary = {
        "drain_count": len(drains),
        "nodes_influenced": nodes_influenced,
        "total_nodes": len(G.nodes),
        "influence_radius_m": DRAIN_INFLUENCE_RADIUS_M,
        "drain_density_per_km2": round(drain_density, 3),
        "avg_drain_spacing_m": round(avg_spacing_m, 1),
        "drain_ids": [d.drain_id for d in drains],
    }

    logger.info(
        "Drain influence applied: %d/%d nodes influenced, density=%.3f/km², spacing=%.0fm",
        nodes_influenced, len(G.nodes), drain_density, avg_spacing_m,
    )
    return summary


# ── Utility / query functions (used by MCP tools and service layer) ──────────
def get_drain_summary(drains: List[DrainSegment]) -> dict:
    """Human-readable summary of a drain list."""
    if not drains:
        return {"count": 0, "message": "No drains loaded."}

    conditions = {}
    for d in drains:
        conditions[d.condition] = conditions.get(d.condition, 0) + 1

    return {
        "count": len(drains),
        "drain_ids": [d.drain_id for d in drains],
        "locations": [d.location_name for d in drains if d.location_name],
        "condition_breakdown": conditions,
        "avg_water_level_cm": round(
            sum(d.water_level_cm for d in drains) / len(drains), 1
        ) if drains else 0.0,
        "avg_capacity_factor": round(
            sum(d.capacity_factor for d in drains) / len(drains), 2
        ) if drains else 0.0,
    }


def get_nearest_drains(
    lat: float, lon: float,
    drains: List[DrainSegment],
    n: int = 5,
) -> List[dict]:
    """Return the *n* closest drains to (lat, lon), sorted by distance."""
    if not drains:
        return []
    scored = []
    for d in drains:
        dist = haversine_km(lat, lon, d.lat, d.lon)
        scored.append((dist, d))
    scored.sort(key=lambda x: x[0])
    result = []
    for dist_km, d in scored[:n]:
        entry = d.to_dict()
        entry["distance_km"] = round(dist_km, 3)
        entry["distance_m"] = round(dist_km * 1000, 1)
        result.append(entry)
    return result


def get_drains_for_hobli(hobli_key: str) -> List[DrainSegment]:
    """
    Load all drains and filter to those within the 2 km radius
    of the given hobli.  Returns an empty list if the hobli is
    unknown or drain data is unavailable.
    """
    try:
        from region_manager import HOBLI_COORDS
        from coord_loader import norm_key
        key = norm_key(hobli_key)
        coords = HOBLI_COORDS.get(key)
        if not coords:
            logger.warning("Hobli '%s' not in HOBLI_COORDS — cannot filter drains.", hobli_key)
            return []
        center_lat = coords["lat"]
        center_lon = coords["lon"]
    except Exception as e:
        logger.error("Cannot resolve hobli '%s': %s", hobli_key, e)
        return []

    all_drains = load_drain_data()
    return filter_drains_by_radius(all_drains, center_lat, center_lon, radius_km=2.0)


# ── Private helpers ──────────────────────────────────────────────────────────
def _safe_float(val, default: float) -> float:
    """Convert to float or return default."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ── Self-test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== drain_data.py self-test ===")
    drains = load_drain_data()
    print(f"\nLoaded {len(drains)} drain segments.")
    for d in drains:
        print(f"  {d.drain_id}: {d.location_name} @ ({d.lat}, {d.lon}) "
              f"condition={d.condition} cap={d.capacity_factor} wl={d.water_level_cm}cm")

    # Test spatial filter for Kasaba hobli centre (~12.978, 77.589)
    filtered = filter_drains_by_radius(drains, 12.978, 77.589, radius_km=2.0)
    print(f"\nFiltered (Kasaba, 2km): {len(filtered)} drains")

    # Test filter for Indiranagar area — should include at least 1 drain
    filtered2 = filter_drains_by_radius(drains, 12.9716, 77.6412, radius_km=2.0)
    print(f"Filtered (Indiranagar pin, 2km): {len(filtered2)} drains")

    summary = get_drain_summary(drains)
    print(f"\nSummary: {summary}")
