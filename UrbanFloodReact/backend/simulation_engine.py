"""
Rainfall simulation, person movement, and session management for the simulate-citizen feature.
Provides scenario picking, rainfall evolution, and person pathfinding.
"""
import random
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from math import radians, cos, sin, sqrt, atan2, exp
import networkx as nx
import logging
from db import _get_db

logger = logging.getLogger(__name__)


# ── Server-side session store ─────────────────────────────────────────────
SIMULATE_SESSIONS: Dict[str, 'SimulationSession'] = {}
SESSION_MAX_AGE_SECONDS = 7200  # 2 hours


@dataclass
class PersonPosition:
    """Tracks a person's position along a route path."""
    path_nodes: List[int]
    G: nx.DiGraph
    speed_kph: float
    tick_mins: float
    current_edge_idx: int = 0
    edge_progress: float = 0.0

    def advance(self) -> Tuple[float, float]:
        """Move person by one tick. Returns (lat, lon) of new position."""
        dist_to_cover = (self.speed_kph / 60) * self.tick_mins * 1000

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

    def _interpolate_position(self) -> Tuple[float, float]:
        """Returns current (lat, lon) by interpolating along current edge."""
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
        """Returns OSM node ID of current position."""
        return self.path_nodes[min(self.current_edge_idx, len(self.path_nodes) - 1)]

    def is_arrived(self) -> bool:
        """Check if person reached destination."""
        return self.current_edge_idx >= len(self.path_nodes) - 1


@dataclass
class SimulationSession:
    """Server-side state for one simulation session."""
    session_id: str
    G: nx.DiGraph
    path_nodes: List[int]
    position: PersonPosition
    rainfall: Dict[str, float]  # { hobli: mm_per_tick }
    hobli_coords: Dict[str, Tuple[float, float]]
    active_hoblis: List[str]
    route_history: List[Dict] = field(default_factory=list)
    tick: int = 0
    evolution_mode: str = "random"
    speed_kph: float = 30.0
    speed_mode: str = "car"
    tick_mins: float = 5.0
    dst_lat: float = 0.0
    dst_lon: float = 0.0
    scenario_date: str = ""
    scenario_month: str = ""
    last_accessed: float = 0.0
    original_route_max_depth: float | None = None
    mode: str = "simulated"  # "simulated" or "realtime"
    rainfall_source: str = "simulated"  # "simulated" or "ksndmc"
    use_traffic: bool = False  # NEW: whether ETA considers traffic
    storm_center: Optional[Tuple[float, float]] = None  # Tracked storm center for "move" mode
    storm_total_rain: float = 0.0  # Total rainfall energy to conserve in "move" mode
    storm_radius_m: float = 8000.0  # Storm cell radius in metres


# ── Rainfall scenario picking and evolution ────────────────────────────────

def normalize_hobli_name(name: str) -> str:
    """Normalize hobli name for matching (strip _1, _2 suffixes)."""
    import re
    return re.sub(r'_\d+$', '', name).strip().lower()


async def fetch_hobli_coords() -> Dict[str, Tuple[float, float]]:
    """Fetch { hobli_name: (lat, lon) } from hobli_coords collection."""
    db = _get_db()
    if db is None:
        return {}
    try:
        docs = list(db.hobli_coords.find(
            {}, {"_id": 0, "hobli_name": 1, "latitude": 1, "longitude": 1}
        ).limit(200))
        return {
            d["hobli_name"]: (float(d["latitude"]), float(d["longitude"]))
            for d in docs if d.get("hobli_name")
        }
    except Exception:
        return {}


def assign_hoblis_to_nodes(
    G: nx.DiGraph,
    hobli_coords: Dict[str, Tuple[float, float]]
) -> Dict[int, str]:
    """For each node in G, find nearest hobli centroid (haversine)."""
    def haversine(lat1, lon1, lat2, lon2):
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return atan2(sqrt(a), sqrt(1 - a))

    hobli_for_node = {}
    for node_id in G.nodes:
        node = G.nodes[node_id]
        lat, lon = node["lat"], node["lon"]
        if hobli_coords is not None and len(hobli_coords) > 0:
            nearest = min(
                hobli_coords.items(),
                key=lambda x: haversine(lat, lon, x[1][0], x[1][1])
            )
            hobli_for_node[node_id] = nearest[0]
        else:
            hobli_for_node[node_id] = "unknown"
    return hobli_for_node


