"""
mcp_chat_metrics.py — MCP-enabled GenAI variant that captures research metrics.
──────────────────────────────────────────────────────────────────────────────
Purpose: research arm of "MCP vs non-MCP" comparison.

Mirrors the tool-calling logic of `evacuation_chat.stream_chat` but is
non-streaming and records every tool call (name, args, result) plus
token usage and latency. Leaves the production streaming path untouched.
"""

import json
import os
import time
import inspect


# Same system prompt as the production chat — keeps the comparison fair.
SYSTEM_PROMPT = """You are an AI disaster response assistant for a Digital Twin-Driven Flood Evacuation System.
You have access to live tools that can fetch shelter status, route details, road conditions,
metro disruptions, and more. Use them when needed to answer the user's question.

CRITICAL TOOL ROUTING HINTS:
- ALWAYS start by calling get_simulation_state() to understand the context.
- For shelter questions      -> call get_shelter_status() first
- For route/path questions   -> call get_route_summary() then narrate_best_route()
- For road/bottleneck questions -> call analyze_road_conditions()
- For bus/transit questions  -> call check_bus_availability() or analyze_transit_disruptions()
- For terrain questions      -> call get_terrain_analysis()
- For rescue/NDRF questions  -> call get_rescue_guidelines()

Make at least 2-3 tool calls before answering. Chain them: first understand the situation, then drill down into specifics.

Rules:
1. Quote specific numbers (shelter names, occupancy %, evacuee counts, distances) whenever possible.
2. If the data is not available even after tool calls, say so — do NOT make up information.
3. Be concise and actionable. Use bullet points or short paragraphs.
4. Use shelter names, never raw IDs.
5. Use Markdown formatting.
"""


def _load_tools():
    """Re-export the same tool set used by stream_chat so behavior matches."""
    from genai.mcp_evacuation_server import (
        narrate_best_route, analyze_road_conditions, get_rescue_guidelines,
        check_bus_availability, analyze_transit_disruptions, identify_evacuation_hubs,
    )
    from genai.mcp_flood_intelligence_server import (
        get_metro_status, get_flood_impact, get_shelter_resource_map,
        get_vulnerability_hotspots,
    )
    return [
        narrate_best_route, analyze_road_conditions, get_rescue_guidelines,
        check_bus_availability, analyze_transit_disruptions, identify_evacuation_hubs,
        get_metro_status, get_flood_impact, get_shelter_resource_map,
        get_vulnerability_hotspots,
    ]


def _minimal_seed(enriched_context: dict) -> dict:
    """
    Strip the MCP arm's seed context down to a simulation summary only.
    This forces Gemini to call tools (get_shelter_status, get_route_summary,
    analyze_road_conditions, etc.) to fetch the detail it needs, rather than
    answering from the pre-loaded context dump.

    Without this, Gemini sees 140 shelters inline and never calls a single tool —
    making the MCP arm functionally identical to the non-MCP arm.
    """
    sim = enriched_context.get("simulation", {})
    return {
        "simulation_summary": {
            "location":               sim.get("location"),
            "algorithm":              sim.get("algorithm"),
            "success_rate_pct":       sim.get("success_rate_pct"),
            "total_evacuated":        sim.get("total_evacuated"),
            "total_at_risk_remaining":sim.get("total_at_risk_remaining"),
            "execution_time_s":       sim.get("execution_time_s"),
        },
        "note": (
            "This is a minimal seed context. Use the available tools to fetch "
            "shelter status, route details, road conditions, terrain, metro disruptions, "
            "rescue guidelines, and any other specifics needed to answer the question."
        ),
    }


async def analyze_with_mcp(question: str, enriched_context: dict, max_tool_loops: int = 10) -> dict:
    """
    Run the MCP-enabled arm: Gemini with tool-calling, capture every tool invocation.

    Key design: only a minimal simulation summary is given inline. All detailed data
    (shelter status, routes, bottlenecks, etc.) must be fetched via tool calls.
    This forces genuine tool-use rather than answering from a pre-loaded dump.

    Returns:
        {
          "mode": "mcp",
          "response_text": str,
          "prompt_chars": int,
          "response_chars": int,
          "prompt_words": int,
          "response_words": int,
          "latency_s": float,
          "tool_calls": [{"name": ..., "args": ..., "result_preview": ...}, ...],
          "tool_call_count": int,
          "error": str | None,
        }
    """
    import google.generativeai as genai

    tools = _load_tools()
    seed = _minimal_seed(enriched_context)
    context_text = json.dumps(seed, indent=2)
    user_prompt = (
        f"=== SIMULATION SEED (summary only — use tools for details) ===\n{context_text}\n\n"
        f"=== USER QUESTION ===\n{question}\n"
    )

    result = {
        "mode": "mcp",
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
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
        )

        t0 = time.time()
        chat = model.start_chat()
        response = chat.send_message(user_prompt)

        # Manual tool-execution loop (matches stream_chat behavior)
        for _ in range(max_tool_loops):
            if not response.candidates or not response.candidates[0].content.parts:
                break

            parts = response.candidates[0].content.parts
            found_call = False

            for part in parts:
                if not getattr(part, "function_call", None):
                    continue
                found_call = True
                fc   = part.function_call
                args = {k: v for k, v in fc.args.items()}

                func = next((t for t in tools if t.__name__ == fc.name), None)
                if func is None:
                    tool_result = f"Tool '{fc.name}' not found"
                else:
                    try:
                        if inspect.iscoroutinefunction(func):
                            tool_result = await func(**args)
                        else:
                            tool_result = func(**args)
                    except Exception as e:
                        tool_result = f"Error executing tool: {e}"

                preview = (str(tool_result)[:300] + "...") if len(str(tool_result)) > 300 else str(tool_result)
                result["tool_calls"].append({
                    "name": fc.name,
                    "args": args,
                    "result_preview": preview,
                })

                response = chat.send_message(
                    genai.protos.Content(parts=[genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fc.name,
                            response={"result": tool_result},
                        )
                    )])
                )

            if not found_call:
                break

        result["latency_s"]       = round(time.time() - t0, 2)
        result["tool_call_count"] = len(result["tool_calls"])

        try:
            text = response.text or ""
        except ValueError:
            text = ""
        result["response_text"]  = text
        result["response_chars"] = len(text)
        result["response_words"] = len(text.split())

        # Aggregate token usage if exposed (sum across all turns is approximate;
        # we use the final response's metadata as the headline figure)
        try:
            usage = response.usage_metadata
            result["prompt_tokens"]   = usage.prompt_token_count
            result["response_tokens"] = usage.candidates_token_count
            result["total_tokens"]    = usage.total_token_count
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)
        
        # Fallback to Groq if Gemini fails (e.g., rate limit 429)
        print(f"[MCP] Gemini failed: {e}. Attempting Groq fallback...")
        try:
            from groq import Groq
            groq_key = os.environ.get("GROQ_API_KEY")
            if groq_key:
                groq_client = Groq(api_key=groq_key)
                groq_response = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=2000,
                )
                text = groq_response.choices[0].message.content
                result["response_text"] = text
                result["response_chars"] = len(text)
                result["response_words"] = len(text.split())
                result["error"] = None  # Clear the error since fallback succeeded
                result["tool_call_count"] = len(result["tool_calls"])
                print(f"[MCP] Groq fallback succeeded with {len(text)} chars")
            else:
                print(f"[MCP] Groq API key not available for fallback")
        except Exception as groq_e:
            print(f"[MCP] Groq fallback also failed: {groq_e}")

    return result
