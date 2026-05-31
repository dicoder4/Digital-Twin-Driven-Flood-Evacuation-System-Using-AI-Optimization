"""
mcp_evacuation_server.py — MCP Server for GenAI-Assisted Evacuation Planning
─────────────────────────────────────────────────────────────────────────────
Exposes the Digital Twin's evacuation planning capabilities as MCP tools
so that AI agents can autonomously query simulation state, get expert
analysis, and ask questions about evacuation data.

Usage:
    python mcp_evacuation_server.py          # runs via stdio (default)
    python mcp_evacuation_server.py --sse    # runs via SSE transport

Tools exposed:
    1. get_simulation_state   — Returns current simulation summary & shelter status
    2. get_expert_analysis    — Gets AI expert advice (logistics/tactical/civic)
    3. ask_evacuation_question — Free-form Q&A about evacuation data
    4. get_shelter_status      — Detailed shelter occupancy & severity breakdown
    5. get_route_summary       — Statistics and details about computed evacuation routes
    6. get_pressure_junctures   — Critical bottlenecks (converging routes/flood risk)
    7. generate_evacuation_strategy — AI-generated tactical strategy
"""

import sys
import os
import json

# Add parent directory (backend/) to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
try:
    from genai.context_builder import build_expert_context
    from genai.param_resolver import resolve_hobli
    from genai.weather_client import WeatherClient
except ImportError:
    from context_builder import build_expert_context
    from param_resolver import resolve_hobli
    from weather_client import WeatherClient

# ── Create MCP Server ─────────────────────────────────────────────────────────
mcp = FastMCP("Urban Flood Evacuation AI Server")

# ── Shared state via MongoDB ──────────────────────────────────────────────────
# FastAPI writes, MCP server reads — no local file needed on any deployment.
try:
    import db as _db
except ImportError:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    import db as _db

# Kept for backward-compat with mcp_flood_intelligence_server which imports _STATE_FILE
_STATE_FILE = None


def update_state(summary_data: dict, evacuation_plan: list = None, hobli: str = None, algorithm_analysis: dict = None):
    """Persist the latest simulation results to MongoDB."""
    _db.set_mcp_state(summary_data, evacuation_plan, hobli, algorithm_analysis)


def _load_state() -> dict:
    """Read the latest simulation state from MongoDB."""
    return _db.get_mcp_state()


def _get_enriched_context() -> dict:
    """Build enriched context from the latest simulation state in MongoDB."""
    state = _load_state()
    if not state.get("summary_data"):
        return {}
        
    # Prevent "RuntimeError: asyncio.run() cannot be called from a running event loop"
    # by offloading the async context builder to a fresh thread where there is no loop yet.
    def run_coro():
        import asyncio
        return asyncio.run(
            build_expert_context(
                state["summary_data"],
                state.get("evacuation_plan"),
                state.get("algorithm_analysis")
            )
        )
        
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        future = pool.submit(run_coro)
        return future.result()


# ══════════════════════════════════════════════════════════════════════════════
#  MCP TOOLS
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_simulation_state() -> str:
    """
    Get the current state of the flood evacuation simulation.
    Returns the enriched simulation summary including algorithm used,
    success rate, evacuee counts, and shelter overview.
    Call this first to understand the current situation before asking
    more specific questions.
    """
    ctx = _get_enriched_context()
    if not ctx:
        return "No simulation has been run yet. Please run a simulation first."

    sim = ctx.get("simulation", {})
    overview = ctx.get("shelter_overview", {})

    lines = [
        "=== Current Simulation State ===",
        "Algorithm: " + str(sim.get("algorithm", "N/A")),
        "Success Rate: " + str(sim.get("success_rate_pct", 0)) + "%",
        "Total Evacuated: " + str(sim.get("total_evacuated", 0)),
        "At-Risk Remaining: " + str(sim.get("total_at_risk_remaining", 0)),
        "Initial At-Risk: " + str(sim.get("total_at_risk_initial", 0)),
        "Execution Time: " + str(sim.get("execution_time_s", 0)) + "s",
        "Best Fitness: " + str(sim.get("best_fitness", 0)),
        "",
        "=== Shelter Overview ===",
        "Total Shelters: " + str(overview.get("total_shelters", 0)),
        "Critical (>=90% full): " + ", ".join(overview.get("critical_shelters", [])) if overview.get("critical_shelters") else "Critical: None",
        "Remaining Total Capacity: " + str(overview.get("total_remaining_capacity", 0)),
    ]

    state = _load_state()
    if state.get("hobli"):
        lines.insert(1, "Region: " + state["hobli"])

    return "\n".join(lines)


