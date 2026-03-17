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
    5. get_route_summary       — Statistics about computed evacuation routes
"""

import sys
import os
import json

# Add parent directory (backend/) to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
try:
    from genai.context_builder import build_expert_context
except ImportError:
    from context_builder import build_expert_context

# ── Create MCP Server ─────────────────────────────────────────────────────────
mcp = FastMCP("Urban Flood Evacuation AI Server")

# ── Shared state file ──────────────────────────────────────────────────────────
# Both FastAPI (writer) and MCP server (reader) use this file.
# This solves the cross-process state problem — no shared memory needed.
_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_state.json")


def update_state(summary_data: dict, evacuation_plan: list = None, hobli: str = None):
    """Write the latest simulation results to the shared state file on disk."""
    state = {
        "summary_data": summary_data,
        "evacuation_plan": evacuation_plan or [],
        "hobli": hobli or "",
    }
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _load_state() -> dict:
    """Read the latest simulation state from disk. Returns empty dict if no file."""
    try:
        with open(_STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"summary_data": None, "evacuation_plan": None, "hobli": None}


def _get_enriched_context() -> dict:
    """Build enriched context from the latest simulation state on disk."""
    state = _load_state()
    if not state.get("summary_data"):
        return {}
    return build_expert_context(
        state["summary_data"],
        state.get("evacuation_plan"),
    )


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

    routes = ctx.get("routes", {})
    if not routes:
        return "No route data available. The simulation may not have generated routes."

    lines = [
        "=== Evacuation Route Summary ===",
        "Total Routes: " + str(routes.get("total_routes", 0)),
        "Total People Routed: " + str(routes.get("total_people_routed", 0)),
        "Routes to Critical Shelters: " + str(routes.get("routes_to_critical_shelters", 0)),
        "Avg Distance: " + str(routes.get("avg_distance_m", 0)) + " m",
        "Max Distance: " + str(routes.get("max_distance_m", 0)) + " m",
        "Min Distance: " + str(routes.get("min_distance_m", 0)) + " m",
        "Largest Group: " + str(routes.get("largest_group_size", 0)) + " people",
    ]
    return "\n".join(lines)


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
