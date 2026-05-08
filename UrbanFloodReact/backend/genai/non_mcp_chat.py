"""
non_mcp_chat.py — Baseline GenAI variant that does NOT use MCP tools.
─────────────────────────────────────────────────────────────────────
Purpose: research baseline for "MCP vs non-MCP" comparison.

Design (rigorous A/B):
  - The LLM receives the EXACT same baseline context as the MCP variant,
    PLUS a pre-materialized dump of every parameter-less MCP tool's output.
  - No `tools=` argument is given to Gemini, so the model cannot make
    on-demand queries. It must answer purely from the static dump.
  - This isolates the variable: same information, same model — only
    retrieval mechanism differs (on-demand vs upfront dump).

The function is non-streaming and returns full metrics so the research
harness can compare token counts, latency, and response content.
"""

import google.generativeai as genai
import json
import time
from groq import Groq
import os

# Lazy initialization of Groq client to avoid errors when API key is not set
_groq_client = None

def _get_groq_client():
    """Get or initialize Groq client lazily."""
    global _groq_client
    if _groq_client is None:
        groq_key = os.environ.get("GROQ_API_KEY")
        if groq_key:
            _groq_client = Groq(api_key=groq_key)
    return _groq_client


# All parameter-less tools we can pre-materialize.
# Parameterised tools (check_bus_availability, identify_evacuation_hubs,
# analyze_transit_disruptions) cannot be pre-dumped without inventing args,
# so they are deliberately omitted — this is the legitimate cost of not
# having a tool-calling agent.
def _materialize_tool_dump() -> str:
    """Call every parameter-less MCP tool and concatenate output as one block."""
    sections = []

    def _try(label, fn, *args, **kwargs):
        try:
            import inspect
            if inspect.iscoroutinefunction(fn):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Already inside async context — schedule and wait via thread
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                            out = ex.submit(asyncio.run, fn(*args, **kwargs)).result()
                    else:
                        out = loop.run_until_complete(fn(*args, **kwargs))
                except RuntimeError:
                    out = asyncio.run(fn(*args, **kwargs))
            else:
                out = fn(*args, **kwargs)
            sections.append(f"### {label}\n{out}")
        except Exception as e:
            sections.append(f"### {label}\n(unavailable: {e})")

    try:
        from genai.mcp_evacuation_server import (
            get_simulation_state, get_shelter_status, get_route_summary,
            get_terrain_analysis, analyze_road_conditions, get_rescue_guidelines,
            narrate_best_route,
        )
        _try("CURRENT SIMULATION STATE", get_simulation_state)
        _try("SHELTER STATUS REPORT",    get_shelter_status)
        _try("EVACUATION ROUTE SUMMARY", get_route_summary)
        _try("TERRAIN ANALYSIS",         get_terrain_analysis)
        _try("PRESSURE JUNCTURES (BOTTLENECKS)",  analyze_road_conditions, "")
        _try("RESCUE GUIDELINES",        get_rescue_guidelines)
        _try("BEST EVACUATION ROUTE",    narrate_best_route)
    except ImportError as e:
        sections.append(f"(mcp_evacuation_server import failed: {e})")

    try:
        from genai.mcp_flood_intelligence_server import (
            get_metro_status, get_flood_impact, get_vulnerability_hotspots,
            get_shelter_resource_map,
        )
        _try("METRO STATUS",             get_metro_status, "")
        _try("FLOOD IMPACT SUMMARY",     get_flood_impact)
        _try("VULNERABILITY HOTSPOTS",   get_vulnerability_hotspots, 0.15)
        _try("SHELTER RESOURCE MAP",     get_shelter_resource_map)
    except ImportError as e:
        sections.append(f"(mcp_flood_intelligence_server import failed: {e})")

    return "\n\n".join(sections)


SYSTEM_PROMPT = """You are an AI disaster response assistant for a Digital Twin-Driven Flood Evacuation System.
You have been given a comprehensive briefing of the current simulation state below, including
shelter status, route summary, pressure junctures, terrain, metro status, flood impact, and
vulnerability hotspots. Answer the user's question using ONLY the data in this briefing.

Rules:
1. Quote specific numbers (shelter names, occupancy %, evacuee counts, distances) whenever possible.
2. If the answer is not in the provided data, say so — do NOT make up information.
3. Be concise and actionable. Use bullet points or short paragraphs.
4. Use shelter names, never raw IDs.
5. Use Markdown formatting.
"""


def _clean_context(enriched_context: dict) -> dict:
    """
    Strip keys that cause hallucination in general Q&A:
      - local_inventory: 200 fire-station/hospital resource items intended only
        for the logistics expert panel. The model confuses supply-source addresses
        with shelter destinations, fabricating recommendations from irrelevant data.
      - _data_notes: internal prompt-engineering notes not needed for Q&A.

    Both MCP and non-MCP arms receive this cleaned context so the only variable
    being studied is the retrieval mechanism, not the noise level.
    """
    drop_keys = {"local_inventory", "_data_notes"}
    return {k: v for k, v in enriched_context.items() if k not in drop_keys}


