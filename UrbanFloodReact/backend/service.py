"""
service.py — Business logic for Urban Flood Digital Twin
────────────────────────────────────────────────────────
Following MVC architecture: This is the Service layer handling logic
between the API (Controller) and the Data/Simulators (Model).
"""

import asyncio
import json
import pandas as pd
import osmnx as ox
from fastapi import HTTPException

# Relative imports from the backend package
from region_manager import (
    get_region, norm_key,
    HOBLI_COORDS, RAINFALL_DATA, REGIONS_TREE, REGION_CACHE,
)
from flood_simulator import UrbanFloodSimulator
from generate_people import get_population
from shelter_generator import extract_shelter_candidates, filter_safe_shelters
from evacuation_ga import GeneticEvacuationPlanner

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

async def run_simulation_generator(hobli: str, rainfall_mm: float, steps: int, decay_factor: float, evacuation_mode: bool = False):
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
        print(f"  [service] Evacuation Mode ON: scaling population to {total_pop}")

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

    print(f"\n{'='*60}")
    print(f"  [GA DEBUG] evacuation_mode = {evacuation_mode} (controls pop scaling only)")
    print(f"  [GA DEBUG] all_shelters count = {len(all_shelters)}")

    # GA always runs — evacuation_mode only affects 1% pop scaling above
    # Recalculate final flood impact for shelter safety classification
    final_impact = await loop.run_in_executor(None, sim.calculate_flood_impact)
    final_flood_gdf = final_impact["flood_gdf"]
    final_flood_geojson = (
        json.loads(final_flood_gdf.to_json()) if not final_flood_gdf.empty else None
    )
    print(f"  [GA DEBUG] final flood features = {len(final_flood_geojson['features']) if final_flood_geojson else 0}")

    # Filter shelters: prefer safe ones; fall back to all if all are flooded
    shelters_with_safety = filter_safe_shelters(all_shelters, final_flood_geojson, None)
    safe_shelters = [s for s in shelters_with_safety if s["safe"]]
    safe_count = len(safe_shelters)
    print(f"  [GA DEBUG] safe shelters after filter = {safe_count} / {len(shelters_with_safety)}")
    for s in shelters_with_safety[:5]:
        print(f"    shelter: {s['name']} | safe={s['safe']} | cap={s['capacity']} | node_id={s.get('node_id')}")

    if not safe_shelters:
        # All shelters are in flood zone — use all of them (least-bad choice)
        print("  [GA DEBUG] WARNING: all shelters flooded — using all candidates as fallback")
        safe_shelters = shelters_with_safety if shelters_with_safety else all_shelters

    at_risk = sim.get_at_risk_nodes()
    print(f"  [GA DEBUG] at_risk nodes = {len(at_risk)}")

    # Diagnostic: check sample depths and populations
    sample_nodes = list(sim.G.nodes())[:5]
    node_depths_sample = {n: round(sim.G.nodes[n].get('water_depth', 0), 3) for n in sample_nodes}
    pop_sample = {n: sim.node_populations.get(n, 0) for n in sample_nodes}
    print(f"  [GA DEBUG] sample node depths: {node_depths_sample}")
    print(f"  [GA DEBUG] sample node pops:   {pop_sample}")
    print(f"  [GA DEBUG] total_pop distributed: {sum(sim.node_populations.values())}")

    if not at_risk:
        print("  [GA DEBUG] WARNING: at_risk is empty — lowering depth threshold to 0.05m for retry")
        # Retry with a lower threshold — maybe flood didn't propagate deeply enough
        at_risk = sim.get_at_risk_nodes(depth_threshold_m=0.05)
        print(f"  [GA DEBUG] at_risk (0.05m threshold) = {len(at_risk)}")

    # Track total at-risk population BEFORE GA runs (for accurate remaining count)
    total_at_risk_before_ga = sum(pop for _, pop in at_risk)
    print(f"  [GA DEBUG] total at-risk pop before GA = {total_at_risk_before_ga}")

    if at_risk and safe_shelters:
        at_risk_formatted = [
            {"id": nid, "pop": pop, "lat": sim.G.nodes[nid]["y"], "lon": sim.G.nodes[nid]["x"]}
            for nid, pop in at_risk
        ]
        print(f"  [GA DEBUG] Running GA: {len(at_risk_formatted)} at-risk groups → {len(safe_shelters)} shelters")

        ga_start = time.time()
        try:
            # Scale GA parameters based on problem size for speed
            n_risk = len(at_risk_formatted)
            gens = max(15, min(50, 3000 // max(n_risk, 1)))
            pop_sz = min(60, max(20, n_risk * 2))
            print(f"  [GA DEBUG] Params: pop_size={pop_sz}, generations={gens}")

            planner = GeneticEvacuationPlanner(
                at_risk_formatted, safe_shelters, sim.G,
                pop_size=pop_sz, generations=gens
            )
            precompute_time = round(time.time() - ga_start, 2)
            print(f"  [GA DEBUG] Dijkstra precompute done in {precompute_time}s")

            evolve_start = time.time()
            final_evacuation_plan = await loop.run_in_executor(None, planner.run)
            ga_execution_time = round(time.time() - ga_start, 2)
            evolve_time = round(time.time() - evolve_start, 2)
            print(f"  [GA DEBUG] GA complete: {len(final_evacuation_plan)} routes in "
                  f"{ga_execution_time}s (precompute={precompute_time}s, evolve={evolve_time}s)")
        except Exception as e:
            import traceback
            print(f"  [GA DEBUG] *** GA EXCEPTION: {e} ***")
            traceback.print_exc()
            ga_execution_time = round(time.time() - ga_start, 2)

        # Update shelter occupancy from GA result
        for move in final_evacuation_plan:
            sim.shelter_occupancy[move["to_shelter"]] = (
                sim.shelter_occupancy.get(move["to_shelter"], 0) + move["pop"]
            )
            sim.total_evacuated += move["pop"]
        print(f"  [GA DEBUG] total_evacuated = {sim.total_evacuated}")
    else:
        print("  [GA DEBUG] *** BLOCKED: at_risk and/or safe_shelters is empty — GA skipped ***")
    print(f"{'='*60}\n")


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

    final_report = {
        "done":  True,
        "total": steps,
        "evacuation_plan": final_evacuation_plan,
        "summary": {
            "total_evacuated":         total_assigned,
            "total_at_risk_remaining": at_risk_remaining,
            "total_at_risk_initial":   total_at_risk_before_ga,
            "simulation_population":   total_pop,  # actual (possibly scaled) population
            "success_rate_pct":        round(
                total_assigned / max(total_at_risk_before_ga, 1) * 100, 1
            ),
            "ga_execution_time":       ga_execution_time,
            "shelter_reports":         shelter_reports,
        },
    }
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