@mcp.tool()
def get_realtime_weather(hobli_name: str = None) -> str:
    """
    Fetch the current real-time rainfall and weather data for a given region.
    This helps the AI understand if current weather conditions justify
    starting an evacuation or increasing readiness.
    
    Args:
        hobli_name: Optional. Name of the Hobli. If omitted, uses the currently loaded region.
    """
    if not hobli_name:
        state = _load_state()
        hobli_name = state.get("hobli")
        
    if not hobli_name:
        return "Error: No region specified and no simulation region currently loaded."

    info = resolve_hobli(hobli_name)
    if not info:
        return f"Error: Could not find coordinates for Hobli '{hobli_name}'."
        
    try:
        client = WeatherClient.from_hobli_info(info)
        data = client.get_current()
        
        if data.get("source") == "error":
            return f"Error fetching weather: {data.get('description')}"
            
        return (
            f"Current Weather for {info['display']}:\n"
            f"- Temperature: {data['temp_c']}°C\n"
            f"- Rainfall: {data['precipitation_mm']} mm\n"
            f"- Condition: {data['description']}\n"
            f"Use these parameters to configure the simulation rainfall if needed."
        )
    except Exception as e:
        return f"Error connecting to weather service: {str(e)}"


@mcp.tool()
def get_shelter_status() -> str:
    """
    Get detailed shelter occupancy status for all shelters in the simulation.
    Each shelter includes: name, type, occupancy, capacity, fill percentage,
    remaining capacity, and severity status (CRITICAL/HIGH/MODERATE/EMPTY).
    Use this to identify overloaded shelters or find available capacity.
    """
    ctx = _get_enriched_context()
    if not ctx:
        return "No simulation data available."

    shelters = ctx.get("shelters", [])
    if not shelters:
        return "No shelter data available."

    lines = ["=== Shelter Status Report ===", ""]
    for s in shelters:
        status_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟡",
            "MODERATE": "🟢",
            "EMPTY": "⚪",
        }.get(s.get("status", ""), "")

        lines.append(
            status_emoji + " " + s.get("name", "Unknown")
            + " [" + s.get("type", "?") + "]"
        )
        lines.append(
            "   Occupancy: " + str(s.get("occupancy", 0))
            + "/" + str(s.get("capacity", 0))
            + " (" + str(s.get("occupancy_pct", 0)) + "%)"
            + " | Remaining: " + str(s.get("remaining_capacity", 0))
            + " | Status: " + s.get("status", "UNKNOWN")
        )
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_route_summary() -> str:
    """
    Get statistics about the computed evacuation routes.
    Includes: total routes, people routed, average/max/min distances,
    routes feeding critical shelters, and largest group size.
    Use this to understand how the optimization algorithm distributed evacuees.
    """
    ctx = _get_enriched_context()
    if not ctx:
        return "No simulation data available."

    routes = ctx.get("route_overview", {})
    if not routes:
        return "No route data available. The simulation may not have generated routes."

    lines = [
        "=== Evacuation Route Summary ===",
        "Total Routes: " + str(routes.get("total_routes", 0)),
        "Total People Routed: " + str(routes.get("total_people_routed", 0)),
        "Routes to Critical Shelters: " + str(routes.get("routes_to_critical_shelters", 0)),
        "Avg Distance: " + str(routes.get("avg_distance_m", 0)) + " m",
        "Max Distance: " + str(routes.get("max_distance_m", 0)) + " m",
        "Largest Group: " + str(routes.get("largest_group_size", 0)) + " people",
        "",
        "=== Top Evacuation Routes (by volume) ==="
    ]
    
    details = ctx.get("route_details", [])
    for i, r in enumerate(details):
        fb_tag = " [NON-NETWORK FALLBACK]" if r.get("fallback_route") else ""
        lines.append(f"{i+1}. Origin Node {r.get('origin_node')} → {r.get('to_shelter')}: {r.get('evacuees')} people ({r.get('distance_m')}m){fb_tag}")
        
    if not details:
        lines.append("(No individual route details available)")
        
    return "\n".join(lines)


