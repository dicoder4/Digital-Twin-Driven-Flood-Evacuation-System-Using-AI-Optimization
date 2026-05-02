"""
mcp_chat_metrics.py — MCP-enabled GenAI variant that captures research metrics.
──────────────────────────────────────────────────────────────────────────────
Purpose: research arm of "MCP vs non-MCP" comparison.

Mirrors the tool-calling logic of `evacuation_chat.stream_chat` but is
non-streaming and records every tool call (name, args, result) plus
token usage and latency. Leaves the production streaming path untouched.
"""

import asyncio
import json
import os
import time
import inspect
from typing import Any


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


def _tools_to_openai_schema(tools: list) -> list[dict]:
    """Convert Python tool functions to OpenAI JSON schema format for Groq."""
    PY_TO_JSON = {"str": "string", "float": "number", "int": "integer", "bool": "boolean"}
    schemas = []
    for fn in tools:
        sig = inspect.signature(fn)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            ann = param.annotation
            json_type = PY_TO_JSON.get(ann.__name__ if hasattr(ann, "__name__") else "", "string")
            properties[name] = {"type": json_type}
            doc_line = next(
                (l.strip() for l in (fn.__doc__ or "").splitlines()
                 if name.lower() in l.lower() and ":" in l), None
            )
            if doc_line:
                properties[name]["description"] = doc_line
            if param.default is inspect.Parameter.empty:
                required.append(name)
        schemas.append({
            "type": "function",
            "function": {
                "name": fn.__name__,
                "description": (fn.__doc__ or "").strip().split("\n")[0],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    **({"required": required} if required else {}),
                },
            },
        })
    return schemas


async def _groq_create_with_retry(groq_client: Any, max_retries: int = 4, **kwargs) -> Any:
    """Call groq_client.chat.completions.create with exponential backoff on 429."""
    import groq as groq_lib
    delay = 15
    for attempt in range(max_retries):
        try:
            return groq_client.chat.completions.create(**kwargs)
        except groq_lib.RateLimitError:
            if attempt == max_retries - 1:
                raise
            print(f"[MCP] Groq 429 — backing off {delay}s (attempt {attempt+1}/{max_retries})")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)


def _fill_tool_defaults(fn_name: str, args: dict, enriched_context: dict) -> dict:
    """Fill missing required args with sensible defaults from the simulation context."""
    if fn_name == "analyze_transit_disruptions":
        sim = enriched_context.get("simulation", {})
        if not args.get("location_name"):
            args["location_name"] = sim.get("location", "Bengaluru")
        if args.get("flood_depth_m") is None:
            args["flood_depth_m"] = 0.3
    if fn_name == "check_bus_availability":
        sim = enriched_context.get("simulation", {})
        if args.get("lat") is None or args.get("lon") is None:
            # Use centroid of Bengaluru if not provided
            args.setdefault("lat", 12.9716)
            args.setdefault("lon", 77.5946)
    if fn_name == "identify_evacuation_hubs":
        sim = enriched_context.get("simulation", {})
        if not args.get("zone_name"):
            args["zone_name"] = sim.get("location", "")
    return args


async def _run_groq_tool_loop(
    groq_client: Any,
    tools: list,
    user_prompt: str,
    result: dict,
    enriched_context: dict,
    max_loops: int = 10,
) -> str:
    """
    Full OpenAI-format tool-calling loop for Groq with retry on 429.
    Mirrors the Gemini loop: send → execute tools → feed results back → repeat.
    """
    tool_schemas = _tools_to_openai_schema(tools)
    tool_map = {fn.__name__: fn for fn in tools}

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    for _ in range(max_loops):
        resp = await _groq_create_with_retry(
            groq_client,
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=tool_schemas,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=2000,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            args = _fill_tool_defaults(fn_name, args, enriched_context)

            func = tool_map.get(fn_name)
            if func is None:
                tool_result = f"Tool '{fn_name}' not found"
            else:
                try:
                    if inspect.iscoroutinefunction(func):
                        tool_result = await func(**args)
                    else:
                        tool_result = func(**args)
                except Exception as e:
                    tool_result = f"Error executing tool: {e}"

            preview = (str(tool_result)[:300] + "...") if len(str(tool_result)) > 300 else str(tool_result)
            result["tool_calls"].append({"name": fn_name, "args": args, "result_preview": preview})

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(tool_result),
            })

    # Max loops reached — ask for final answer
    messages.append({"role": "user", "content": "Please summarize your findings based on the tool results above."})
    final = await _groq_create_with_retry(
        groq_client,
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.2,
        max_tokens=2000,
    )
    return final.choices[0].message.content or ""