def _trim_context_for_groq(enriched_context: dict) -> dict:
    """
    Aggressively trim context to fit Groq's ~6K token safe limit.
    Keeps simulation summary, top-20 shelters, top-5 routes, top-3 junctures.
    Drops route_details (large), local_inventory, shelter_overview raw lists.
    """
    trimmed = {
        "simulation":         enriched_context.get("simulation", {}),
        "shelter_overview":   enriched_context.get("shelter_overview", {}),
        "route_overview":     enriched_context.get("route_overview", {}),
        "shelters":           enriched_context.get("shelters", [])[:20],
        "pressure_junctures": enriched_context.get("pressure_junctures", [])[:3],
        "route_details":      enriched_context.get("route_details", [])[:5],
    }
    return trimmed


async def analyze_no_mcp(question: str, enriched_context: dict) -> dict:
    """
    Run the non-MCP baseline: cleaned full context dump + all parameter-less tool
    outputs materialized as static text. No tool-calling capability.

    The LLM receives the same underlying data as the MCP arm (which fetches it via
    tools), but in one large upfront dump rather than on-demand queries.

    Returns:
        {
          "mode": "non_mcp",
          "provider": "gemini" | "groq",
          "response_text": str,
          "prompt_words": int,
          "response_words": int,
          "latency_s": float,
          "tool_calls": [],
          "tool_call_count": 0,
          "error": str | None,
        }
    """
    tool_dump   = _materialize_tool_dump()
    context_str = json.dumps(_clean_context(enriched_context), indent=2)

    # This is the full prompt — same one sent to both Gemini and (trimmed) Groq
    full_prompt = (
        f"=== SIMULATION CONTEXT (full data dump) ===\n{context_str}\n\n"
        f"=== PRE-MATERIALIZED TOOL DATA (read-only briefing) ===\n{tool_dump}\n\n"
        f"=== USER QUESTION ===\n{question}\n"
    )

    result = {
        "mode": "non_mcp",
        "provider": None,
        "response_text": "",
        "prompt_chars": len(full_prompt),
        "response_chars": 0,
        "prompt_words": len(full_prompt.split()),
        "response_words": 0,
        "latency_s": 0.0,
        "tool_calls": [],
        "tool_call_count": 0,
        "error": None,
    }

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        result["error"] = "GEMINI_API_KEY not set"
        return result

    t0 = time.time()  # Start timing before any provider attempt

    # ── Primary: Gemini 2.5 Flash ──────────────────────────────────────────────
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(full_prompt)
        text = response.text or ""
        result["provider"] = "gemini"
    except Exception as gemini_err:
        print(f"Gemini failed for non-MCP, falling back to Groq: {gemini_err}")

        # ── Fallback: Groq with trimmed context ────────────────────────────────
        # Groq has a smaller context limit (~8K tokens) so we trim the context.
        # The trimmed version retains top-50 shelters, top-10 routes, top-3 junctures.
        groq_context_str = json.dumps(
            _trim_context_for_groq(_clean_context(enriched_context)), indent=2
        )
        # Groq limit ~8K tokens: drop the tool dump (3K+ words) entirely —
        # the trimmed context already contains the same data inline.
        groq_prompt = (
            f"=== SIMULATION CONTEXT (trimmed for context limit) ===\n{groq_context_str}\n\n"
            f"=== USER QUESTION ===\n{question}\n"
        )

        try:
            groq_client = _get_groq_client()
            if groq_client:
                import groq as groq_lib
                import asyncio
                delay = 10
                for attempt in range(2):
                    try:
                        groq_resp = groq_client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user",   "content": groq_prompt},
                            ],
                            temperature=0.2,
                            max_tokens=1500,
                        )
                        break
                    except groq_lib.RateLimitError as e:
                        if "tokens per day" in str(e) or attempt == 1:
                            raise
                        print(f"[non-MCP] Groq 429 — backing off {delay}s")
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30)
                text = groq_resp.choices[0].message.content or ""
                result["provider"] = "groq"
                result["prompt_words"] = len(groq_prompt.split())
                result["prompt_chars"] = len(groq_prompt)
            else:
                result["error"] = f"Gemini failed and GROQ_API_KEY not set. Gemini error: {gemini_err}"
                result["latency_s"] = round(time.time() - t0, 2)
                return result
        except Exception as groq_err:
            result["error"] = f"Both providers failed. Gemini: {gemini_err} | Groq: {groq_err}"
            result["latency_s"] = round(time.time() - t0, 2)
            return result

    result["latency_s"]    = round(time.time() - t0, 2)
    result["response_text"]  = text
    result["response_chars"] = len(text)
    result["response_words"] = len(text.split())
    return result
