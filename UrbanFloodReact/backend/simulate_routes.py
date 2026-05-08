"""
FastAPI endpoints for the Simulate Citizen feature.
Allows testing flood routing with historical rainfall scenarios.
"""
from fastapi import APIRouter
from pydantic import BaseModel
import uuid
import time
import logging

from geo_db import fetch_corridor
from corridor_graph import build_graph, snap_to_node
from corridor_flood import compute_flood
from astar_router import astar_route, build_route_geojson, generate_steps, route_summary
from simulation_engine import (
    fetch_hobli_coords,
    assign_hoblis_to_nodes,
    pick_scenario,
    scenario_to_flood_input,
    evolve_rainfall,
    should_reroute,
    PersonPosition,
    SimulationSession,
    SIMULATE_SESSIONS,
    build_rainfall_heatmap,
    cleanup_stale_sessions,
    get_rainfall_stats,
)
from db import _get_db

logger = logging.getLogger(__name__)


simulate_router = APIRouter(prefix="/simulate", tags=["simulate"])


class SimulateStartRequest(BaseModel):
    src_lat: float
    src_lon: float
    dst_lat: float
    dst_lon: float
    speed_mode: str = "car"
    intensity: str = "random"
    month: str | None = None
    evolution_mode: str = "random"
    tick_mins: float = 5.0
    mode: str = "simulated"  # "simulated" or "realtime"
    rainfall_source: str = "simulated"  # "simulated" or "ksndmc"


class SimulateTickRequest(BaseModel):
    session_id: str
    current_lat: float | None = None
    current_lon: float | None = None


class SimulateResetRequest(BaseModel):
    session_id: str


SPEED_MAP = {
    "car": 30,      # Car: 30 km/h (realistic urban speed with traffic)
    "bike": 15,     # Bike: 15 km/h (cycling speed)
    "walk": 4,      # Walk: 4 km/h (normal walking pace)
}

IMPASSABLE_DEPTH_MAP = {
    "car": 0.25,      # Lowered to 0.25m for stricter car rerouting
    "bike": 0.15,     # 0.15m max for bikes
    "walk": 0.5,      # 0.5m max for walking (knee/waist deep)
    "emergency": 1.0  # High clearance vehicles
}


def calculate_eta_minutes(distance_m: float, speed_kph: float) -> int:
    """
    Calculate ETA in minutes based on distance and speed.

    Args:
        distance_m: Distance in meters
        speed_kph: Speed in kilometers per hour

    Returns:
        ETA in minutes (rounded)
    """
    if speed_kph <= 0:
        return 0
    distance_km = distance_m / 1000.0
    time_hours = distance_km / speed_kph
    time_minutes = time_hours * 60
    return round(time_minutes)