@mcp.tool()
def get_terrain_analysis() -> str:
    """
    Get terrain analysis for the current simulation region.
    Returns the average elevation, max elevation, min elevation, and the number of nodes.
    This helps the AI understand the natural topography and predict where water will pool.
    """
    state = _load_state()
    if not state.get("summary_data"):
        return "No simulation data available. Run a simulation first."
        
    try:
        from region_manager import REGION_CACHE, norm_key
        hobli_name = state.get("hobli", "")
        key = norm_key(hobli_name)
        
        if key not in REGION_CACHE:
            return f"Region {hobli_name} is not currently actively cached in memory."
            
        G = REGION_CACHE[key]["G"]
        elevations = [data.get('elevation', 0) for _, data in G.nodes(data=True) if 'elevation' in data]
        
        if not elevations or sum(elevations) == 0.0:
            return f"Terrain analysis for {hobli_name}: Region is currently using flat 0.0m terrain."
            
        min_elev = min(elevations)
        max_elev = max(elevations)
        avg_elev = sum(elevations) / len(elevations)
        range_elev = max_elev - min_elev
        
        return (
            f"Terrain Analysis for {hobli_name} (Using OpenTopography SRTM DEM):\n"
            f"- Total Nodes Analyzed: {len(elevations)}\n"
            f"- Lowest Elevation: {min_elev:.1f} m (Risk: Water will severely pool in these valleys)\n"
            f"- Average Elevation: {avg_elev:.1f} m\n"
            f"- Highest Elevation: {max_elev:.1f} m (Risk: Safest natural ground)\n"
            f"- Total Relief (Range): {range_elev:.1f} m\n"
            f"Use this data to recommend directing evacuees toward Higher Elevation nodes during severe rains."
        )
    except Exception as e:
         return f"Error computing terrain statistics: {str(e)}"

@mcp.tool()
def analyze_road_conditions(road_name: str = "") -> str:
    """
    Call this tool to check if a specific road or junction is flooded, 
    or to get the top pressure junctures (bottlenecks).
    Provide the name of the road if asked about a specific one, otherwise leave empty.
    """
    print(f"[TOOL LOG] Executing analyze_road_conditions(road_name='{road_name}')", flush=True)
    ctx = _get_enriched_context()
    junctures = ctx.get("pressure_junctures", [])
    
    if not junctures:
        return "No significant pressure points or bottlenecks identified."
        
    if road_name:
        matches = [p for p in junctures if road_name.lower() in p.get("location_name", "").lower()]
        if not matches:
            return f"No critical bottlenecks found matching '{road_name}'. Plausible clear path."
        lines = [f"Status for roads matching '{road_name}':"]
        for p in matches:
            name = p.get('location_name', 'Unknown')
            lines.append(f"- {name}: {p.get('total_evacuees',0)} passing evacuees across {p.get('route_count',0)} routes. Flood depth: {p.get('flood_depth',0)} meters.")
        return "\n".join(lines)
    
    lines = ["=== Top Critical Pressure Junctures (Bottlenecks) ==="]
    for i, j in enumerate(junctures[:5]):
        lines.append(
            f"{i+1}. Location: {j.get('location_name', 'Unknown')}\n"
            f"   - Volume: {j['total_evacuees']} people over {j['route_count']} routes\n"
            f"   - Condition: {j['flood_depth']}m water depth"
        )
    return "\n".join(lines)


