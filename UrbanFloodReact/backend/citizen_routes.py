"""
FastAPI APIRouter for all citizen-facing endpoints.
Mounted in main.py: app.include_router(citizen_router)
"""
from fastapi import APIRouter
from pydantic import BaseModel
import uuid
import time
import asyncio
import httpx
import logging

from geo_db import fetch_corridor, find_nearest_node
from corridor_graph import build_graph, snap_to_node
from rainfall_service import fetch_rainfall, assign_wards_to_nodes
from corridor_flood import compute_flood
from astar_router import astar_route, build_route_geojson, generate_steps, route_summary
from shelter_integration import get_shelter_candidates, rank_shelters_by_distance
from realtime_traffic_service import get_route_traffic_eta, embed_live_traffic_in_path

logger = logging.getLogger(__name__)


citizen_router = APIRouter(prefix="/citizen", tags=["citizen"])


class CitizenRouteRequest(BaseModel):
    src_lat: float
    src_lon: float
    dst_lat: float
    dst_lon: float


class CitizenShelterRequest(BaseModel):
    src_lat: float
    src_lon: float


class GeocodeRequest(BaseModel):
    query: str
    near_lat: float = 12.9716
    near_lon: float = 77.5946


class LocationUpdate(BaseModel):
    session_id: str
    current_lat: float
    current_lon: float
    dst_lat: float
    dst_lon: float
    active_ward_rainfall: dict