async def pick_scenario(
    month: Optional[str] = None,
    intensity: str = "random"
) -> Tuple[Dict[str, float], str, str]:
    """
    Pick a historical rainfall scenario from MongoDB.
    Returns (rainfall_mm_per_tick, scenario_date, month).
    """
    db = _get_db()
    if db is None:
        # Fallback: uniform 10mm/24h = 0.069mm/tick
        TICK_SCALE = 1 / (24 * 12)
        return {"fallback": 10.0 * TICK_SCALE}, "unknown", "July"

    # 1. Choose month
    if month is None:
        month = random.choice(["May", "June", "July"])

    # 2. Fetch records for that month
    try:
        month_doc = db.rainfall_data.find_one({"month": month})
        if month_doc is None or not month_doc.get("records"):
            month = "July"
            month_doc = db.rainfall_data.find_one({"month": month})
        if month_doc is None or not month_doc.get("records"):
            TICK_SCALE = 1 / (24 * 12)
            return {"fallback": 10.0 * TICK_SCALE}, "unknown", "July"

        records = month_doc["records"]
    except Exception:
        TICK_SCALE = 1 / (24 * 12)
        return {"fallback": 10.0 * TICK_SCALE}, "unknown", "July"

    # 3. Filter by intensity
    intensity_ranges = {
        "light": (0, 10),
        "moderate": (10, 30),
        "heavy": (30, 60),
        "extreme": (60, 200),
    }
    if intensity == "random":
        min_mm, max_mm = 0, 200
    else:
        min_mm, max_mm = intensity_ranges.get(intensity, (0, 200))

    filtered = [
        r for r in records
        if min_mm <= float(r.get("24h_Actual_mm", 0)) <= max_mm
    ]
    if not filtered:
        filtered = records

    # 4. Pick random date
    if not filtered:
        TICK_SCALE = 1 / (24 * 12)
        return {"fallback": 10.0 * TICK_SCALE}, "unknown", month

    target_record = random.choice(filtered)
    target_date = target_record["Date"]
    date_records = [r for r in records if r["Date"] == target_date]

    # 5. Build hobli → mm_per_tick mapping
    TICK_SCALE = 1 / (24 * 12)
    rainfall_snapshot = {}
    for r in date_records:
        hobli = r.get("Hobli", "unknown")
        mm_24h = float(r.get("24h_Actual_mm", 0))
        mm_per_tick = mm_24h * TICK_SCALE
        rainfall_snapshot[hobli] = mm_per_tick

    # If no data or intensity is 'heavy'/'extreme', use synthetic rainfall for realistic flooding
    if not rainfall_snapshot or intensity in ("heavy", "extreme"):
        # Generate synthetic heavy rainfall based on intensity
        synthetic_mm_24h = 45.0 if intensity == "heavy" else 100.0 if intensity == "extreme" else 30.0
        synthetic_mm_per_tick = synthetic_mm_24h * TICK_SCALE
        rainfall_snapshot = {
            "Indiranagar": synthetic_mm_per_tick * 1.2,
            "Domlur": synthetic_mm_per_tick * 1.1,
            "KR Market": synthetic_mm_per_tick * 0.9,
            "Ulsoor": synthetic_mm_per_tick * 1.0,
            "Koramangala": synthetic_mm_per_tick * 1.3,
            "Whitefield": synthetic_mm_per_tick * 0.8,
            "unknown": synthetic_mm_per_tick,
        }
        logger.info(f"[PICK SCENARIO] Using synthetic {intensity} rainfall: {synthetic_mm_24h}mm/24h")

    if not rainfall_snapshot:
        rainfall_snapshot = {"fallback": 10.0 * TICK_SCALE}

    return rainfall_snapshot, target_date, month


def scenario_to_flood_input(rainfall_snapshot: Dict[str, float], tick_mins: float) -> Dict[str, float]:
    """Convert mm/tick to mm/hour for flood physics input."""
    ticks_per_hour = 60.0 / tick_mins
    return {
        hobli: mm_per_tick * ticks_per_hour
        for hobli, mm_per_tick in rainfall_snapshot.items()
    }