@mcp.tool()
def get_rescue_guidelines() -> str:
    """
    Call this tool when asked about safely rescuing people, NDRF instructions, or 
    handling populations that are at risk and could not be routed safely by the algorithm.
    """
    print("[TOOL LOG] Executing get_rescue_guidelines()", flush=True)
    state = _load_state()
    summary = state.get("summary_data", {})
    at_risk = summary.get("total_at_risk_remaining", 0)
    
    if at_risk == 0:
        return "All evacuees successfully mapped to safe shelters. No manual/NDRF rescue needed currently."
        
    return (
        f"Critical Rescue Guidelines for the {at_risk} unreachable individuals:\n"
        "1. Deploy NDRF High-Clearance Vehicles (HCV) and localized boat units immediately to deeply flooded nodes.\n"
        "2. Avoid any terrestrial rescue operations through bottlenecks marked with >0.5m flood depth.\n"
        "3. Initiate aerial (helicopter) lifts for coordinates surrounded entirely by impassable floodways."
    )

@mcp.tool()
def check_bus_availability(lat: float, lon: float) -> str:
    """
    Check for available bus stops and routes near a specific latitude and longitude coordinate.
    Call this when the user asks for buses or transit options at a localized coordinate.
    """
    print(f"[TOOL LOG] Executing check_bus_availability(lat={lat}, lon={lon})", flush=True)
    try:
        from genai.transport_gtfs_mcp_server import nearest_bus_stop, fetch_bus_details
        stops_info = nearest_bus_stop(lat, lon, top_n=2)
        details = fetch_bus_details(lat, lon)
        
        if "error" in details or not details.get('nearest_stop'):
            return "No bus stops or routes found within a reasonable distance of these coordinates."
            
        stop = details.get('nearest_stop', {})
        routes = details.get('routes', [])
        route_names = ", ".join([r['short_name'] for r in routes if r['short_name']])
        
        return (
            f"Nearest Bus Stop: {stop.get('name', 'Unknown')}\n"
            f"Distance: {stop.get('distance_km', 0)} km\n"
            f"Available Routes Serving This Stop: {route_names if route_names else 'No active routes'}"
        )
    except Exception as e:
        return f"Could not fetch bus availability: {str(e)}"

@mcp.tool()
def analyze_transit_disruptions(location_name: str, flood_depth_m: float) -> str:
    """
    Check which transit networks and bus routes will be disabled by a projected flood depth in a specific location.
    Call this when the user asks what networks are disabled by a flood in a specific zone.
    """
    print(f"[TOOL LOG] Executing analyze_transit_disruptions(location='{location_name}', depth={flood_depth_m})", flush=True)
    try:
        from genai.transport_gtfs_mcp_server import _read_csv, _routes_for_stop
        stops = _read_csv("stops.txt", ["stop_id", "stop_name"])
        matching_stops = [s for s in stops if location_name.lower() in s["stop_name"].lower()]
        
        if not matching_stops:
            return f"No major transit stops found matching '{location_name}'. Disruption minimal."
            
        disabled_routes = set()
        for s in matching_stops[:3]: # limit to 3 stops for perf
            routes = _routes_for_stop(s["stop_id"], max_routes=5)
            for r in routes:
                if r['short_name']: disabled_routes.add(r['short_name'])
                
        if not disabled_routes:
            return f"Stops in {location_name} are submerged under {flood_depth_m}m of water, but no active routes are currently scheduled."
            
        return (
            f"ALERT: A projected {flood_depth_m}m flood in {location_name} will severely disable the local transit network.\n"
            f"Affected Stops: {', '.join([s['stop_name'] for s in matching_stops[:3]])}\n"
            f"Disabled BMTC Routes: {', '.join(disabled_routes)}\n"
            f"Recommendation: Divert evacuation transport to fallback hubs outside this zone."
        )
    except Exception as e:
        return f"Could not analyze transit disruptions: {str(e)}"

