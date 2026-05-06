"""
Shelter integration for citizen routing.
Wraps shelter_generator.py to provide real OSM shelter candidates for evacuation.
"""
import logging
from typing import List, Dict, Tuple
import networkx as nx

try:
    from shelter_generator import extract_shelter_candidates
except ImportError:
    extract_shelter_candidates = None

logger = logging.getLogger(__name__)


def get_shelter_candidates(
    G: nx.DiGraph,
    src_lat: float,
    src_lon: float,
    hobli_key: str,
    dist_m: int = 5000
) -> List[Dict]:
    """
    Get real shelter candidates from OSM via shelter_generator.

    Returns list of shelters with:
    - name: str (school name, hospital name, etc.)
    - type: str (school | hospital | community_centre | townhall | police | fire_station)
    - lat, lon: float (shelter location)
    - capacity_persons: int (estimated)
    - elevation_m: float (if available)

    Falls back to empty list if shelter_generator is unavailable.

    Args:
        G: NetworkX DiGraph (corridor graph, used for node attachment)
        src_lat, src_lon: Source location (search center)
        hobli_key: Hobli name for cache lookup
        dist_m: Search radius in metres

    Returns:
        List of shelter dicts, or empty list on error
    """
    if extract_shelter_candidates is None:
        logger.warning("shelter_generator not available. Returning empty shelter list.")
        return []

    try:
        candidates = extract_shelter_candidates(
            G=G,
            lat=src_lat,
            lon=src_lon,
            hobli_key=hobli_key,
            dist=dist_m
        )

        # Normalize to citizen-friendly format
        shelters = []
        for c in candidates:
            shelter = {
                "name": c.get("name", "Shelter"),
                "type": c.get("amenity", c.get("building", "shelter")),
                "lat": c.get("y", c.get("lat", src_lat)),
                "lon": c.get("x", c.get("lon", src_lon)),
                "capacity_persons": c.get("capacity", 100),
                "elevation_m": c.get("elevation", 0),
                "osm_id": c.get("osmid"),
            }
            shelters.append(shelter)

        logger.info(f"Found {len(shelters)} shelter candidates near ({src_lat:.4f}, {src_lon:.4f})")
        return shelters

    except Exception as e:
        logger.error(f"Shelter candidate extraction failed: {e}", exc_info=True)
        return []


def filter_shelters_by_flood_safety(
    shelters: List[Dict],
    flooded_areas: Dict[str, float]  # { shelter_name: max_depth }
) -> List[Dict]:
    """
    Filter shelters that are in flooded areas (depth > 0.5m).

    Args:
        shelters: From get_shelter_candidates()
        flooded_areas: Dict mapping shelter names to max flood depth

    Returns:
        Filtered list of safe shelters
    """
    safe = [s for s in shelters if flooded_areas.get(s["name"], 0) < 0.5]
    logger.info(f"Filtered to {len(safe)} / {len(shelters)} safe shelters")
    return safe


def rank_shelters_by_distance(
    shelters: List[Dict],
    src_lat: float,
    src_lon: float
) -> List[Dict]:
    """
    Rank shelters by distance from source (closest first).

    Args:
        shelters: From filter_shelters_by_flood_safety()
        src_lat, src_lon: Source location

    Returns:
        Shelters sorted by distance (closest first)
    """
    from math import radians, cos, sin, sqrt, atan2

    def haversine(lat1, lon1, lat2, lon2):
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return 6371000 * 2 * atan2(sqrt(a), sqrt(1 - a))

    ranked = sorted(
        shelters,
        key=lambda s: haversine(src_lat, src_lon, s["lat"], s["lon"])
    )
    return ranked