def evolve_rainfall(
    current_snapshot: Dict[str, float],
    hobli_coords: Dict[str, Tuple[float, float]],
    tick: int,
    mode: str = "random",
    session: Optional['SimulationSession'] = None
) -> Dict[str, float]:
    """Evolve rainfall by one tick according to mode.
    
    For 'move' mode, the storm cell physically moves across regions.
    Rainfall increases in regions the storm enters and decreases in
    regions it leaves — total rainfall energy is conserved.
    """
    new_snapshot = {}

    old_avg = sum(current_snapshot.values()) / max(len(current_snapshot), 1)

    if mode == "intensify":
        for hobli, mm in current_snapshot.items():
            # Cap at 0.8 mm/tick (~230 mm/24h) to avoid unrealistic 3m floods
            new_snapshot[hobli] = min(mm * 1.05, 0.8)

    elif mode == "dissipate":
        for hobli, mm in current_snapshot.items():
            new_snapshot[hobli] = max(mm * 0.92, 0.0)

    elif mode == "move":
        new_snapshot = _evolve_move_mode(current_snapshot, hobli_coords, tick, session)

    elif mode == "random":
        for hobli, mm in current_snapshot.items():
            factor = random.gauss(1.0, 0.15)
            new_snapshot[hobli] = max(0, mm * factor)

    else:
        new_snapshot = dict(current_snapshot)

    new_avg = sum(new_snapshot.values()) / max(len(new_snapshot), 1)
    logger.info(
        f"[EVOLVE RAINFALL] tick={tick} mode={mode} | "
        f"avg_mm_tick: {old_avg:.6f} → {new_avg:.6f} (Δ={new_avg - old_avg:+.6f}) | "
        f"hoblis={len(new_snapshot)}"
    )

    return new_snapshot


def _evolve_move_mode(
    current_snapshot: Dict[str, float],
    hobli_coords: Dict[str, Tuple[float, float]],
    tick: int,
    session: Optional['SimulationSession'] = None
) -> Dict[str, float]:
    """Move a storm cell across regions so rainfall shifts geographically.
    
    The storm center is tracked explicitly (not re-derived from decayed values)
    and total rainfall energy is conserved. When the storm enters a new region
    that region's rainfall increases; when it leaves, rainfall there decreases.
    """
    # ── 1. Initialize storm parameters on first call ──
    if session is not None and session.storm_center is not None:
        storm_center = session.storm_center
        total_rain = session.storm_total_rain
        storm_radius = session.storm_radius_m
    else:
        # First tick: compute initial storm center from rainfall-weighted centroid
        storm_center = _compute_storm_center(current_snapshot, hobli_coords)
        total_rain = sum(current_snapshot.values())
        storm_radius = 8000.0
        if storm_center is None:
            return dict(current_snapshot)

    # ── 2. Move the storm center ──
    # Storm drifts at ~0.001° per tick ≈ ~100m per tick
    # Direction: predominantly NE with slight random jitter for realism
    base_dlat = 0.001
    base_dlon = 0.001
    jitter_lat = random.gauss(0, 0.0003)
    jitter_lon = random.gauss(0, 0.0003)
    new_center = (
        storm_center[0] + base_dlat + jitter_lat,
        storm_center[1] + base_dlon + jitter_lon,
    )

    # ── 3. Recompute rainfall for each hobli based on distance to new storm center ──
    # Use a Gaussian-like falloff so the storm has a smooth bell-curve shape
    raw_intensities = {}
    total_intensity = 0.0

    for hobli in current_snapshot.keys():
        if hobli in hobli_coords:
            hlat, hlon = hobli_coords[hobli]
            dist = _haversine_dist(hlat, hlon, new_center[0], new_center[1])
            # Gaussian falloff: intensity = exp(-(dist/sigma)^2)
            # sigma = storm_radius / 2 gives a nice bell shape within the radius
            sigma = storm_radius / 2.0
            intensity = exp(-((dist / sigma) ** 2))
        else:
            # Hobli not in coords — give it a small baseline
            intensity = 0.01

        raw_intensities[hobli] = intensity
        total_intensity += intensity

    # ── 4. Distribute total rainfall energy proportionally ──
    # This conserves the total rain so the storm moves rather than dissipates
    new_snapshot = {}
    if total_intensity > 0:
        for hobli, raw_i in raw_intensities.items():
            fraction = raw_i / total_intensity
            new_snapshot[hobli] = min(fraction * total_rain, 0.8)  # cap per-hobli
    else:
        new_snapshot = dict(current_snapshot)

    # ── 5. Persist storm state in session for next tick ──
    if session is not None:
        session.storm_center = new_center
        session.storm_total_rain = total_rain  # conserved
        session.storm_radius_m = storm_radius

    # Log the storm movement
    logger.info(
        f"[MOVE MODE] Storm center: ({new_center[0]:.4f}, {new_center[1]:.4f}) | "
        f"total_rain={total_rain:.4f}mm/tick | radius={storm_radius:.0f}m | "
        f"hoblis_affected={sum(1 for v in new_snapshot.values() if v > 0.001)}"
    )

    return new_snapshot