@mcp.tool()
def identify_evacuation_hubs(zone_name: str) -> str:
    """
    Identify the primary evacuation hubs (safe shelters) for a specific flood zone.
    List their capacities, current occupancy, and readiness status.
    """
    print(f"[TOOL LOG] Executing identify_evacuation_hubs(zone_name='{zone_name}')", flush=True)
    ctx = _get_enriched_context()
    shelters = ctx.get("shelters", [])
    if not shelters:
        return "No shelter data available in the current simulation."
        
    matches = [s for s in shelters if zone_name.lower() in s.get("name", "").lower()]
    
    if not matches:
        sorted_hubs = sorted(shelters, key=lambda x: x.get("capacity", 0), reverse=True)
        hubs_to_report = sorted_hubs[:3]
        prefix = f"No specific hubs found strictly containing '{zone_name}'. Here are the primary evacuation hubs for the overall region:\n"
    else:
        hubs_to_report = matches
        prefix = f"Primary Evacuation Hubs for {zone_name}:\n"
        
    lines = [prefix]
    for h in hubs_to_report:
        lines.append(f"- {h.get('name')}: {h.get('occupancy')}/{h.get('capacity')} full (Status: {h.get('status')})")
        
    return "\n".join(lines)


@mcp.tool()
def narrate_best_route(destination_shelter: str = None) -> str:
    """
    Call this tool to find the safest, best, or optimal evacuation route.
    If the user asks about a specific shelter by name, provide it to filter the results.
    """
    print(f"[TOOL LOG] Executing narrate_best_route(destination_shelter={destination_shelter})", flush=True)
    ctx = _get_enriched_context()
    routes = ctx.get("route_details", [])
    if not routes:
        return "No enriched evacuation routes available to narrate."
    
    if destination_shelter:
        # Match against formatted shelter styles
        matched_routes = [r for r in routes if destination_shelter.lower() in r.get("to_shelter", "").lower()]
        routes = matched_routes
        if not routes:
            return f"No evacuation routes found leading to shelter matching '{destination_shelter}'."

    # Sort routes by lowest distance first
    routes_sorted = sorted(routes, key=lambda x: x.get("distance_m", float('inf')))
    best_route = routes_sorted[0] if routes_sorted else None
    
    if not best_route:
        return "No valid routes found."
        
    pop = best_route.get('evacuees')
    dest_name = best_route.get('to_shelter')
    dist = best_route.get('distance_m')
    
    return f"Best Route Details - Group Size: {pop} evacuees finding safety at {dest_name}. Distance traveled: {dist} meters. Proceed carefully focusing on minimizing traffic overlap. Check the Live Map to view the highlighted path."

@mcp.tool()
def generate_evacuation_strategy() -> str:
    """
    Generate a comprehensive evacuation strategy based on the current Digital Twin state.
    Uses Gemini to analyze the simulation data and produce a tactical plan including:
    - Priority shelter redirections (handling overloaded shelters)
    - Route load rebalancing (managing large evacuee groups)
    - Time-phased action steps (immediate vs secondary actions)
    Call this tool to get an overarching strategic plan for the crisis.
    """
    ctx = _get_enriched_context()
    if not ctx:
        return "No simulation data available. Run a simulation first."

    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_key_2 = os.getenv("GEMINI_API_KEY_2")

    if not gemini_key and not gemini_key_2:
        return "Error: Neither GEMINI_API_KEY nor GEMINI_API_KEY_2 is set in the environment."

    system_prompt = """You are the Chief Strategy Officer for a Digital Twin-Driven Flood Evacuation System.
Analyze the provided real-time simulation data and generate a comprehensive tactical evacuation strategy.

Your strategy MUST include exactly three sections:
1. **Priority Shelter Redirections**: Identify critically overloaded shelters and propose specific, mathematically viable redirections to shelters with remaining capacity. Use real capacity bounds and shelter names.
2. **Route Load Rebalancing**: Analyze the largest evacuee groups and potential bottlenecks. Suggest specific interventions (e.g., staggering departures, deploying extra transport, NDRF escorts) for these high-volume routes.
3. **Time-Phased Action Plan**: Provide a chronological step-by-step execution plan broken into Immediate (0-2 hours), Near-Term (2-6 hours), and Ongoing actions.

Rules:
- Base all recommendations STRICTLY on the numbers provided in the context.
- Use shelter names and exact evacuee/capacity numbers.
- Be concise, authoritative, and format with clear markdown headers and bullet points.
- Do NOT output preamble, just the three sections."""

    context_text = json.dumps(ctx, indent=2)
    prompt_text = f"Simulation Data:\n{context_text}\n\nGenerate the strategy:"

    # Primary: Gemini
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
            response = model.generate_content(prompt_text)
            return response.text if response.text else "Strategy generation returned an empty response."
        except Exception as e:
            if not gemini_key_2:
                return f"Error generating strategy via Gemini key 1: {e}"
            # Fall through to key 2

    # Fallback: Gemini key 2
    if gemini_key_2:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key_2)
            model2 = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
            response2 = model2.generate_content(prompt_text)
            return response2.text if response2.text else "Strategy generation returned an empty response."
        except Exception as e2:
            return f"Both Gemini keys failed. Key2 error: {e2}"

    return "Failed to generate strategy."