async def _compute_route(src_lat, src_lon, dst_lat, dst_lon, include_street_names: bool = True):
    """
    Shared pipeline for both routing modes.
    Returns full response dict or raises ValueError on no-path.

    Args:
        src_lat, src_lon, dst_lat, dst_lon: Route endpoints
        include_street_names: If True, enrich steps with OSM street names

    Raises:
        ValueError on routing failure
    """
    logger.info(f"[CITIZEN ROUTE] Computing route: src=({src_lat}, {src_lon}), dst=({dst_lat}, {dst_lon})")

    edges, nodes, _ = await fetch_corridor(src_lat, src_lon, dst_lat, dst_lon)
    if edges is None or (isinstance(edges, list) and len(edges) == 0):
        logger.error("[CITIZEN ROUTE] No road data found for corridor")
        raise ValueError("No road data found for this corridor.")
    logger.info(f"[CITIZEN ROUTE] Corridor loaded: {len(edges)} edges, {len(nodes)} nodes")

    logger.debug("[CITIZEN ROUTE] Building graph...")
    G = build_graph(edges, nodes)
    logger.debug(f"[CITIZEN ROUTE] Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    logger.debug("[CITIZEN ROUTE] Snapping coordinates...")
    src_node = snap_to_node(G, src_lat, src_lon)
    dst_node = snap_to_node(G, dst_lat, dst_lon)
    if src_node is None or dst_node is None:
        logger.error(f"[CITIZEN ROUTE] Snap failed: src_node={src_node}, dst_node={dst_node}")
        raise ValueError("Could not snap coordinates to road network.")
    logger.debug(f"[CITIZEN ROUTE] Snapped: src={src_node}, dst={dst_node}")

    logger.debug("[CITIZEN ROUTE] Fetching rainfall data...")
    rainfall_mm, ward_centroids = await fetch_rainfall()
    logger.debug(f"[CITIZEN ROUTE] Rainfall: {len(rainfall_mm)} wards, {len(ward_centroids)} centroids")

    node_coords = {n: (G.nodes[n]["lat"], G.nodes[n]["lon"]) for n in G.nodes}
    ward_for_node = assign_wards_to_nodes(list(G.nodes), node_coords, ward_centroids)

    logger.debug("[CITIZEN ROUTE] Computing flood physics...")
    G = compute_flood(G, rainfall_mm, ward_for_node)

    logger.info("[CITIZEN ROUTE] Computing A* route...")
    path = astar_route(G, src_node, dst_node)
    if path is None:
        logger.error("[CITIZEN ROUTE] No passable route found (all paths flooded)")
        raise ValueError("No passable route — all paths are flooded.")
    logger.info(f"[CITIZEN ROUTE] Route found: {len(path)} nodes")

    # NEW: Fetch live traffic data ONLY for the actual path (not entire corridor)
    logger.info("[CITIZEN ROUTE] Fetching live TomTom traffic data for routing...")
    try:
        updated = await embed_live_traffic_in_path(G, path)
        logger.info(f"[CITIZEN ROUTE] Traffic data embedded into {updated} edges in path")
    except Exception as e:
        logger.exception("[CITIZEN ROUTE] Traffic data fetch failed. Using base speeds.")

    # Street names are already in the graph from MongoDB (populated during setup)
    # The generate_steps() function will use them directly from edge data
    logger.debug("[CITIZEN ROUTE] Using street names from MongoDB")

    summary = route_summary(G, path)
    active_wards = list({ward_for_node.get(n, "unknown") for n in path})
    active_ward_rainfall = {w: rainfall_mm.get(w, 0.0) for w in active_wards}

    # Compute live ETA post-routing (now accounting for traffic-aware A*)
    logger.info("[CITIZEN ROUTE] Computing final ETA with traffic...")
    traffic_eta_data = await get_route_traffic_eta(G, path, speed_mode="car")
    live_eta_minutes = traffic_eta_data.get("eta_minutes", summary["eta_minutes"])
    logger.info(f"[CITIZEN ROUTE] Live traffic ETA: {live_eta_minutes} min (vs base: {summary['eta_minutes']} min)")

    return {
        "status": "ok",
        "session_id": str(uuid.uuid4()),
        "route_geojson": build_route_geojson(G, path),
        "steps": generate_steps(G, path),
        "total_distance_m": summary["total_distance_m"],
        "eta_minutes": live_eta_minutes,  # Use live traffic ETA
        "eta_minutes_base": summary["eta_minutes"],  # Keep base for reference
        "max_flood_depth_m": summary["max_flood_depth_m"],
        "flooded_segments": summary["flooded_segments"],
        "safe": summary["safe"],
        "warning": None if summary["safe"] else "Route passes through flooded areas.",
        "active_ward_rainfall": active_ward_rainfall,
        "traffic_info": traffic_eta_data,  # Include detailed traffic breakdown
    }


@citizen_router.post("/route")
async def citizen_route(req: CitizenRouteRequest):
    """Mode A: GPS → user-specified destination."""
    logger.info("[CITIZEN /ROUTE] New route request")
    logger.debug(f"[CITIZEN /ROUTE] Params: src=({req.src_lat}, {req.src_lon}), dst=({req.dst_lat}, {req.dst_lon})")
    try:
        result = await _compute_route(req.src_lat, req.src_lon, req.dst_lat, req.dst_lon)
        logger.info("[CITIZEN /ROUTE] Route computed successfully")
        return result
    except ValueError as e:
        logger.error(f"[CITIZEN /ROUTE] Route computation failed: {str(e)}")
        return {"status": "error", "message": str(e), "route_geojson": None, "steps": []}


@citizen_router.post("/nearest-shelter")
async def citizen_nearest_shelter(req: CitizenShelterRequest):
    """
    Mode B: GPS → nearest safe shelter.
    Uses real OSM shelters (schools, hospitals, community centres).
    Ranks by distance, filters by routability and flood safety.
    """
    logger.info("[CITIZEN /NEAREST-SHELTER] Nearest shelter request")
    logger.debug(f"[CITIZEN /NEAREST-SHELTER] Location: ({req.src_lat}, {req.src_lon})")
    
    edges, nodes, _ = await fetch_corridor(req.src_lat - 0.025, req.src_lon - 0.025, req.src_lat + 0.025, req.src_lon + 0.025)
    if edges is None or (isinstance(edges, list) and len(edges) == 0):
        logger.error("[CITIZEN /NEAREST-SHELTER] No road data found")
        return {
            "status": "error",
            "message": "No road data found. Cannot search shelters.",
            "route_geojson": None,
            "steps": []
        }

    G = build_graph(edges, nodes)
    logger.debug(f"[CITIZEN /NEAREST-SHELTER] Graph built: {G.number_of_nodes()} nodes")

    # Estimate hobli for shelter_generator cache lookup (rough grid)
    hobli_key = f"cell_{int(req.src_lat * 10)}_{int(req.src_lon * 10)}"

    logger.debug(f"[CITIZEN /NEAREST-SHELTER] Searching shelters with hobli_key={hobli_key}")
    shelters = get_shelter_candidates(
        G, req.src_lat, req.src_lon, hobli_key=hobli_key, dist_m=5000
    )

    if shelters is None or (isinstance(shelters, list) and len(shelters) == 0):
        logger.error("[CITIZEN /NEAREST-SHELTER] No shelters found nearby")
        return {
            "status": "error",
            "message": "No shelters found nearby. Stay in place and call 112.",
            "route_geojson": None,
            "steps": []
        }
    logger.info(f"[CITIZEN /NEAREST-SHELTER] Found {len(shelters)} shelters")

    # Rank by distance
    shelters = rank_shelters_by_distance(shelters, req.src_lat, req.src_lon)
    logger.debug("[CITIZEN /NEAREST-SHELTER] Shelters ranked by distance")

    # Try each shelter until we find a safe route
    logger.info(f"[CITIZEN /NEAREST-SHELTER] Testing {len(shelters)} shelters for safe routes...")
    for idx, shelter in enumerate(shelters):
        logger.debug(f"[CITIZEN /NEAREST-SHELTER] Testing shelter {idx+1}/{len(shelters)}: {shelter['name']}")
        try:
            result = await _compute_route(
                req.src_lat, req.src_lon,
                shelter["lat"], shelter["lon"]
            )
            if result.get("status") == "ok" and result.get("safe"):
                logger.info(f"[CITIZEN /NEAREST-SHELTER] SAFE ROUTE FOUND to {shelter['name']}")
                result["shelter"] = {
                    "name": shelter["name"],
                    "type": shelter["type"],
                    "lat": shelter["lat"],
                    "lon": shelter["lon"],
                    "capacity_persons": shelter.get("capacity_persons", 0),
                    "elevation_m": shelter.get("elevation_m", 0),
                    "osm_id": shelter.get("osm_id"),
                }
                return result
            else:
                logger.debug(f"[CITIZEN /NEAREST-SHELTER] Shelter {shelter['name']} unsafe or no status")
        except ValueError as e:
            logger.debug(f"[CITIZEN /NEAREST-SHELTER] Shelter {shelter['name']} routing failed: {str(e)}")
            continue

    logger.error("[CITIZEN /NEAREST-SHELTER] No safe shelter route found")
    return {
        "status": "error",
        "message": "No safe shelter route found. Stay in place and call 112.",
        "route_geojson": None,
        "steps": []
    }


_nominatim_last = 0.0
_nominatim_lock = asyncio.Lock()


@citizen_router.post("/geocode")
async def citizen_geocode(req: GeocodeRequest):
    """Server-side Nominatim proxy. Enforces 1 req/sec. Returns top 5 results."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = 1.0 - (time.time() - _nominatim_last)
        if wait > 0:
            await asyncio.sleep(wait)
        _nominatim_last = time.time()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": req.query,
                        "format": "json",
                        "limit": 5,
                        "countrycodes": "in",
                        "viewbox": (
                            f"{req.near_lon - 0.5},{req.near_lat + 0.5},"
                            f"{req.near_lon + 0.5},{req.near_lat - 0.5}"
                        ),
                        "bounded": 1,
                    },
                    headers={"User-Agent": "UrbanFloodEvacSystem/1.0"},
                )
            return [
                {
                    "display_name": r["display_name"],
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"])
                }
                for r in resp.json()[:5]
            ]
        except Exception:
            return []


@citizen_router.post("/location-update")
async def citizen_location_update(req: LocationUpdate):
    """
    30-second heartbeat during navigation.
    Checks if rainfall has changed in active wards or user entered new ward.
    Triggers full reroute if needed.
    """
    fresh_mm, ward_centroids = await fetch_rainfall()

    changed = any(
        abs(fresh_mm.get(ward, 0.0) - old_mm) > 10.0
        for ward, old_mm in req.active_ward_rainfall.items()
    )

    if ward_centroids is not None and len(ward_centroids) > 0 and not changed:
        from rainfall_service import assign_wards_to_nodes
        current_ward = assign_wards_to_nodes(
            ["current"],
            {"current": (req.current_lat, req.current_lon)},
            ward_centroids
        ).get("current")
        if current_ward and current_ward not in req.active_ward_rainfall:
            changed = True

    if not changed:
        return {"reroute_needed": False}

    try:
        new_route = await _compute_route(
            req.current_lat, req.current_lon,
            req.dst_lat, req.dst_lon
        )
        return {
            "reroute_needed": True,
            "reason": "Flood conditions changed in your area.",
            "new_route": new_route,
        }
    except ValueError as e:
        return {
            "reroute_needed": True,
            "reason": str(e),
            "new_route": None,
        }
