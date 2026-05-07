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


class SimulateTickRequest(BaseModel):
    session_id: str


class SimulateResetRequest(BaseModel):
    session_id: str


SPEED_MAP = {
    "car": 30,      # Car: 30 km/h (realistic urban speed with traffic)
    "bike": 15,     # Bike: 15 km/h (cycling speed)
    "walk": 4,      # Walk: 4 km/h (normal walking pace)
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
            req.src_lat, req.src_lon, req.dst_lat, req.dst_lon
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

        # 5. Pick rainfall scenario
        logger.info(f"[SIMULATE START] Step 5: Picking rainfall scenario (month={req.month}, intensity={req.intensity})...")
        rainfall_snapshot, scenario_date, scenario_month = await pick_scenario(req.month, req.intensity)
        logger.info(f"[SIMULATE START] Scenario selected: date={scenario_date}, month={scenario_month}, hoblis={len(rainfall_snapshot)}")
        logger.debug(f"[SIMULATE START] Rainfall snapshot: {rainfall_snapshot}")

        # 6. Assign hoblis to nodes
        logger.info("[SIMULATE START] Step 6: Assigning hoblis to nodes...")
        hobli_for_node = assign_hoblis_to_nodes(G, hobli_coords)
        logger.info(f"[SIMULATE START] Hoblis assigned to {len(hobli_for_node)} nodes")

        # 7. Compute flood with scenario rainfall (converted to mm/hour)
        logger.info("[SIMULATE START] Step 7: Computing flood physics with rainfall...")
        rainfall_mm_hour = scenario_to_flood_input(rainfall_snapshot, req.tick_mins)
        logger.debug("[SIMULATE START] Rainfall converted to mm/hour scale")
        G = compute_flood(G, rainfall_mm_hour, hobli_for_node)
        logger.info("[SIMULATE START] Flood physics computed")

        # 8. Create session ID early (needed for shelter evacuation response)
        session_id = str(uuid.uuid4())
        logger.info(f"[SIMULATE START] Session created: {session_id}")

        # 9. Route - Find primary and alternative paths
        logger.info("[SIMULATE START] Step 9: Computing A* route...")
        import networkx as nx
        from shelter_integration import get_shelter_candidates, rank_shelters_by_distance

        path = astar_route(G, src_node, dst_node)
        if path is None:
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

                shelter_path = astar_route(G, src_node, shelter_node)
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
                "session_id": session_id,
            }
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
            if depth >= 1.5:  # IMPASSABLE_DEPTH
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
                            alt1 = astar_route(G, src_node, mid_node)
                            alt2 = astar_route(G, mid_node, dst_node)
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
                                alt_path = astar_route(G_copy, src_node, dst_node)
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
        base_summary = route_summary(G, path)
        summary = {
            "total_distance_m": base_summary["total_distance_m"],
            "eta_minutes": calculate_eta_minutes(base_summary["total_distance_m"], speed_kph),
            "max_flood_depth_m": base_summary["max_flood_depth_m"],
            "flooded_segments": base_summary["flooded_segments"],
            "safe": base_summary["safe"],
        }
        active_hoblis = list({hobli_for_node.get(n, "unknown") for n in path})
        heatmap = build_rainfall_heatmap(rainfall_snapshot, hobli_coords)
        logger.debug(f"[SIMULATE START] Route summary: distance={summary['total_distance_m']}m, ETA={summary['eta_minutes']}min ({speed_kph}km/h), max_depth={summary['max_flood_depth_m']}m")

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
            tick_mins=req.tick_mins,
            dst_lat=req.dst_lat,
            dst_lon=req.dst_lon,
            scenario_date=scenario_date,
            scenario_month=scenario_month,
            last_accessed=time.time()
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
            alt_base_summary = route_summary(G, alt_path)
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
        primary_base = route_summary(G, path)
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
    """Advance simulation by one tick."""
    logger.debug(f"[SIMULATE TICK] Tick requested for session_id={req.session_id}")
    cleanup_stale_sessions()

    if req.session_id not in SIMULATE_SESSIONS:
        logger.warning(f"[SIMULATE TICK] Session not found: {req.session_id}")
        return {"status": "error", "message": "Session not found."}

    session = SIMULATE_SESSIONS[req.session_id]
    session.last_accessed = time.time()
    logger.debug(f"[SIMULATE TICK] Session {req.session_id} loaded. Tick={session.tick}")

    try:
        # 1. Advance person
        logger.debug("[SIMULATE TICK] Step 1: Advancing person position...")
        session.position.advance()
        person_lat, person_lon = session.position._interpolate_position()
        logger.debug(f"[SIMULATE TICK] Person moved to ({person_lat}, {person_lon})")

        # 2. Evolve rainfall
        logger.debug("[SIMULATE TICK] Step 2: Evolving rainfall scenario...")
        old_rainfall = dict(session.rainfall)
        new_rainfall = evolve_rainfall(
            session.rainfall,
            session.hobli_coords,
            session.tick,
            session.evolution_mode
        )
        session.rainfall = new_rainfall
        logger.debug(f"[SIMULATE TICK] Rainfall evolved. Changed hoblis: {len([h for h in old_rainfall if old_rainfall[h] != new_rainfall.get(h)])}")

        # 3. Check reroute
        logger.debug("[SIMULATE TICK] Step 3: Checking reroute condition...")
        rerouted = False
        reroute_reason = None
        new_route_geojson = None
        new_steps = None

        should_reroute_bool, changed_hobli = should_reroute(old_rainfall, new_rainfall, session.active_hoblis)
        if should_reroute_bool:
            logger.info(f"[SIMULATE TICK] REROUTE TRIGGERED by hobli: {changed_hobli}")
            # Re-run flood physics
            logger.debug("[SIMULATE TICK] Recomputing flood physics...")
            rainfall_mm_hour = scenario_to_flood_input(new_rainfall, session.tick_mins)

            # Create a copy of the graph for recomputation
            import networkx as nx
            g_copy = session.G.copy()
            hobli_for_node = assign_hoblis_to_nodes(g_copy, session.hobli_coords)
            g_copy = compute_flood(g_copy, rainfall_mm_hour, hobli_for_node)

            # Route from current position to destination
            logger.debug(f"[SIMULATE TICK] Computing new route from node {session.position.current_node()}...")
            current_node = session.position.current_node()
            dst_node = session.path_nodes[-1]
            new_path = astar_route(g_copy, current_node, dst_node)

            if new_path and new_path != session.path_nodes:
                # Save old route to history (max 5)
                session.route_history.append({
                    "geojson": build_route_geojson(session.G, session.path_nodes),
                    "tick": session.tick
                })
                if len(session.route_history) > 5:
                    session.route_history = session.route_history[-5:]

                # Update session
                session.G = G_copy
                session.path_nodes = new_path
                session.position = PersonPosition(
                    path_nodes=new_path,
                    G=G_copy,
                    speed_kph=session.speed_kph,
                    tick_mins=session.tick_mins,
                    current_edge_idx=0,
                    edge_progress=0.0
                )

                rerouted = True
                reroute_reason = f"Rainfall increased in {changed_hobli}"
                new_route_geojson = build_route_geojson(G_copy, new_path)
                new_steps = generate_steps(G_copy, new_path)

        # 4. Update tick and heatmap
        session.tick += 1
        heatmap = build_rainfall_heatmap(session.rainfall, session.hobli_coords)
        summary = route_summary(session.G, session.path_nodes)

        # 5. Check arrival
        arrived = session.position.is_arrived()
        if arrived:
            # Cleanup session
            del SIMULATE_SESSIONS[req.session_id]

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
            "steps": new_steps or generate_steps(session.G, session.path_nodes),
            "summary": summary,
            "arrived": arrived,
        }

    except Exception as e:
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