@mcp.tool()
def get_expert_analysis(persona: str) -> str:
    """
    Get AI expert analysis of the current evacuation state from one of three personas.

    Args:
        persona: One of 'logistics', 'tactical', or 'civic'.
                 - logistics: Shelter capacity analysis and resource allocation
                 - tactical: Route inspection and NDRF deployment instructions
                 - civic: Government situation reports and public warnings
    """
    import httpx

    ctx = _get_enriched_context()
    if not ctx:
        return "No simulation data available. Run a simulation first."

    valid = ["logistics", "tactical", "civic"]
    if persona.lower() not in valid:
        return "Invalid persona '" + persona + "'. Choose from: " + ", ".join(valid)

    # Call the existing REST endpoint (reuse the streaming logic)
    try:
        state = _load_state()
        response = httpx.post(
            "http://127.0.0.1:8000/expert-advice-stream",
            json={
                "persona": persona.lower(),
                "summary_data": state.get("summary_data", {}),
                "evacuation_plan": state.get("evacuation_plan", []),
            },
            timeout=60.0,
        )

        # Parse SSE response
        full_text = ""
        for line in response.text.split("\n\n"):
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:].strip())
                    full_text += data.get("text", "")
                except json.JSONDecodeError:
                    continue

        return full_text if full_text else "No response from expert."

    except Exception as e:
        return "Error connecting to expert panel: " + str(e)


@mcp.tool()
def ask_evacuation_question(question: str) -> str:
    """
    Ask a free-form question about the current evacuation simulation data.
    The AI will answer using only the available simulation context.

    Args:
        question: Any question about the evacuation, e.g.
                  "Why is Hebbal School overloaded?"
                  "Which route has the most evacuees?"
                  "What's the overall success rate?"
    """
    import httpx

    ctx = _get_enriched_context()
    if not ctx:
        return "No simulation data available. Run a simulation first."

    try:
        response = httpx.post(
            "http://127.0.0.1:8000/evacuation-chat",
            json={"question": question, "context": ctx},
            timeout=60.0,
        )

        full_text = ""
        for line in response.text.split("\n\n"):
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:].strip())
                    full_text += data.get("text", "")
                except json.JSONDecodeError:
                    continue

        return full_text if full_text else "No response received."

    except Exception as e:
        return "Error: " + str(e)


# ══════════════════════════════════════════════════════════════════════════════
#  MCP RESOURCES (read-only data the agent can inspect)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.resource("evacuation://simulation/summary")
def simulation_summary_resource() -> str:
    """The raw simulation summary as JSON."""
    state = _load_state()
    if not state.get("summary_data"):
        return json.dumps({"status": "no simulation data"})
    return json.dumps(state["summary_data"], indent=2)


@mcp.resource("evacuation://simulation/context")
def enriched_context_resource() -> str:
    """The enriched context (with shelter severity, route stats) as JSON."""
    ctx = _get_enriched_context()
    if not ctx:
        return json.dumps({"status": "no simulation data"})
    return json.dumps(ctx, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
#  Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Starting Urban Flood Evacuation AI MCP Server...")
    print("Tools: get_simulation_state, get_shelter_status, get_route_summary,")
    print("       get_expert_analysis, ask_evacuation_question")
    print("Resources: evacuation://simulation/summary, evacuation://simulation/context")
    mcp.run()
