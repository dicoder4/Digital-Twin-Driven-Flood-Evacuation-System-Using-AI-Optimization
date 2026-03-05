"""
service.py — Business logic for Urban Flood Digital Twin
────────────────────────────────────────────────────────
Following MVC architecture: This is the Service layer handling logic
between the API (Controller) and the Data/Simulators (Model).
"""

import asyncio
import json
import time as _time_module
from datetime import datetime
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
    if key not in _PLANNER_MAP:
        raise ValueError(f"Unknown algorithm '{algorithm}'. Choose from: {list(_PLANNER_MAP.keys())}")
    return _PLANNER_MAP[key]

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
        # Offload CPU-bound graph loading to executor
        await asyncio.get_event_loop().run_in_executor(None, get_region, key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load graph: {e}")

    return {
        "status":   "loaded",
        "hobli":    hobli_name,
        "lat":      coords["lat"],
        "lon":      coords["lon"],
        "district": coords["district"],
    }

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

async def run_simulation_generator(hobli: str, rainfall_mm: float, steps: int, decay_factor: float, evacuation_mode: bool = False, use_traffic: bool = False, algorithm: str = "ga"):
    """Generator for SSE simulation stream."""
    import time
    key = norm_key(hobli)
    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli}' not loaded.")

    entry  = REGION_CACHE[key]
    G_ref  = entry["G"]
    drains = entry["drain_nodes"]
    lakes  = entry["lake_nodes"]

    sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)
    sim.initialize_from_drains(rainfall_mm)

    # 1. Distribute population on nodes
    pop_data = await get_hobli_population(hobli)
    total_pop = pop_data.get("total_population", 0)

    # Scale population if in evacuation mode (1% test)
    if evacuation_mode:
        total_pop = max(1, total_pop // 100)
        print(f"{_ts()}  [service] Evacuation Mode ON: scaling population to {total_pop}")

    sim.distribute_population(total_pop)

    # 2. Pre-fetch shelters
    shelter_resp = await fetch_shelters(hobli)
    all_shelters = shelter_resp["shelters"]

    loop = asyncio.get_event_loop()

    # ── Streaming loop: flood physics only, no GA ─────────────────────────
    for i in range(steps):
        await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
        impact = await loop.run_in_executor(None, sim.calculate_flood_impact)

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
    final_flood_geojson = (
        json.loads(final_flood_gdf.to_json()) if not final_flood_gdf.empty else None
    )
    print(f"{_ts()}  [DEBUG] final flood features = {len(final_flood_geojson['features']) if final_flood_geojson else 0}")

    # Filter shelters: prefer safe ones; fall back to all if all are flooded
    shelters_with_safety = filter_safe_shelters(all_shelters, final_flood_geojson, None)
    safe_shelters = [s for s in shelters_with_safety if s["safe"]]
    safe_count = len(safe_shelters)
    print(f"{_ts()}  [DEBUG] safe shelters after filter = {safe_count} / {len(shelters_with_safety)}")
    for s in shelters_with_safety[:5]:
        print(f"{_ts()}    shelter: {s['name']} | safe={s['safe']} | cap={s['capacity']} | node_id={s.get('node_id')}")

    if not safe_shelters:
        # All shelters are in flood zone — use all of them (least-bad choice)
        print(f"{_ts()}  [DEBUG] WARNING: all shelters flooded — using all candidates as fallback")
        safe_shelters = shelters_with_safety if shelters_with_safety else all_shelters

    at_risk = sim.get_at_risk_nodes()
    print(f"{_ts()}  [DEBUG] at_risk nodes = {len(at_risk)}")

    # Diagnostic: check sample depths and populations
    sample_nodes = list(sim.G.nodes())[:5]
    node_depths_sample = {n: round(sim.G.nodes[n].get('water_depth', 0), 3) for n in sample_nodes}
    pop_sample = {n: sim.node_populations.get(n, 0) for n in sample_nodes}
    print(f"{_ts()}  [DEBUG] sample node depths: {node_depths_sample}")
    print(f"{_ts()}  [DEBUG] sample node pops:   {pop_sample}")
    print(f"{_ts()}  [DEBUG] total_pop distributed: {sum(sim.node_populations.values())}")

    if not at_risk:
        print(f"{_ts()}  [DEBUG] WARNING: at_risk is empty — lowering depth threshold to 0.05m for retry")
        # Retry with a lower threshold — maybe flood didn't propagate deeply enough
        at_risk = sim.get_at_risk_nodes(depth_threshold_m=0.05)
        print(f"{_ts()}  [DEBUG] at_risk (0.05m threshold) = {len(at_risk)}")

    # Track total at-risk population BEFORE GA runs (for accurate remaining count)
    total_at_risk_before_ga = sum(pop for _, pop in at_risk)
    print(f"{_ts()}  [DEBUG] total at-risk pop before GA = {total_at_risk_before_ga}")

    planner_instance = None  # sentinel for traffic geojson extraction
    if at_risk and safe_shelters:
        at_risk_formatted = [
            {"id": nid, "pop": pop, "lat": sim.G.nodes[nid]["y"], "lon": sim.G.nodes[nid]["x"]}
            for nid, pop in at_risk
        ]
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

            planner_instance, final_evacuation_plan = await loop.run_in_executor(None, _init_and_run)

            ga_execution_time = round(time.time() - ga_start, 2)
            print(f"{_ts()}  [{algo_label}] complete: {len(final_evacuation_plan)} routes in {ga_execution_time}s")
            best_fitness = round(getattr(planner_instance, 'best_fitness', 0.0), 1)
            print(f"{_ts()}  [{algo_label}] best_fitness = {best_fitness}")

        except Exception as e:
            import traceback
            print(f"{_ts()}  [DEBUG] *** {algo_label} EXCEPTION: {e} ***")
            traceback.print_exc()
            ga_execution_time = round(time.time() - ga_start, 2)

        # Update shelter occupancy from GA result
        for move in final_evacuation_plan:
            sim.shelter_occupancy[move["to_shelter"]] = (
                sim.shelter_occupancy.get(move["to_shelter"], 0) + move["pop"]
            )
            sim.total_evacuated += move["pop"]
        print(f"{_ts()}  [DEBUG] total_evacuated = {sim.total_evacuated}")
    else:
        print(f"{_ts()}  [DEBUG] *** BLOCKED: at_risk and/or safe_shelters is empty — {algo_label} skipped ***")
    print(f"{_ts()} {'='*56}\n")


    # Build shelter reports with fill percentage
    shelter_reports = [
        {
            "id":       s["id"],
            "name":     s.get("name", s["id"]),
            "type":     s.get("type", "unknown"),
            "occupancy": sim.shelter_occupancy.get(s["id"], 0),
            "capacity":  s["capacity"],
            "occupancy_pct": round(
                min(sim.shelter_occupancy.get(s["id"], 0) / max(s["capacity"], 1) * 100, 100), 1
            ),
        }
        for s in all_shelters
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

    final_report = {
        "done":      True,
        "total":     steps,
        "algorithm": algorithm.upper(),
        "evacuation_plan":      final_evacuation_plan,
        "traffic_geojson":      traffic_geojson,
        "traffic_segment_count": traffic_segment_count,
        "summary": {
            "total_evacuated":         total_assigned,
            "total_at_risk_remaining": at_risk_remaining,
            "total_at_risk_initial":   total_at_risk_before_ga,
            "simulation_population":   total_pop,
            "success_rate_pct":        round(
                total_assigned / max(total_at_risk_before_ga, 1) * 100, 1
            ),
            "algorithm":               algorithm.upper(),
            "ga_execution_time":       ga_execution_time,
            "best_fitness":            best_fitness,
            "avg_distance_per_person": round(
                best_fitness / max(total_at_risk_before_ga, 1), 1
            ),
            "shelter_reports":         shelter_reports,
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

    key = norm_key(hobli)
    if key not in REGION_CACHE:
        raise HTTPException(status_code=400, detail=f"Region '{hobli}' not loaded.")

    entry  = REGION_CACHE[key]
    G_ref  = entry["G"]
    drains = entry["drain_nodes"]
    lakes  = entry["lake_nodes"]

    sim = UrbanFloodSimulator(G_ref.copy(), drain_nodes=drains, lake_nodes=lakes)
    sim.initialize_from_drains(rainfall_mm)

    # Population
    pop_data  = await get_hobli_population(hobli)
    total_pop = pop_data.get("total_population", 0)
    if evacuation_mode:
        total_pop = max(1, total_pop // 100)
        print(f"{_ts()}  [compare] Evacuation Mode ON: scaling population to {total_pop}")
    sim.distribute_population(total_pop)

    # Shelters
    shelter_resp = await fetch_shelters(hobli)
    all_shelters = shelter_resp["shelters"]

    loop = asyncio.get_event_loop()

    # ── Phase 1: stream flood steps (identical to single-algo mode) ──────────
    print(f"{_ts()}  [compare] Starting flood simulation ({steps} steps)")
    for i in range(steps):
        await loop.run_in_executor(None, sim.propagate_flood_step, decay_factor)
        impact    = await loop.run_in_executor(None, sim.calculate_flood_impact)
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
    final_flood_geojson = (
        json.loads(final_flood_gdf.to_json()) if not final_flood_gdf.empty else None
    )

    shelters_with_safety = filter_safe_shelters(all_shelters, final_flood_geojson, None)
    safe_shelters        = [s for s in shelters_with_safety if s["safe"]]
    if not safe_shelters:
        print(f"{_ts()}  [compare] WARNING: all shelters flooded — using all as fallback")
        safe_shelters = shelters_with_safety if shelters_with_safety else all_shelters

    at_risk = sim.get_at_risk_nodes()
    if not at_risk:
        print(f"{_ts()}  [compare] WARNING: at_risk empty — retrying at 0.05 m threshold")
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
                    "occupancy_pct": round(
                        min(shelter_occ.get(s["id"], 0) / max(s["capacity"], 1) * 100, 100), 1
                    ),
                }
                for s in all_shelters
            ]

            traffic_geojson       = None
            traffic_segment_count = 0
            if use_traffic and instance is not None:
                try:
                    traffic_geojson       = instance.get_traffic_geojson()
                    traffic_segment_count = getattr(instance, "_traffic_segment_count", 0)
                except Exception:
                    pass

            compare_results[algo_key] = {
                "evacuation_plan":       plan,
                "traffic_geojson":       traffic_geojson,
                "traffic_segment_count": traffic_segment_count,
                "summary": {
                    "total_evacuated":         total_evac,
                    "total_at_risk_remaining": at_risk_remaining,
                    "total_at_risk_initial":   total_at_risk_initial,
                    "simulation_population":   total_pop,
                    "success_rate_pct":        round(total_evac / max(total_at_risk_initial, 1) * 100, 1),
                    "algorithm":               algo_key.upper(),
                    "ga_execution_time":       elapsed,
                    "best_fitness":            fitness,
                    "avg_distance_per_person": round(fitness / max(total_at_risk_initial, 1), 1),
                    "shelter_reports":         shelter_reports,
                },
            }

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

