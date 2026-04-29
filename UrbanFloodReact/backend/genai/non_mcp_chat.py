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

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

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


async def analyze_no_mcp(question: str, enriched_context: dict) -> dict:
    """
    Run the non-MCP baseline: cleaned full context dump + all parameter-less tool
    outputs materialized as static text. No tool-calling capability.

    The LLM receives the same underlying data as the MCP arm (which fetches it via
    tools), but in one large upfront dump rather than on-demand queries.

    Returns:
        {
          "mode": "non_mcp",
          "response_text": str,
          "prompt_chars": int,
          "response_chars": int,
          "prompt_words": int,
          "response_words": int,
          "latency_s": float,
          "tool_calls": [],         # always empty for non-MCP
          "tool_call_count": 0,
          "error": str | None,
        }
    """
    tool_dump   = _materialize_tool_dump()
    context_str = json.dumps(_clean_context(enriched_context), indent=2)

    user_prompt = (
        f"=== SIMULATION CONTEXT (full data dump) ===\n{context_str}\n\n"
        f"=== PRE-MATERIALIZED TOOL DATA (read-only briefing) ===\n{tool_dump}\n\n"
        f"=== USER QUESTION ===\n{question}\n"
    )

    result = {
        "mode": "non_mcp",
        "response_text": "",
        "prompt_chars": len(user_prompt),
        "response_chars": 0,
        "prompt_words": len(user_prompt.split()),
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

    try:
        prompt = f"""You are an AI disaster response assistant. Answer the user's question based ONLY on the following context.
        
Context:
{context_str}

Question: {question}
"""

        model = genai.GenerativeModel("gemini-2.5-flash")

        start_time = time.time()
        try:
            response = model.generate_content(prompt)
            text = response.text
            model_used = "gemini-2.5-flash"
        except Exception as e:
            print(f"Gemini failed for non-MCP, falling back to Groq: {e}")
            try:
                groq_client = _get_groq_client()
                if groq_client:
                    groq_resp = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": "You are a helpful AI disaster response assistant."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2,
                        max_tokens=1000,
                    )
                    text = groq_resp.choices[0].message.content
                    model_used = "llama-3.3-70b-versatile"
                else:
                    text = f"Error: Both Gemini and Groq failed. Gemini Error: {e}, Groq API key not available."
                    model_used = "error"
            except Exception as groq_e:
                text = f"Error generating response natively. Gemini Error: {e}, Groq Error: {groq_e}"
                model_used = "error"

        end_time = time.time()

        # Update result dict with response
        result["response_text"] = text
        result["response_chars"] = len(text)
        result["response_words"] = len(text.split())
        result["latency_s"] = end_time - start_time
        result["tool_call_count"] = 0
        result["tool_calls"] = []

        return result

    except Exception as e:
        result["error"] = str(e)

    return result