def _compute_storm_center(
    snapshot: Dict[str, float],
    hobli_coords: Dict[str, Tuple[float, float]]
) -> Optional[Tuple[float, float]]:
    """Weighted centroid of rainfall intensity."""
    total_rain = sum(snapshot.values())
    if total_rain == 0:
        return None
    lat = sum(
        hobli_coords[h][0] * mm for h, mm in snapshot.items() if h in hobli_coords
    ) / total_rain
    lon = sum(
        hobli_coords[h][1] * mm for h, mm in snapshot.items() if h in hobli_coords
    ) / total_rain
    return lat, lon


def _haversine_dist(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371000 * 2 * atan2(sqrt(a), sqrt(1 - a))


def should_reroute(
    old_snapshot: Dict[str, float],
    new_snapshot: Dict[str, float],
    active_hoblis: List[str],
    threshold_mm: float = 0.0005
) -> Tuple[bool, Optional[str]]:
    """Check if rainfall changed enough to trigger flood recomputation.
    
    The threshold is in mm/tick units. For heavy rain at ~0.03 mm/tick,
    intensify mode changes by 5% per tick = ~0.0015 mm/tick delta.
    Default 0.0005 catches all meaningful changes.
    """
    max_delta = 0.0
    max_hobli = None
    for hobli in active_hoblis:
        old = old_snapshot.get(hobli, 0)
        new = new_snapshot.get(hobli, 0)
        delta = abs(new - old)
        if delta > max_delta:
            max_delta = delta
            max_hobli = hobli
    
    triggered = max_delta >= threshold_mm
    if triggered:
        logger.info(
            f"[SHOULD_REROUTE] YES — hobli='{max_hobli}' delta={max_delta:.6f}mm/tick "
            f"(threshold={threshold_mm})"
        )
    else:
        logger.debug(
            f"[SHOULD_REROUTE] NO — max_delta={max_delta:.6f}mm/tick "
            f"(threshold={threshold_mm})"
        )
    return triggered, max_hobli


def build_rainfall_heatmap(
    rainfall_snapshot: Dict[str, float],
    hobli_coords: Dict[str, Tuple[float, float]],
    max_rainfall_mm: float = 5.0
) -> List[Dict]:
    """
    Build list of hobli points with normalized intensity for heatmap rendering.
    Returns list of { lat, lon, intensity, hobli }.
    """
    heatmap = []
    for hobli, mm in rainfall_snapshot.items():
        if hobli in hobli_coords:
            lat, lon = hobli_coords[hobli]
            intensity = min(mm / max_rainfall_mm, 1.0)  # normalize 0–1
            heatmap.append({
                "lat": lat,
                "lon": lon,
                "intensity": intensity,
                "hobli": hobli
            })
    return heatmap


def get_rainfall_stats(all_records: List[Dict]) -> Dict:
    """Compute statistics on historical rainfall."""
    mm_values = []
    hobli_maxes = {}
    for r in all_records:
        mm = float(r.get("24h_Actual_mm", 0))
        mm_values.append(mm)
        hobli = r.get("Hobli", "unknown")
        if hobli not in hobli_maxes:
            hobli_maxes[hobli] = 0
        hobli_maxes[hobli] = max(hobli_maxes[hobli], mm)

    return {
        "max_24h_mm": max(mm_values) if mm_values else 0,
        "avg_24h_mm": sum(mm_values) / len(mm_values) if mm_values else 0,
        "hobli_maxes": hobli_maxes
    }


def cleanup_stale_sessions():
    """Remove sessions older than MAX_AGE."""
    import time
    now = time.time()
    stale = [
        sid for sid, sess in SIMULATE_SESSIONS.items()
        if (now - sess.last_accessed) > SESSION_MAX_AGE_SECONDS
    ]
    for sid in stale:
        del SIMULATE_SESSIONS[sid]