@simulate_router.post("/start")
async def simulate_start(req: SimulateStartRequest):
    """Start a new simulation session."""
    logger.info("[SIMULATE START] Initializing new simulation session")
    logger.debug(f"[SIMULATE START] Request params: src=({req.src_lat}, {req.src_lon}), dst=({req.dst_lat}, {req.dst_lon})")
    logger.debug(f"[SIMULATE START] Config: speed_mode={req.speed_mode}, intensity={req.intensity}, month={req.month}, evolution={req.evolution_mode}")
    
    cleanup_stale_sessions()
    logger.debug(f"[SIMULATE START] Cleaned up stale sessions. Active sessions: {len(SIMULATE_SESSIONS)}")

    try:
        # 1. Fetch corridor
        logger.info("[SIMULATE START] Step 1: Fetching corridor data...")
        edges, nodes, _ = await fetch_corridor(
            req.src_lat, req.src_lon, req.dst_lat, req.dst_lon, buffer_km=2.0
        )
        if edges is None or (isinstance(edges, list) and len(edges) == 0):
            logger.error("[SIMULATE START] No road data found for corridor")
            return {"status": "error", "message": "No road data found for this corridor."}
        logger.info(f"[SIMULATE START] Corridor fetched: {len(edges)} edges, {len(nodes)} nodes")

        # 2. Build graph
        logger.info("[SIMULATE START] Step 2: Building NetworkX graph...")
        G = build_graph(edges, nodes)
        logger.info(f"[SIMULATE START] Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        # 3. Snap src/dst
        logger.info("[SIMULATE START] Step 3: Snapping coordinates to road network...")
        src_node = snap_to_node(G, req.src_lat, req.src_lon)
        dst_node = snap_to_node(G, req.dst_lat, req.dst_lon)
        if src_node is None or dst_node is None:
            logger.error(f"[SIMULATE START] Could not snap coordinates. src_node={src_node}, dst_node={dst_node}")
            return {"status": "error", "message": "Could not snap coordinates to road network."}
        logger.info(f"[SIMULATE START] Snapped: src_node={src_node}, dst_node={dst_node}")

        # 4. Fetch hobli coords
        logger.info("[SIMULATE START] Step 4: Fetching hobli coordinates...")
        hobli_coords = await fetch_hobli_coords()
        if hobli_coords is None or (isinstance(hobli_coords, dict) and len(hobli_coords) == 0):
            logger.error("[SIMULATE START] Hobli data not available")
            return {"status": "error", "message": "Hobli data not available."}
        logger.info(f"[SIMULATE START] Hobli coords loaded: {len(hobli_coords)} hoblis")

        # 5. Pick rainfall scenario or fetch live rainfall
        rainfall_snapshot = {}
        scenario_date = "live"
        scenario_month = "live"

        if req.mode == "realtime" and req.rainfall_source == "ksndmc":
            logger.info("[SIMULATE START] Step 5: Fetching live KSNDMC rainfall...")
            from rainfall_service import fetch_rainfall, assign_wards_to_nodes
            rainfall_mm, ward_centroids = await fetch_rainfall()
            
            # Use ward_for_node instead of hobli_for_node for KSNDMC data
            ward_for_node = assign_wards_to_nodes(
                list(G.nodes()), 
                {n: (G.nodes[n]['lat'], G.nodes[n]['lon']) for n in G.nodes()}, 
                ward_centroids
            )
            # KSNDMC rain values are used as mm/hour as per user feedback
            rainfall_snapshot = rainfall_mm
            hobli_for_node = ward_for_node # Re-assign for compute_flood
            logger.info(f"[SIMULATE START] Live rainfall fetched for {len(rainfall_snapshot)} wards")
        else:
            logger.info(f"[SIMULATE START] Step 5: Picking rainfall scenario (month={req.month}, intensity={req.intensity})...")
            rainfall_snapshot, scenario_date, scenario_month = await pick_scenario(req.month, req.intensity)
            logger.info(f"[SIMULATE START] Scenario selected: date={scenario_date}, month={scenario_month}, hoblis={len(rainfall_snapshot)}")
        logger.debug(f"[SIMULATE START] Rainfall snapshot: {rainfall_snapshot}")

        # 6. Assign hoblis to nodes
        logger.info("[SIMULATE START] Step 6: Assigning hoblis to nodes...")
        hobli_for_node = assign_hoblis_to_nodes(G, hobli_coords)
        logger.info(f"[SIMULATE START] Hoblis assigned to {len(hobli_for_node)} nodes")

        # 6.5 Bridge rainfall keys → actual hobli names
        # The rainfall_snapshot keys (from CSV "Hobli" column or synthetic names)
        # often don't match the hobli_coords keys used by assign_hoblis_to_nodes.
        # We remap: for each actual hobli used by nodes, find the nearest rainfall
        # source point and assign its value. This ensures compute_flood gets data.
        actual_hoblis_used = set(hobli_for_node.values())
        rainfall_keys_match = actual_hoblis_used & set(rainfall_snapshot.keys())

        if len(rainfall_keys_match) < len(actual_hoblis_used) * 0.5:
            # Most hoblis don't match → need to remap
            logger.info(f"[SIMULATE START] Rainfall key mismatch: {len(rainfall_keys_match)}/{len(actual_hoblis_used)} hoblis matched. Remapping...")

            # Compute average rainfall from snapshot as baseline
            rain_values = [v for v in rainfall_snapshot.values() if v > 0]
            avg_rain = sum(rain_values) / len(rain_values) if rain_values else 0.0

            # For each actual hobli used by nodes, assign rainfall with spatial variation
            import random as _rng
            remapped_rainfall = {}
            for hobli_name in actual_hoblis_used:
                if hobli_name in rainfall_snapshot:
                    remapped_rainfall[hobli_name] = rainfall_snapshot[hobli_name]
                else:
                    # Apply random spatial variation (±30%) around the average
                    variation = _rng.uniform(0.7, 1.3)
                    remapped_rainfall[hobli_name] = avg_rain * variation

            rainfall_snapshot = remapped_rainfall
            logger.info(f"[SIMULATE START] Remapped rainfall to {len(remapped_rainfall)} actual hoblis (avg={avg_rain:.4f} mm/tick)")

        # 7. Compute flood with scenario rainfall (converted to mm/hour)
        logger.info("[SIMULATE START] Step 7: Computing flood physics with rainfall...")
        rainfall_mm_hour = scenario_to_flood_input(rainfall_snapshot, req.tick_mins)
        logger.debug("[SIMULATE START] Rainfall converted to mm/hour scale")
        # Log sample rainfall values for debugging
        sample_hoblis = list(rainfall_mm_hour.items())[:5]
        logger.info(f"[SIMULATE START] Rainfall mm/hour sample: {sample_hoblis}")
        G = compute_flood(G, rainfall_mm_hour, hobli_for_node)
        # Log max flood depth on the graph
        max_depth_on_graph = max((d.get("water_depth", 0) for _, _, d in G.edges(data=True)), default=0)
        flooded_edge_count = sum(1 for _, _, d in G.edges(data=True) if d.get("water_depth", 0) > 0.1)
        logger.info(f"[SIMULATE START] Flood physics computed: max_depth={max_depth_on_graph:.3f}m, flooded_edges={flooded_edge_count}/{G.number_of_edges()}")

        # 8. Create session ID early (needed for shelter evacuation response)
        session_id = str(uuid.uuid4())
        logger.info(f"[SIMULATE START] Session created: {session_id}")

        # 9. Route - Find primary and alternative paths
        logger.info("[SIMULATE START] Step 9: Computing A* route...")
        import networkx as nx
        from shelter_integration import get_shelter_candidates, rank_shelters_by_distance

        impassable_depth = IMPASSABLE_DEPTH_MAP.get(req.speed_mode, 0.25)
        
        # Check if a safe path exists first (to trigger shelter fallback if needed)
        safe_path = astar_route(G, src_node, dst_node, impassable_depth)
        
        if safe_path is None:
            logger.warning(f"[SIMULATE START] No passable route to destination. Finding safe shelters...")

            # Get current hobli for shelter lookup
            current_hobli = hobli_for_node.get(src_node, "unknown")
            shelters = get_shelter_candidates(G, req.src_lat, req.src_lon, current_hobli, dist_m=3000)

            if not shelters:
                logger.error("[SIMULATE START] No shelters found either. Emergency evacuation impossible.")
                return {"status": "error", "message": "No passable route found. No shelters available."}

            # Rank shelters by distance and try each one
            ranked_shelters = rank_shelters_by_distance(shelters, req.src_lat, req.src_lon)
            logger.info(f"[SIMULATE START] Found {len(ranked_shelters)} nearby shelters")

            # Try to route to nearest safe shelter
            best_shelter = None
            best_path = None

            for shelter in ranked_shelters[:5]:  # Try top 5 nearest shelters
                shelter_lat, shelter_lon = shelter['lat'], shelter['lon']
                shelter_node = snap_to_node(G, shelter_lat, shelter_lon)

                if shelter_node is None:
                    logger.warning(f"Could not snap shelter '{shelter['name']}' to road network")
                    continue

                shelter_path = astar_route(G, src_node, shelter_node, impassable_depth)
                if shelter_path is not None:
                    best_shelter = shelter
                    best_path = shelter_path
                    logger.info(f"[SIMULATE START] Found evacuation route to shelter: {shelter['name']}")
                    break

            if not best_path or not best_shelter:
                logger.error("[SIMULATE START] Cannot route to any shelter either")
                return {"status": "error", "message": "No passable route found. Cannot reach shelters."}

            # Return shelter evacuation response
            return {
                "status": "severe_flood",
                "message": "🌊 SEVERE FLOODING DETECTED - Direct route impossible",
                "alert": "Floods are severe in your area. Nearest safe shelter identified.",
                "shelter": {
                    "name": best_shelter.get("name", "Safe Shelter"),
                    "type": best_shelter.get("type", "shelter"),
                    "lat": best_shelter['lat'],
                    "lon": best_shelter['lon'],
                    "capacity": best_shelter.get("capacity_persons", 100),
                    "distance_m": sum(G[best_path[i]][best_path[i+1]]["length"] for i in range(len(best_path)-1)),
                },
                "alternative_shelters": ranked_shelters[1:4],
                "route_geojson": build_route_geojson(G, best_path),
                "session_id": session_id,
            }
        
        # A safe path exists! We start with the optimal flood-aware route immediately 
        # (Google Maps style). The simulation's 500m "radar" will still trigger a detour 
        # dynamically if the flood worsens and the route becomes impassable during the drive!
        path = safe_path

        logger.info(f"[SIMULATE START] Primary route found: {len(path)} nodes")

        # 9. Find alternative routes (FORCE minimum 2 alternatives)
        logger.info("[SIMULATE START] Step 9: Computing alternative routes...")
        alternative_paths = []
        seen_paths = {tuple(path)}  # Use tuple for hashable comparison

        def path_is_new(p):
            return tuple(p) not in seen_paths

        def add_path(p, strategy_name):
            if path_is_new(p):
                alternative_paths.append(p)
                seen_paths.add(tuple(p))
                logger.info(f"[SIMULATE START] {strategy_name}: Added alternative #{len(alternative_paths)} ({len(p)} nodes)")
                return True
            return False

        # Define flood-aware cost function (must match astar_router.py)
        def flood_aware_cost(u, v, data):
            depth = data.get("water_depth", 0.0)
            if depth >= impassable_depth:  # Dynamic impassable depth
                return float("inf")
            travel_min = (data["length"] / 1000.0) / data.get("speed_kph", 30) * 60.0
            # Flood penalty: prefer less flooded routes but don't block passable ones
            flood_penalty = (depth ** 2) * 5.0
            return travel_min + flood_penalty

        # Strategy 1: Use length-based K-shortest paths
        try:
            k_shortest_count = 0
            for i, alt_path in enumerate(nx.shortest_simple_paths(G, src_node, dst_node, weight='length')):
                k_shortest_count += 1
                if i >= 8:
                    break
                if len(alternative_paths) < 3 and add_path(alt_path, "Strategy 1"):
                    pass
            logger.info(f"[SIMULATE START] Strategy 1: Explored {k_shortest_count} length-based paths")
        except Exception as e:
            logger.warning(f"[SIMULATE START] Strategy 1 failed: {e}")

        # Strategy 1.5: Penalize primary route edges to force diverse alternatives
        if len(alternative_paths) < 3:
            logger.info("[SIMULATE START] Strategy 1.5: Computing diversity-penalized alternatives...")
            try:
                G_penalized = G.copy()
                primary_edges = set(zip(path[:-1], path[1:]))
                for u_e, v_e in primary_edges:
                    if G_penalized.has_edge(u_e, v_e):
                        G_penalized[u_e][v_e]["length"] = G_penalized[u_e][v_e]["length"] * 5.0
                pen_count = 0
                for i, alt_path in enumerate(nx.shortest_simple_paths(G_penalized, src_node, dst_node, weight='length')):
                    pen_count += 1
                    if i >= 6:
                        break
                    if len(alternative_paths) < 3 and add_path(alt_path, "Strategy 1.5"):
                        pass
                logger.info(f"[SIMULATE START] Strategy 1.5: Explored {pen_count} penalized paths")
            except Exception as e:
                logger.warning(f"[SIMULATE START] Strategy 1.5 failed: {e}")

        # Strategy 2: If < 2, try flood-aware K-shortest paths
        if len(alternative_paths) < 2:
            logger.info("[SIMULATE START] Strategy 2: Computing flood-aware K-shortest paths...")
            try:
                flood_k_count = 0
                for i, alt_path in enumerate(nx.shortest_simple_paths(G, src_node, dst_node, weight=flood_aware_cost)):
                    flood_k_count += 1
                    if i >= 8:
                        break
                    if len(alternative_paths) < 3 and add_path(alt_path, "Strategy 2"):
                        pass
                logger.info(f"[SIMULATE START] Strategy 2: Explored {flood_k_count} flood-aware paths")
            except Exception as e:
                logger.warning(f"[SIMULATE START] Strategy 2 failed: {e}")

        # Strategy 3: Waypoint-based routing through intermediate nodes
        if len(alternative_paths) < 2:
            logger.info("[SIMULATE START] Strategy 3: Creating waypoint-based alternatives...")
            try:
                all_nodes = list(G.nodes())
                path_set = set(path)
                attempts = 0

                for mid_node in all_nodes:
                    attempts += 1
                    if attempts > 150 or len(alternative_paths) >= 2:
                        break
                    if mid_node not in path_set and mid_node != src_node and mid_node != dst_node:
                        try:
                            alt1 = astar_route(G, src_node, mid_node, impassable_depth)
                            alt2 = astar_route(G, mid_node, dst_node, impassable_depth)
                            if alt1 and alt2:
                                alt_path = alt1[:-1] + alt2
                                if len(alternative_paths) < 3:
                                    add_path(alt_path, f"Strategy 3 (waypoint {mid_node})")
                        except Exception:
                            continue
                logger.info(f"[SIMULATE START] Strategy 3: Tried {attempts} waypoints")
            except Exception as e:
                logger.warning(f"[SIMULATE START] Strategy 3 failed: {e}")

        # Strategy 4: Random edge removal and reroute
        if len(alternative_paths) < 2:
            logger.info("[SIMULATE START] Strategy 4: Creating alternatives via edge removal...")
            try:
                import random
                for attempt in range(20):
                    if len(alternative_paths) >= 2:
                        break
                    if len(path) > 5:
                        G_copy = G.copy()
                        remove_idx = random.randint(1, min(len(path) - 2, len(path) - 1))
                        if remove_idx < len(path) - 1:
                            removed_edge = (path[remove_idx], path[remove_idx + 1])
                            try:
                                G_copy.remove_edge(*removed_edge)
                                alt_path = astar_route(G_copy, src_node, dst_node, impassable_depth)
                                if alt_path and len(alternative_paths) < 3:
                                    add_path(alt_path, f"Strategy 4 (removed edge {removed_edge})")
                            except:
                                pass
                logger.info(f"[SIMULATE START] Strategy 4: Attempted edge removal")
            except Exception as e:
                logger.warning(f"[SIMULATE START] Strategy 4 failed: {e}")

        # Strategy 5: Synthetic variation as last resort
        if len(alternative_paths) < 2 and len(path) > 10:
            logger.info("[SIMULATE START] Strategy 5: Creating synthetic route variation...")
            try:
                third = len(path) // 3
                alt_variation = path[:third] + path[third:2*third][::-1] + path[2*third:]
                if path_is_new(alt_variation):
                    add_path(alt_variation, "Strategy 5 (synthetic)")
            except Exception as e:
                logger.warning(f"[SIMULATE START] Strategy 5 failed: {e}")

        logger.info(f"[SIMULATE START] Alternative route generation complete: {len(alternative_paths)} alternatives found")

        # 10. Build response
        logger.info("[SIMULATE START] Step 10: Building session and response...")
        speed_kph = SPEED_MAP.get(req.speed_mode, 30)
        logger.debug(f"[SIMULATE START] Speed mode: {req.speed_mode} ({speed_kph} km/h)")

        # Calculate summary with proper ETA based on speed mode
        base_summary = route_summary(G, path, impassable_depth)
        summary = {
            "total_distance_m": base_summary["total_distance_m"],
            "eta_minutes": calculate_eta_minutes(base_summary["total_distance_m"], speed_kph),
            "max_flood_depth_m": base_summary["max_flood_depth_m"],
            "flooded_segments": base_summary["flooded_segments"],
            "safe": base_summary["safe"],
        }
        active_hoblis = list({hobli_for_node.get(n, "unknown") for n in path})
        # Use mm/hour values for heatmap (not mm/tick which are too small to visualize)
        heatmap = build_rainfall_heatmap(rainfall_mm_hour, hobli_coords, max_rainfall_mm=100.0)
        logger.debug(f"[SIMULATE START] Route summary: distance={summary['total_distance_m']}m, ETA={summary['eta_minutes']}min ({speed_kph}km/h), max_depth={summary['max_flood_depth_m']}m")

        # Build flood overlay GeoJSON (flooded corridor edges for map visualization)
        flood_features = []
        for u, v, data in G.edges(data=True):
            wd = data.get("water_depth", 0)
            if wd > 0.05:
                coords = data.get("geometry", [
                    [G.nodes[u]["lon"], G.nodes[u]["lat"]],
                    [G.nodes[v]["lon"], G.nodes[v]["lat"]],
                ])
                flood_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "water_depth": round(wd, 3),
                        "flood_risk": data.get("flood_risk", "low"),
                    }
                })
        # Cap at 2000 features for performance, prioritizing deepest floods
        if len(flood_features) > 2000:
            flood_features.sort(key=lambda f: f["properties"]["water_depth"], reverse=True)
            flood_features = flood_features[:2000]
        flood_overlay = {"type": "FeatureCollection", "features": flood_features}
        logger.info(f"[SIMULATE START] Flood overlay: {len(flood_features)} flooded road segments")

        # 11. Create session (session_id already created earlier)
        logger.info("[SIMULATE START] Step 11: Creating simulation session...")
        position = PersonPosition(
            path_nodes=path,
            G=G,
            speed_kph=speed_kph,
            tick_mins=req.tick_mins
        )
        session = SimulationSession(
            session_id=session_id,
            G=G,
            path_nodes=path,
            position=position,
            rainfall=rainfall_snapshot,
            hobli_coords=hobli_coords,
            active_hoblis=active_hoblis,
            tick=0,
            evolution_mode=req.evolution_mode,
            speed_kph=speed_kph,
            speed_mode=req.speed_mode,
            tick_mins=req.tick_mins,
            dst_lat=req.dst_lat,
            dst_lon=req.dst_lon,
            scenario_date=scenario_date,
            scenario_month=scenario_month,
            last_accessed=time.time(),
            mode=req.mode,
            rainfall_source=req.rainfall_source
        )
        SIMULATE_SESSIONS[session_id] = session
        logger.info(f"[SIMULATE START] Session created: session_id={session_id}")
        logger.debug(f"[SIMULATE START] Total active sessions: {len(SIMULATE_SESSIONS)}")

        # Build alternative route GeoJSON
        logger.info("[SIMULATE START] Step 12: Building alternative route responses...")
        alternative_routes = []

        # Create summaries for all alternatives
        alt_summaries_with_paths = []
        for alt_path in alternative_paths:
            alt_base_summary = route_summary(G, alt_path, impassable_depth)
            alt_summary = {
                "total_distance_m": alt_base_summary["total_distance_m"],
                "eta_minutes": calculate_eta_minutes(alt_base_summary["total_distance_m"], speed_kph),
                "max_flood_depth_m": alt_base_summary["max_flood_depth_m"],
                "flooded_segments": alt_base_summary["flooded_segments"],
                "safe": alt_base_summary["safe"],
            }
            alt_summaries_with_paths.append((alt_path, alt_summary))

        # Rank alternatives: prefer safe routes, then shorter distance, then less flood
        alt_summaries_with_paths.sort(key=lambda x: (
            not x[1]["safe"],  # Safe routes first
            x[1]["max_flood_depth_m"],  # Less flood depth
            x[1]["total_distance_m"]  # Shorter distance
        ))

        # Build route responses in ranked order
        best_alt = None
        for alt_path, alt_summary in alt_summaries_with_paths:
            alternative_routes.append({
                "geojson": build_route_geojson(G, alt_path),
                "summary": alt_summary,
                "steps": generate_steps(G, alt_path),
            })
            if best_alt is None:
                best_alt = alt_summary

        logger.info(f"[SIMULATE START] Alternative routes built: {len(alternative_routes)}")

        # Decide: use primary or best alternative based on flood conditions
        primary_base = route_summary(G, path, impassable_depth)
        if best_alt and best_alt["max_flood_depth_m"] < primary_base["max_flood_depth_m"] and best_alt["safe"]:
            logger.info(f"[SIMULATE START] Switching to safer alternative route (flood: {primary_base['max_flood_depth_m']:.2f}m → {best_alt['max_flood_depth_m']:.2f}m)")
            # Don't actually switch the route in the response, just inform frontend

        logger.info(f"[SIMULATE START] SUCCESS: Simulation initialized (session_id={session_id})")

        # Build route recommendation based on flood conditions
        route_recommendation = None
        primary_summary = summary
        if best_alt and best_alt["safe"] and best_alt["max_flood_depth_m"] < primary_summary["max_flood_depth_m"]:
            route_recommendation = f"⚠️ Safer alternative available: {best_alt['max_flood_depth_m']:.2f}m flood (vs {primary_summary['max_flood_depth_m']:.2f}m on main route)"

        return {
            "status": "ok",
            "session_id": session_id,
            "route_geojson": build_route_geojson(G, path),
            "alternative_routes": alternative_routes,
            "flood_overlay": flood_overlay,
            "steps": generate_steps(G, path),
            "initial_rainfall": rainfall_snapshot,
            "rainfall_heatmap": heatmap,
            "scenario": {
                "date": scenario_date,
                "month": scenario_month,
                "evolution_mode": req.evolution_mode,
            },
            "person_position": dict(zip(("lat", "lon"), position._interpolate_position())),
            "summary": summary,
            "active_hoblis": active_hoblis,
            "route_recommendation": route_recommendation,
            "tick": 0,
            "arrived": False,
        }

    except Exception as e:
        import traceback
        logger.error(f"[SIMULATE START] EXCEPTION: {type(e).__name__}: {str(e)}")
        logger.error(f"[SIMULATE START] Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@simulate_router.post("/tick")
async def simulate_tick(req: SimulateTickRequest):
    """Advance simulation by one tick — evolves rainfall, recomputes flood physics, reroutes if needed."""
    logger.info(f"[SIMULATE TICK] ═══════════ Tick requested for session={req.session_id[:8]}... ═══════════")
    cleanup_stale_sessions()

    if req.session_id not in SIMULATE_SESSIONS:
        logger.warning(f"[SIMULATE TICK] Session not found: {req.session_id}")
        return {"status": "error", "message": "Session not found."}

    session = SIMULATE_SESSIONS[req.session_id]
    session.last_accessed = time.time()
    logger.info(f"[SIMULATE TICK] Session loaded | tick={session.tick} | mode={session.evolution_mode} | edge_idx={session.position.current_edge_idx}/{len(session.path_nodes)-1}")

    try:
        import networkx as nx

        # ── 1. Advance person position ─────────────────────────────────────
        if session.mode == "realtime" and req.current_lat is not None and req.current_lon is not None:
            # Update position based on real GPS coordinates
            person_lat, person_lon = req.current_lat, req.current_lon
            # Snap to nearest node on the path to keep navigation logic working
            from corridor_graph import snap_to_node
            # We don't want to re-snap the whole path, just find where we are
            # For simplicity, we'll keep the current_edge_idx logic but update it if the user is far ahead
            # But for a true "Google Maps" feel, we should probably just find the nearest node on the current path
            
            # Simple approach: update the PersonPosition object with new coords
            # But PersonPosition is designed for path interpolation. 
            # Let's just use the provided lat/lon directly for the response.
            logger.info(f"[SIMULATE TICK] 📍 Real-time GPS: ({person_lat:.5f}, {person_lon:.5f})")
            
            # Update session position's current node to the nearest on path
            min_dist = float('inf')
            nearest_idx = session.position.current_edge_idx
            for i, nid in enumerate(session.path_nodes):
                n = session.G.nodes[nid]
                dist = ((n['lat'] - person_lat)**2 + (n['lon'] - person_lon)**2)**0.5
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = i
            
            session.position.current_edge_idx = min(nearest_idx, len(session.path_nodes) - 2)
            session.position.edge_progress = 0.0 # reset progress on edge for simplicity
        else:
            session.position.advance()
            person_lat, person_lon = session.position._interpolate_position()
            logger.info(f"[SIMULATE TICK] 🚗 Person at ({person_lat:.5f}, {person_lon:.5f}) | edge {session.position.current_edge_idx}/{len(session.path_nodes)-1} | progress={session.position.edge_progress:.2f}")

        # ── 2. Evolve rainfall ─────────────────────────────────────────────
        old_rainfall = dict(session.rainfall)
        
        if session.mode == "realtime" and session.rainfall_source == "ksndmc":
            logger.info("[SIMULATE TICK] Fetching fresh KSNDMC rainfall...")
            from rainfall_service import fetch_rainfall
            new_rainfall, _ = await fetch_rainfall()
        else:
            new_rainfall = evolve_rainfall(
                session.rainfall,
                session.hobli_coords,
                session.tick,
                session.evolution_mode
            )
        session.rainfall = new_rainfall

        # Compute rainfall statistics for logging and frontend
        old_avg = sum(old_rainfall.values()) / max(len(old_rainfall), 1)
        new_avg = sum(new_rainfall.values()) / max(len(new_rainfall), 1)
        new_max = max(new_rainfall.values()) if new_rainfall else 0
        rain_mm_hr_avg = new_avg * (60.0 / session.tick_mins)  # Convert mm/tick to mm/hr
        rain_mm_hr_max = new_max * (60.0 / session.tick_mins)

        # Track which hoblis changed significantly
        changed_hoblis = []
        for h in new_rainfall:
            old_val = old_rainfall.get(h, 0)
            new_val = new_rainfall.get(h, 0)
            if abs(new_val - old_val) > 0.0001:
                changed_hoblis.append(h)

        logger.info(
            f"[SIMULATE TICK] 🌧️ Rainfall: avg={rain_mm_hr_avg:.1f}mm/hr max={rain_mm_hr_max:.1f}mm/hr | "
            f"Δavg={((new_avg - old_avg) / max(old_avg, 0.0001)) * 100:+.1f}% | "
            f"changed_hoblis={len(changed_hoblis)}"
        )

        # ── 3. ALWAYS recompute flood physics (rainfall evolves every tick) ──
        should_reroute_bool, changed_hobli = should_reroute(old_rainfall, new_rainfall, session.active_hoblis)

        impassable_depth = IMPASSABLE_DEPTH_MAP.get(session.speed_mode, 0.25)

        # Always recompute flood physics — this is the key fix.
        # In a real system, we'd be continuously querying rain gauges.
        rainfall_mm_hour = scenario_to_flood_input(new_rainfall, session.tick_mins)
        hobli_for_node = assign_hoblis_to_nodes(session.G, session.hobli_coords)
        session.G = compute_flood(session.G, rainfall_mm_hour, hobli_for_node)

        # Log flood state after recomputation
        max_depth_on_graph = max((d.get("water_depth", 0) for _, _, d in session.G.edges(data=True)), default=0)
        flooded_edge_count = sum(1 for _, _, d in session.G.edges(data=True) if d.get("water_depth", 0) > 0.05)
        impassable_edge_count = sum(1 for _, _, d in session.G.edges(data=True) if d.get("water_depth", 0) >= impassable_depth)
        logger.info(
            f"[SIMULATE TICK] 💧 Flood recomputed: max_depth={max_depth_on_graph:.3f}m | "
            f"flooded_edges={flooded_edge_count}/{session.G.number_of_edges()} | "
            f"impassable_edges={impassable_edge_count}"
        )

        # ── 4. Check distance to next flooded segment on CURRENT path ──────
        rerouted = False
        reroute_reason = None
        new_route_geojson = None
        new_steps = None
        distance_to_flood = float('inf')
        accumulated_dist = 0.0
        flood_ahead_depth = 0.0

        for i in range(session.position.current_edge_idx, len(session.path_nodes) - 1):
            u = session.path_nodes[i]
            v = session.path_nodes[i+1]
            if not session.G.has_edge(u, v):
                continue

            edge_data = session.G[u][v]
            if isinstance(edge_data, dict) and 0 in edge_data:
                edge_data = edge_data[0]

            depth = edge_data.get("water_depth", 0.0)
            if depth >= impassable_depth:
                distance_to_flood = accumulated_dist
                flood_ahead_depth = depth
                break

            edge_len = edge_data.get("length", 0.0)
            if i == session.position.current_edge_idx:
                accumulated_dist += edge_len * (1.0 - session.position.edge_progress)
            else:
                accumulated_dist += edge_len

        if distance_to_flood < float('inf'):
            logger.info(
                f"[SIMULATE TICK] ⚠️ Flooded road detected {distance_to_flood:.0f}m ahead | "
                f"depth={flood_ahead_depth:.3f}m (impassable={impassable_depth}m)"
            )
        else:
            logger.debug("[SIMULATE TICK] ✅ No impassable flood on current path")

        # ── 5. Trigger reroute if approaching flood (within 500m) ──────────
        approaching_flood = (distance_to_flood <= 500.0)

        if approaching_flood:
            current_node = session.position.current_node()
            dst_node = session.path_nodes[-1]
            new_path = astar_route(session.G, current_node, dst_node, impassable_depth, strict=False)
            current_remainder = session.path_nodes[session.position.current_edge_idx:]

            if new_path and new_path != current_remainder:
                logger.info(
                    f"[SIMULATE TICK] 🔄 REROUTE TRIGGERED! Flooded road {int(distance_to_flood)}m ahead "
                    f"(depth={flood_ahead_depth:.2f}m) | new_path={len(new_path)} nodes vs old={len(current_remainder)} nodes"
                )

                if session.original_route_max_depth is None:
                    old_summary = route_summary(session.G, current_remainder, impassable_depth)
                    session.original_route_max_depth = old_summary["max_flood_depth_m"]

                session.route_history.append({
                    "geojson": build_route_geojson(session.G, current_remainder),
                    "tick": session.tick
                })
                if len(session.route_history) > 5:
                    session.route_history = session.route_history[-5:]

                traveled_nodes = session.path_nodes[:session.position.current_edge_idx]
                combined_path = traveled_nodes + new_path
                session.path_nodes = combined_path
                session.position.path_nodes = combined_path
                session.position.G = session.G

                rerouted = True
                reroute_reason = f"Flooded road {int(distance_to_flood)}m ahead ({flood_ahead_depth:.2f}m deep)"
                new_route_geojson = build_route_geojson(session.G, session.path_nodes)
                new_steps = generate_steps(session.G, session.path_nodes)
            else:
                logger.info("[SIMULATE TICK] ⚠️ Approaching flood but no better route found")

        # ── 6. Build flood overlay for frontend map ────────────────────────
        flood_features = []
        for u, v, data in session.G.edges(data=True):
            wd = data.get("water_depth", 0)
            if wd > 0.05:
                coords = data.get("geometry", [
                    [session.G.nodes[u]["lon"], session.G.nodes[u]["lat"]],
                    [session.G.nodes[v]["lon"], session.G.nodes[v]["lat"]],
                ])
                flood_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "water_depth": round(wd, 3),
                        "flood_risk": data.get("flood_risk", "low"),
                    }
                })
        if len(flood_features) > 2000:
            flood_features.sort(key=lambda f: f["properties"]["water_depth"], reverse=True)
            flood_features = flood_features[:2000]
        flood_overlay = {"type": "FeatureCollection", "features": flood_features}

        # ── 7. Build rainfall log for frontend ─────────────────────────────
        # Determine flood status
        if rerouted:
            flood_status = "rerouting"
        elif impassable_edge_count > 0:
            flood_status = "critical"
        elif flooded_edge_count > 10:
            flood_status = "building"
        else:
            flood_status = "none"

        # Build human-readable log message
        if rerouted:
            log_message = f"🔄 REROUTING — {reroute_reason}"
        elif rain_mm_hr_avg > 50:
            log_message = f"🌊 Heavy rain: {rain_mm_hr_avg:.0f}mm/hr"
        elif rain_mm_hr_avg > 20:
            log_message = f"⛈️ Moderate rain: {rain_mm_hr_avg:.0f}mm/hr — {flooded_edge_count} roads flooding"
        elif rain_mm_hr_avg > 5:
            log_message = f"🌧️ Light rain: {rain_mm_hr_avg:.0f}mm/hr"
        else:
            log_message = f"🌤️ Minimal rain: {rain_mm_hr_avg:.1f}mm/hr"

        rainfall_log = {
            "tick": session.tick,
            "avg_rainfall_mm_hr": round(rain_mm_hr_avg, 1),
            "max_rainfall_mm_hr": round(rain_mm_hr_max, 1),
            "max_flood_depth_m": round(max_depth_on_graph, 3),
            "flooded_roads": flooded_edge_count,
            "impassable_roads": impassable_edge_count,
            "flood_status": flood_status,
            "message": log_message,
            "evolution_mode": session.evolution_mode,
        }

        logger.info(f"[SIMULATE TICK] 📊 Log: {log_message}")

        # ── 8. Update tick, heatmap, summary ───────────────────────────────
        session.tick += 1
        heatmap = build_rainfall_heatmap(session.rainfall, session.hobli_coords)
        
        # Calculate summary for the remaining/full path
        if session.position.is_arrived():
            # Upon arrival, return the total journey summary (full path)
            summary = route_summary(session.G, session.path_nodes, impassable_depth)
            # Add total time taken (tick * 0.2 min)
            summary["total_time_taken_min"] = round(session.tick * 0.2)
        else:
            # During transit, return the summary for the remaining path
            remaining_path = session.path_nodes[session.position.current_edge_idx:]
            summary = route_summary(session.G, remaining_path, impassable_depth)

        # ── 9. Check arrival ───────────────────────────────────────────────
        arrived = session.position.is_arrived()
        if arrived:
            logger.info(f"[SIMULATE TICK] 🏁 ARRIVED at destination after {session.tick} ticks!")
            del SIMULATE_SESSIONS[req.session_id]
        else:
            logger.info(f"[SIMULATE TICK] ═══════════ Tick {session.tick} complete ═══════════")

        return {
            "session_id": req.session_id,
            "tick": session.tick,
            "person_position": {"lat": person_lat, "lon": person_lon},
            "current_rainfall": session.rainfall,
            "rainfall_heatmap": heatmap,
            "rerouted": rerouted,
            "reroute_reason": reroute_reason,
            "route_geojson": new_route_geojson or build_route_geojson(session.G, session.path_nodes),
            "route_history_geojson": [r["geojson"] for r in session.route_history],
            "original_route_max_depth": session.original_route_max_depth,
            "flood_overlay": flood_overlay,
            "rainfall_log": rainfall_log,
            "steps": new_steps or generate_steps(session.G, session.path_nodes),
            "summary": summary,
            "arrived": arrived,
        }

    except Exception as e:
        import traceback
        logger.error(f"[SIMULATE TICK] EXCEPTION: {type(e).__name__}: {str(e)}")
        logger.error(f"[SIMULATE TICK] Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}


@simulate_router.post("/reset")
async def simulate_reset(req: SimulateResetRequest):
    """Clear a simulation session."""
    if req.session_id in SIMULATE_SESSIONS:
        del SIMULATE_SESSIONS[req.session_id]
    return {"status": "ok"}


@simulate_router.get("/scenarios")
async def simulate_scenarios():
    """Return available scenario options."""
    return {
        "months": ["April", "May", "June", "July"],
        "intensities": ["light", "moderate", "heavy", "extreme", "random"],
        "evolution_modes": ["intensify", "dissipate", "move", "random"],
        "speed_modes": [
            {"key": "walk", "label": "Walking (4 km/h)", "km_h": 4},
            {"key": "car", "label": "Car (30 km/h)", "km_h": 30},
            {"key": "emergency", "label": "Emergency (60 km/h)", "km_h": 60},
        ]
    }


@simulate_router.get("/rainfall-stats")
async def simulate_rainfall_stats():
    """Return historical rainfall statistics."""
    try:
        db = _get_db()
        if db is None:
            return {"max_24h_mm": 100, "avg_24h_mm": 20, "hobli_maxes": {}}

        all_records = []
        for month in ["April", "May", "June", "July"]:
            doc = await db.rainfall_data.find_one({"month": month})
            if doc is not None and doc.get("records"):
                all_records.extend(doc["records"])

        stats = get_rainfall_stats(all_records)
        return stats
    except Exception:
        return {"max_24h_mm": 100, "avg_24h_mm": 20, "hobli_maxes": {}}