def _load_tools():
    """Full tool set — includes parameter-less discovery tools + parameterised query tools."""
    from genai.mcp_evacuation_server import (
        get_simulation_state, get_shelter_status, get_route_summary,
        get_terrain_analysis, narrate_best_route, analyze_road_conditions,
        get_rescue_guidelines, check_bus_availability, analyze_transit_disruptions,
        identify_evacuation_hubs,
    )
    from genai.mcp_flood_intelligence_server import (
        get_metro_status, get_flood_impact, get_shelter_resource_map,
        get_vulnerability_hotspots,
    )
    return [
        get_simulation_state, get_shelter_status, get_route_summary,
        get_terrain_analysis, narrate_best_route, analyze_road_conditions,
        get_rescue_guidelines, check_bus_availability, analyze_transit_disruptions,
        identify_evacuation_hubs, get_metro_status, get_flood_impact,
        get_shelter_resource_map, get_vulnerability_hotspots,
    ]


def _minimal_seed(enriched_context: dict) -> dict:
    """
    Strip the MCP arm's seed context to simulation summary + shelter overview only.
    This forces Gemini to call tools (get_shelter_status, get_route_summary,
    analyze_road_conditions, etc.) to fetch the detail it needs, rather than
    answering from the pre-loaded context dump.

    Includes shelter_overview to help the model select appropriate tools, but NOT
    the full shelter list (which would make tools redundant).

    Without this, Gemini sees 140 shelters inline and never calls a single tool —
    making the MCP arm functionally identical to the non-MCP arm.
    """
    sim = enriched_context.get("simulation", {})
    overview = enriched_context.get("shelter_overview", {})
    return {
        "simulation_summary": {
            "location":               sim.get("location"),
            "algorithm":              sim.get("algorithm"),
            "success_rate_pct":       sim.get("success_rate_pct"),
            "total_evacuated":        sim.get("total_evacuated"),
            "total_at_risk_remaining":sim.get("total_at_risk_remaining"),
            "execution_time_s":       sim.get("execution_time_s"),
        },
        "shelter_overview": overview,  # High-level counts only, NOT full shelter list
        "available_tools": [
            "get_simulation_state", "get_shelter_status", "get_route_summary",
            "get_terrain_analysis", "analyze_road_conditions", "get_rescue_guidelines",
            "narrate_best_route", "get_metro_status", "get_flood_impact",
            "get_vulnerability_hotspots", "check_bus_availability", "analyze_transit_disruptions"
        ]
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

    t0 = time.time()

    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
            tools=tools,
        )

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
        result["provider"]        = "gemini"

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
        
        # Fallback to Groq with full tool-calling loop
        print(f"[MCP] Gemini failed: {e}. Attempting Groq tool-calling fallback...")
        try:
            from groq import Groq
            groq_key = os.environ.get("GROQ_API_KEY")
            if groq_key:
                groq_client = Groq(api_key=groq_key)
                text = await _run_groq_tool_loop(groq_client, tools, user_prompt, result, enriched_context)
                result["response_text"]  = text
                result["response_chars"] = len(text)
                result["response_words"] = len(text.split())
                result["tool_call_count"] = len(result["tool_calls"])
                result["error"] = None
                result["provider"] = "groq"
                result["latency_s"] = round(time.time() - t0, 2)
                print(f"[MCP] Groq tool-calling fallback succeeded: {result['tool_call_count']} tools, {len(text)} chars")
            else:
                print("[MCP] Groq API key not available for fallback")
        except Exception as groq_e:
            result["latency_s"] = round(time.time() - t0, 2)
            print(f"[MCP] Groq fallback also failed: {groq_e}")

    return result
