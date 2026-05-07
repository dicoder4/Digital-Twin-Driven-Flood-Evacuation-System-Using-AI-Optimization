"""
Rainfall simulation, person movement, and session management for the simulate-citizen feature.
Provides scenario picking, rainfall evolution, and person pathfinding.
"""
import random
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from math import radians, cos, sin, sqrt, atan2
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
    mode: str = "random"
) -> Dict[str, float]:
    """Evolve rainfall by one tick according to mode."""
    new_snapshot = {}

    if mode == "intensify":
        for hobli, mm in current_snapshot.items():
            # Cap at 0.8 mm/tick (~230 mm/24h) to avoid unrealistic 3m floods
            new_snapshot[hobli] = min(mm * 1.05, 0.8)

    elif mode == "dissipate":
        for hobli, mm in current_snapshot.items():
            new_snapshot[hobli] = max(mm * 0.92, 0.0)

    elif mode == "move":
        storm_center = _compute_storm_center(current_snapshot, hobli_coords)
        if storm_center:
            # Move the storm center NE at a constant rate (~100m per tick)
            move_lat = 0.001
            move_lon = 0.001
            new_center = (storm_center[0] + move_lat, storm_center[1] + move_lon)
            
            # Find the peak rainfall to maintain storm intensity without exploding
            max_rain = max(current_snapshot.values()) if current_snapshot else 0.3
            max_rain = max(0.1, min(max_rain, 0.8))  # clamp to reasonable bounds
            
            for hobli, (hlat, hlon) in hobli_coords.items():
                dist_to_new = _haversine_dist(hlat, hlon, *new_center)
                # 8km radius for the storm cell
                intensity = max(0.0, 1.0 - dist_to_new / 8000.0)
                target_rain = intensity * max_rain
                
                base = current_snapshot.get(hobli, 0)
                # Smooth transition towards the moving storm center
                new_snapshot[hobli] = base * 0.8 + target_rain * 0.2
        else:
            new_snapshot = dict(current_snapshot)

    elif mode == "random":
        for hobli, mm in current_snapshot.items():
            factor = random.gauss(1.0, 0.15)
            new_snapshot[hobli] = max(0, mm * factor)

    else:
        new_snapshot = dict(current_snapshot)

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
    threshold_mm: float = 0.5
) -> Tuple[bool, Optional[str]]:
    """Check if rainfall changed enough to trigger reroute."""
    for hobli in active_hoblis:
        old = old_snapshot.get(hobli, 0)
        new = new_snapshot.get(hobli, 0)
        if abs(new - old) >= threshold_mm:
            return True, hobli
    return False, None


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
