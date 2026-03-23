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
    get_rescue_guidelines
)

AGENT_TOOLS = [
    narrate_best_route, 
    analyze_road_conditions, 
    get_rescue_guidelines
]

async def stream_chat(question: str, context_data: dict):
    """
    Stream an answer to a free-form user question about the evacuation.
    Primary: Gemini 2.5 Flash  →  Fallback: Groq llama-3.1-8b-instant.
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
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=CHAT_SYSTEM_PROMPT,
                tools=AGENT_TOOLS
            )
            chat = model.start_chat(enable_automatic_function_calling=True)
            response = chat.send_message(user_prompt, stream=False)
            try:
                if response.text:
                    yield "data: " + json.dumps({"text": response.text}) + nl
            except ValueError:
                pass # Ignore parts with no text
            return  # success
        except Exception as e:
            err_text = f"_(Gemini error: {e} — falling back to Groq...)_\n\n"
            yield "data: " + json.dumps({"text": err_text}) + nl

    # ── Fallback: Groq llama-3.1-8b-instant ──────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": True,
        }
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", groq_url, headers=headers, json=payload, timeout=None) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    data = json.loads(data_str)
                                    content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                    if content:
                                        yield "data: " + json.dumps({"text": content}) + nl
                                except json.JSONDecodeError:
                                    continue
                        return
                    else:
                        err = f"_(Groq API error {response.status_code})_\n\n"
                        yield "data: " + json.dumps({"text": err}) + nl
        except Exception as e:
            yield "data: " + json.dumps({"text": f"_(Groq connection failed: {e})_\n\n"}) + nl
            return

    # ── All providers unavailable ─────────────────────────────────────────────
    yield "data: " + json.dumps({"text": "_(No AI provider available. Set GEMINI_API_KEY or GROQ_API_KEY.)_"}) + nl
