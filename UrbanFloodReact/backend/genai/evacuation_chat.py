"""
evacuation_chat.py — Free-form NL chat about evacuation data
────────────────────────────────────────────────────────────
Streaming endpoint: takes a user question + enriched context,
returns a grounded answer via Gemini 2.5 Flash (fallback to Groq).
"""

import json
import os
import httpx

CHAT_SYSTEM_PROMPT = """You are an AI disaster response assistant for a Digital Twin-Driven Flood Evacuation System.
You have access to the real-time simulation data provided below. Your job is to answer the user's question
concisely and accurately using ONLY the data from the provided context.

Rules:
1. Quote specific numbers (shelter names, occupancy percentages, evacuee counts, distances) whenever possible.
2. If the answer is not in the provided data, say so clearly — do NOT make up information.
3. Keep responses concise and actionable. Use bullet points or short paragraphs.
4. If in 'compare' mode (multiple algorithm results), compare GA, ACO, and PSO metrics clearly. Explain which performed best (lowest fitness/highest success) and why.
5. Do NOT explain your reasoning process. Just give the answer.
6. When referring to shelters, use their names, not IDs.
7. Use Markdown for formatting (bold, tables, etc.).

Context structure guide:
- `route_details`: Each entry = one evacuation group (cluster of people routed to one shelter).
  Fields: origin_node, to_shelter, evacuees (group size), distance_m, path_points (waypoints), fallback_route.
  Sorted by evacuees descending — the first entry is the largest evacuation group.
- `pressure_junctures`: Critical bottlenecks detected in the road network.
  Fields: node_id, location_name, lat, lon, total_evacuees, route_count, flood_depth.
  Use 'location_name' to provide specific street/junction names to the user.
- `shelters_by_inflow`: Shelters ranked by total evacuees received (sum of all routes to that shelter).
- `route_overview`: Aggregated route stats (total routes, avg/max distance, fallback count).
- `shelters`: Per-shelter occupancy, capacity, and status (CRITICAL / HIGH / MODERATE / EMPTY).

What you CANNOT answer from this data (be explicit if asked):
- Specific per-second traffic delays (TomTom gives real-time, but only the aggregate routing is used here).
For these, suggest users look at the Live Map for visual street-level labels.

IMPORTANT: You also have access to the "OFFICIAL RELIEF STANDARDS (Govt of Karnataka)". 
If the user asks about resource needs (Water, Food, Toilets), use these strict standards:
- 3 Liters/person/day for drinking.
- 15-20 Liters/person/day for hygiene.
- 1 Toilet per 30 persons.
- 3.5 sq.m shelter area per person.
"""


def _load_guidelines_text() -> str:
    """Helper to load guidelines for the chat context."""
    try:
        from genai.expert_panel import get_resource_guidelines
        return get_resource_guidelines()
    except ImportError:
        return ""

from genai.mcp_evacuation_server import (
    narrate_best_route,
    analyze_road_conditions,
    get_rescue_guidelines,
    check_bus_availability,
    analyze_transit_disruptions,
    identify_evacuation_hubs
)

from genai.mcp_flood_intelligence_server import (
    get_metro_status as _flood_intel_metro,
    get_flood_impact as _flood_intel_impact,
    get_shelter_resource_map as _flood_intel_resources,
    get_vulnerability_hotspots as _flood_intel_hotspots
)

AGENT_TOOLS = [
    narrate_best_route, 
    analyze_road_conditions, 
    get_rescue_guidelines,
    check_bus_availability,
    analyze_transit_disruptions,
    identify_evacuation_hubs,
    _flood_intel_metro,
    _flood_intel_impact,
    _flood_intel_resources,
    _flood_intel_hotspots,
]

async def stream_chat(question: str, context_data: dict):
    """
    Stream an answer to a free-form user question about the evacuation.
    Primary: Gemini 2.5 Flash (GEMINI_API_KEY)  →  Fallback: Gemini 2.5 Flash (GEMINI_API_KEY_2).
    """
    # 1. Load Standards
    guidelines_text = _load_guidelines_text()

    # 2. Build Context
    context_text = json.dumps(context_data, indent=2)
    user_prompt = f"""
Evacuation Context:
{context_text}

{guidelines_text}

User Question: {question}
"""
    nl = "\n\n"

    # ── Primary: Gemini 2.5 Flash ─────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            import inspect
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=CHAT_SYSTEM_PROMPT,
                tools=AGENT_TOOLS
            )
            
            # Manual execution loop to support async tools
            chat = model.start_chat()
            response = chat.send_message(user_prompt)

            for i in range(10):
                if not response.candidates or not response.candidates[0].content.parts:
                    break
                
                parts = response.candidates[0].content.parts
                found_call = False
                for part in parts:
                    if part.function_call:
                        found_call = True
                        fc = part.function_call
                        args = {k: v for k, v in fc.args.items()}
                        
                        # Find the tool function
                        func = None
                        for t in AGENT_TOOLS:
                            if t.__name__ == fc.name:
                                func = t
                                break
                        
                        if func:
                            try:
                                # Handle both sync and async tools
                                if inspect.iscoroutinefunction(func):
                                    result = await func(**args)
                                else:
                                    result = func(**args)
                            except Exception as e:
                                result = f"Error executing tool: {e}"
                            
                            response = chat.send_message(
                                genai.protos.Content(
                                    parts=[genai.protos.Part(
                                        function_response=genai.protos.FunctionResponse(
                                            name=fc.name,
                                            response={"result": result}
                                        )
                                    )]
                                )
                            )
                
                if not found_call:
                    break

            try:
                if response.text:
                    yield "data: " + json.dumps({"text": response.text}) + nl
            except ValueError:
                pass
            return  # success
        except Exception as e:
            yield "data: " + json.dumps({"text": f"_(Gemini key 1 {type(e).__name__} — trying key 2...)_\n\n"}) + nl

    # ── Fallback: Gemini key 2 ────────────────────────────────────────────────
    gemini_key_2 = os.getenv("GEMINI_API_KEY_2")
    if gemini_key_2:
        try:
            import google.generativeai as genai
            import inspect
            genai.configure(api_key=gemini_key_2)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=CHAT_SYSTEM_PROMPT,
                tools=AGENT_TOOLS
            )
            chat = model.start_chat()
            response = chat.send_message(user_prompt)
            for i in range(10):
                if not response.candidates or not response.candidates[0].content.parts:
                    break
                parts = response.candidates[0].content.parts
                found_call = False
                for part in parts:
                    if part.function_call:
                        found_call = True
                        fc = part.function_call
                        args = {k: v for k, v in fc.args.items()}
                        func = next((t for t in AGENT_TOOLS if t.__name__ == fc.name), None)
                        if func:
                            try:
                                result = await func(**args) if inspect.iscoroutinefunction(func) else func(**args)
                            except Exception as tool_e:
                                result = f"Error: {tool_e}"
                            response = chat.send_message(
                                genai.protos.Content(parts=[genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=fc.name, response={"result": result}))])
                            )
                if not found_call:
                    break
            try:
                if response.text:
                    yield "data: " + json.dumps({"text": response.text}) + nl
            except ValueError:
                pass
            return
        except Exception as e2:
            yield "data: " + json.dumps({"text": f"_(Gemini key 2 also failed: {type(e2).__name__})_\n\n"}) + nl

    yield "data: " + json.dumps({"text": "_(No Gemini key available. Set GEMINI_API_KEY or GEMINI_API_KEY_2.)_"}) + nl
