"""
app_copilot.py — Agentic LLM for UI Navigation & Simulation Control
───────────────────────────────────────────────────────────────────
Uses Gemini 2.5 Flash function calling to drive a multi-step flow:
  1. Fuzzy-match region → call select_region  (updates sidebar + navigates to config)
  2. Ask for simulation parameters via ask_clarification options
  3. call run_simulation with all flags (algorithm, rainfall, evacuation_mode, use_traffic)
"""

import os
import json
import difflib
import google.generativeai as genai
import inspect
import httpx
import requests

from genai.mcp_evacuation_server import (
    get_simulation_state, get_shelter_status, get_route_summary,
    analyze_road_conditions, get_rescue_guidelines, narrate_best_route,
    check_bus_availability, analyze_transit_disruptions, identify_evacuation_hubs
)

from genai.mcp_flood_intelligence_server import (
    get_metro_status as _flood_intel_metro,
    get_flood_impact as _flood_intel_impact,
    get_shelter_resource_map as _flood_intel_resources,
    get_vulnerability_hotspots as _flood_intel_hotspots
)

BACKEND_TOOLS = {
    "get_simulation_state": get_simulation_state,
    "get_shelter_status": get_shelter_status,
    "get_route_summary": get_route_summary,
    "analyze_road_conditions": analyze_road_conditions,
    "get_rescue_guidelines": get_rescue_guidelines,
    "narrate_best_route": narrate_best_route,
    "check_bus_availability": check_bus_availability,
    "analyze_transit_disruptions": analyze_transit_disruptions,
    "identify_evacuation_hubs": identify_evacuation_hubs,
    "get_metro_status": _flood_intel_metro,
    "get_flood_impact": _flood_intel_impact,
    "get_shelter_resource_map": _flood_intel_resources,
    "get_vulnerability_hotspots": _flood_intel_hotspots,
}

COPILOT_SYSTEM_PROMPT = """You are the 'App Copilot' for the Urban Flood Evacuation System.
Your job is to help the user navigate the application and run flood simulations.

The app workflow:
1. Select a region (District → Taluk → Hobli) from the sidebar.
2. Configure rainfall (default 150mm) and algorithm.
3. Click "Run Flood Simulation".
4. View results in the "Evacuation" tab.
5. Compare algorithms using Compare mode.

App tabs: 'setup' (region + config + map) | 'evacuation' (results + routes) | 'ai-agent' (AI resources + transport) | 'automation' (sentinel weather watcher) | 'compare' (activates compare mode, not a tab) | 'tutorial' (launches guided tutorial overlay).

TOOL CALL RULES — follow this exact flow when the user wants a simulation:
Step A: Fuzzy-match the location (see rules below). If it is a specific Hobli → call `select_region(hobli)`.
Step B: If the user has NOT specified all parameters (algorithm, rainfall, evacuation_mode, use_traffic), call `ask_clarification` with clickable options.
Step C: Once all parameters are known → call `run_simulation`.

If the user specifies everything in one message (e.g. "run Hebbal with GA, 200mm, live traffic"), skip Step B and go directly to Step C.

If the user only wants navigation (e.g. "take me to compare tab"), call `navigate` directly.

NEVER ask clarifying questions in plain text when you should be calling a tool.
Do NOT explain what you are doing. Just call the tool or give a concise answer."""


def _build_tools(available_hoblis: list, flat_taluks: dict) -> list:
    """Build Gemini tool declarations."""
    return [
        genai.protos.Tool(
            function_declarations=[
                genai.protos.FunctionDeclaration(
                    name="select_region",
                    description=(
                        "Select a specific Hobli region. Updates the dashboard sidebar and navigates to the config tab. "
                        "Call this FIRST after fuzzy-matching a valid Hobli."
                    ),
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "hobli": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="The exact Hobli name from the valid list.",
                            )
                        },
                        required=["hobli"],
                    ),
                ),
                genai.protos.FunctionDeclaration(
                    name="navigate",
                    description="Navigate to a specific tab or trigger an action in the application.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "tab": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="Tab or action: 'setup' (region/config), 'evacuation' (results), 'ai-agent' (AI resources), 'automation' (sentinel), 'compare' (compare mode), or 'tutorial' (guided walkthrough).",
                                enum=["setup", "evacuation", "ai-agent", "automation", "compare", "tutorial"],
                            )
                        },
                        required=["tab"],
                    ),
                ),
                genai.protos.FunctionDeclaration(
                    name="run_simulation",
                    description="Run a flood simulation with the given parameters.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "hobli": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="The exact Hobli name to simulate.",
                            ),
                            "algorithm": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="Optimization algorithm. Default: 'aco'.",
                                enum=["ga", "aco", "pso", "all"],
                            ),
                            "rainfall_mm": genai.protos.Schema(
                                type=genai.protos.Type.INTEGER,
                                description="Rainfall in mm. Default: 150.",
                            ),
                            "evacuation_mode": genai.protos.Schema(
                                type=genai.protos.Type.BOOLEAN,
                                description="If true, scales population to 1% for faster testing. Default: false.",
                            ),
                            "use_traffic": genai.protos.Schema(
                                type=genai.protos.Type.BOOLEAN,
                                description="If true, uses TomTom live traffic congestion on roads. Default: false.",
                            ),
                        },
                        required=["hobli"],
                    ),
                ),
                genai.protos.FunctionDeclaration(
                    name="ask_clarification",
                    description=(
                        "Ask the user a question with clickable option buttons. "
                        "Use this to offer simulation parameter choices (algorithm, traffic, evacuation mode, weather) "
                        "OR to disambiguate a Taluk into a specific Hobli."
                    ),
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "message": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="The question to ask the user.",
                            ),
                            "options": genai.protos.Schema(
                                type=genai.protos.Type.ARRAY,
                                description="Clickable option strings for the user to choose from.",
                                items=genai.protos.Schema(type=genai.protos.Type.STRING),
                            ),
                        },
                        required=["message", "options"],
                    ),
                ),
                genai.protos.FunctionDeclaration(
                    name="get_weather",
                    description="Fetch current real-time rainfall (mm) for a specific Hobli.",
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            "hobli": genai.protos.Schema(
                                type=genai.protos.Type.STRING,
                                description="The exact Hobli name.",
                            )
                        },
                        required=["hobli"],
                    ),
                ),
            ]
        )
    ]


def _build_system_instruction(available_hoblis: list, regions_tree: dict, latest_msg: str, map_pin: dict = None, lang: str = "en") -> str:
    """Inject dynamic location context into the system prompt."""
    hoblis_str = ", ".join(available_hoblis) if available_hoblis else "Hebbal, Yelahanka, Varthur, Begur (etc)"

    # Flatten district->taluk->hobli to simple taluk->hobli map
    flat_taluks: dict = {}
    if regions_tree:
        for taluks in regions_tree.values():
            for taluk_name, hobli_list in taluks.items():
                flat_taluks[taluk_name] = hobli_list

    # Language instruction — if user has switched to Kannada, force all replies in Kannada
    lang_instruction = ""
    if lang == "kn":
        lang_instruction = """

LANGUAGE INSTRUCTION (CRITICAL — MUST FOLLOW):
The user has enabled Kannada (ಕನ್ನಡ) mode. You MUST:
- Reply ENTIRELY in Kannada script (ಕನ್ನಡ ಲಿಪಿ).
- All explanations, questions, confirmations, and option labels must be in Kannada.
- Tool call argument values (hobli names, algorithm names like 'ga'/'aco'/'pso', tab names) must remain in English as they are code identifiers.
- But any user-facing text, messages, and ask_clarification message text MUST be in Kannada.
"""

    validation = f"""
VALID LOCATIONS:
- Hoblis: [{hoblis_str}]
- Taluks: [{", ".join(flat_taluks.keys())}]
- Taluk → Hobli mapping: {json.dumps(flat_taluks)}

NOTE: Location fuzzy-matching is handled by the system automatically. 
You will receive location tool calls pre-resolved. Focus on:
1. Navigation requests → call `navigate`
2. Parameter confirmation → call `ask_clarification` with options:
   ["▶ Start with defaults (ACO, 150mm)", "🔄 Start with GA instead", "🔄 Start with PSO instead", "📊 Start Compare Mode (GA vs ACO vs PSO)", "🚗 Enable live traffic", "⚡ Enable evac mode (1% population, faster)", "☁️ Use real-time rainfall"]
3. Running simulations with specified params → call `run_simulation`
4. For questions about the disaster, evacuation routes, transport, shelters, or anything else, CALL YOUR TOOLS to inspect the crisis database.

{f"- CRITICAL: The user has dropped a PIN on the map at coordinates lat={map_pin['lat']}, lon={map_pin['lon']}. Whenever they ask to check buses 'here', 'at the pinned location', 'selected location', or 'this location', you MUST automatically use these exact coordinates ({map_pin['lat']}, {map_pin['lon']}) for any tool calls requiring `lat` and `lon`." if map_pin else ""}
{lang_instruction}
"""
    return COPILOT_SYSTEM_PROMPT + validation


def _convert_messages(messages: list) -> list:
    """Convert {role, content} list to Gemini's Content format."""
    history = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        content = msg.get("content", "")
        history.append({"role": role, "parts": [content]})
    return history


def _best_fuzzy_match(query: str, candidates: list, min_ratio=0.55) -> tuple:
    """Returns (best_match, ratio) or (None, 0)."""
    query_lower = query.lower()
    best, best_ratio = None, 0
    for name in candidates:
        r = difflib.SequenceMatcher(None, query_lower, name.lower()).ratio()
        if r > best_ratio:
            best, best_ratio = name, r
    return (best, best_ratio) if best_ratio >= min_ratio else (None, 0)


def _python_location_match(user_msg: str, available_hoblis: list, flat_taluks: dict) -> dict | None:
    """
    Deterministic fuzzy location matching — bypasses LLM entirely.
    Returns a tool-call dict if a location is found, None otherwise.
    """
    # Only trigger for messages that look like they mention a place name
    # Trigger words - narrowed to reduce false positives
    location_triggers = ["run", "simulate", "simulation", "sim", "select", "load", "region"]
    msg_lower = user_msg.lower()
    if not any(t in msg_lower for t in location_triggers):
        return None

    # Stopwords that should NEVER be fuzzy-matched to locations
    stopwords = {
        "what", "where", "who", "when", "why", "how", "those", "these", "this", "that",
        "best", "good", "better", "great", "show", "tell", "give", "want", "need",
        "help", "green", "blue", "yellow", "purple", "white", "black", "with", "using",
        "line", "lane", "road", "rail", "metro", "train", "bus", "alternatives"
    }

    # Extract candidate words (> 3 chars, stripped of punctuation)
    words = [w.strip('.,?!:') for w in user_msg.split() if len(w.strip('.,?!:')) > 3]
    # Filter out trigger words and stopwords
    words = [w for w in words if w.lower() not in location_triggers and w.lower() not in stopwords]
    
    if not words:
        return None

    # Try individual words and multi-word combinations
    attempts = list(words)
    if len(words) > 1:
        attempts.append("".join(words))  # "dodda bellapur" → "doddabellapur"

    best_hobli, best_hobli_ratio = None, 0
    best_taluk, best_taluk_ratio = None, 0

    # Fast-path for explicit button clicks
    if "(Hobli — run directly)" in user_msg:
        exact_h = user_msg.split("(Hobli")[0].strip()
        hm, _ = _best_fuzzy_match(exact_h, available_hoblis, min_ratio=0.8)
        if hm: return {"type": "tool_call", "name": "select_region", "arguments": {"hobli": hm}}

    if "(in " in user_msg and "Taluk)" in user_msg:
        exact_h = user_msg.split("(in ")[0].strip()
        hm, _ = _best_fuzzy_match(exact_h, available_hoblis, min_ratio=0.8)
        if hm: return {"type": "tool_call", "name": "select_region", "arguments": {"hobli": hm}}

    for w in attempts:
        hm, hr = _best_fuzzy_match(w, available_hoblis, min_ratio=0.75)  # Stricter threshold
        tm, tr = _best_fuzzy_match(w, list(flat_taluks.keys()), min_ratio=0.75)
        if hm and hr > best_hobli_ratio:
            best_hobli, best_hobli_ratio = hm, hr
        if tm and tr > best_taluk_ratio:
            best_taluk, best_taluk_ratio = tm, tr

    # No match at all
    if not best_hobli and not best_taluk:
        return None

    # BOTH match above threshold
    if best_hobli and best_taluk and best_hobli != best_taluk:
        # If one match is significantly better than the other, let the winner take all
        if best_hobli_ratio > best_taluk_ratio + 0.15:
            return {"type": "tool_call", "name": "select_region", "arguments": {"hobli": best_hobli}}
        elif best_taluk_ratio > best_hobli_ratio + 0.15:
            # Let it fall through to the Taluk-only logic below
            best_hobli = None
        else:
            # Truly ambiguous
            options = [f"{best_hobli} (Hobli — run directly)"]
            for h in flat_taluks.get(best_taluk, []):
                options.append(f"{h} (in {best_taluk} Taluk)")
            return {
                "type": "message",
                "content": f"Did you mean the hobli **{best_hobli}**, or a hobli in **{best_taluk}** taluk?",
                "options": options
            }

    # Only taluk matched → ask which hobli
    if best_taluk and best_taluk_ratio > best_hobli_ratio:
        hoblis = flat_taluks.get(best_taluk, [])
        if len(hoblis) == 1:
            # Only one hobli in this taluk → select it directly
            return {"type": "tool_call", "name": "select_region", "arguments": {"hobli": hoblis[0]}}
        return {
            "type": "message",
            "content": f"**{best_taluk}** is a Taluk. Which hobli would you like to run the simulation for?",
            "options": hoblis
        }

    # Only hobli matched → select directly
    if best_hobli:
        return {"type": "tool_call", "name": "select_region", "arguments": {"hobli": best_hobli}}

    return None


async def ask_copilot(messages: list, available_hoblis: list = None, regions_tree: dict = None, map_pin: dict = None, lang: str = "en") -> dict:
    """
    Sends conversation to Gemini 2.5 Flash with function calling.
    Returns one of:
      {"type": "message",   "content": "...", "options": [...]}
      {"type": "tool_call", "name": "...",    "arguments": {...}}
    """
    available_hoblis = available_hoblis or []
    regions_tree = regions_tree or {}

    # Build flat taluks map
    flat_taluks: dict = {}
    if regions_tree:
        for taluks in regions_tree.values():
            for taluk_name, hobli_list in taluks.items():
                flat_taluks[taluk_name] = hobli_list

    last_msg = messages[-1] if messages else {}
    last_role = last_msg.get("role", "user")
    latest_user_msg = last_msg.get("content", "")

    # ── DETERMINISTIC PRE-CHECK: fuzzy match locations in Python ──
    # Only run for USERS. This prevents internal follow-ups (assistant messages) 
    # from accidentally triggering the location matcher again.
    if last_role == "user":
        pre_result = _python_location_match(latest_user_msg, available_hoblis, flat_taluks)
        if pre_result:
            return pre_result

    # ── Otherwise, send to LLM for general queries / navigation / params ──
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"type": "message", "content": "Error: GEMINI_API_KEY is not set.", "options": []}

    try:
        genai.configure(api_key=api_key)
        system_instruction = _build_system_instruction(available_hoblis, regions_tree, latest_user_msg, map_pin, lang)

        # --- Fix: Ensure tool list is consistent (either all functions or all protos) ---
        # Gemini SDK takes a list of functions OR a list of protos. Mixing can be flaky.
        # We'll convert our frontend declarations to a format Gemini likes, or just use parts.
        
        # Define safety settings to prevent unnecessary blocks
        safety_settings = {
            genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
            genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
            genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        }

        # Instead of protos.Tool, we'll just pass a list of functions where possible.
        # But for navigate/ask_clarification we need the custom schema.
        # Let's use the explicit tool declaration approach.
        frontend_tools_obj = _build_tools(available_hoblis or [], flat_taluks)
        backend_funcs = list(BACKEND_TOOLS.values())
        
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction,
            tools=backend_funcs + frontend_tools_obj,
            safety_settings=safety_settings
        )

        history = _convert_messages(messages[:-1]) if len(messages) > 1 else []
        chat = model.start_chat(history=history)
        
        print(f"[Copilot] Sending message: '{latest_user_msg}'")
        response = chat.send_message(latest_user_msg)

        # Agent execution loop for backend tools (max 10 iterations)
        for i in range(10):
            # Safe parts access
            if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                print(f"[Copilot] Iteration {i}: No parts in response. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
                break
            
            parts = response.candidates[0].content.parts
            has_backend_call = False
            
            for part in parts:
                if part.function_call:
                    fc = part.function_call
                    func_name = fc.name
                    args = {k: v for k, v in fc.args.items()}
                    print(f"[Copilot] Iteration {i}: Model called '{func_name}' with {args}")

                    if func_name in BACKEND_TOOLS:
                        print(f"[Copilot] Executing BACKEND tool '{func_name}'")
                        func = BACKEND_TOOLS[func_name]
                        try:
                            # ── FIX: Handle both sync and async tools ──
                            if inspect.iscoroutinefunction(func):
                                result = await func(**args)
                            else:
                                result = func(**args)
                        except Exception as e:
                            print(f"[Copilot] Tool error: {e}")
                            result = f"Error: {e}"
                        
                        # Send result back and continue loop
                        response = chat.send_message(
                            genai.protos.Content(
                                parts=[genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=func_name,
                                        response={"result": result}
                                    )
                                )]
                            )
                        )
                        has_backend_call = True
                        break # Re-evaluate the new response from the top
                        
                    else:
                        # Frontend / App tool! Return immediately to UI.
                        print(f"[Copilot] Identified FRONTEND tool '{func_name}'. Returning to UI.")
                        if func_name == "ask_clarification":
                            return {
                                "type": "message",
                                "content": args.get("message", "Which option do you prefer?"),
                                "options": list(args.get("options", [])),
                            }
                        return {
                            "type": "tool_call",
                            "name": func_name,
                            "arguments": args,
                        }
            
            if not has_backend_call:
                # If we're here, either it's plain text or we've finished the tool chain
                print(f"[Copilot] Iteration {i}: No further backend calls. Checking for text output.")
                break

        # Final check for text output
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            # Check if any part has text
            text_parts = [p.text for p in response.candidates[0].content.parts if p.text]
            if text_parts:
                return {"type": "message", "content": "\n".join(text_parts), "options": []}
        
        return {"type": "message", "content": "I'm sorry, I couldn't process that request properly. (Empty Response)", "options": []}

    except Exception as e:
        print(f"[Copilot] CRITICAL ERROR: {e}")
        # If Gemini fails (e.g. rate limit 429), attempt fallback to Groq
        if "429" in str(e) or "quota" in str(e).lower():
            print(f"Gemini rate limit hit, falling back to Groq... ({e})")
            return await _fallback_ask_groq(messages, system_instruction)
        return {"type": "message", "content": f"Copilot error: {str(e)}", "options": []}


async def _fallback_ask_groq(messages: list, system_instruction: str) -> dict:
    """Fallback handler using Groq API (Llama 3.3 70B) if Gemini rate limits us."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return {"type": "message", "content": "Gemini rate limited and GROQ_API_KEY is missing.", "options": []}

    # Translate tools to OpenAI schema for Groq
    groq_tools = [
        {
            "type": "function",
            "function": {
                "name": "select_region",
                "description": "Select a specific Hobli region. Call FIRST after fuzzy-matching.",
                "parameters": {
                    "type": "object",
                    "properties": {"hobli": {"type": "string"}},
                    "required": ["hobli"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "navigate",
                "description": "Navigate to a specific tab.",
                "parameters": {
                    "type": "object",
                    "properties": {"tab": {"type": "string", "enum": ["setup", "evacuation", "ai-agent", "automation", "compare", "tutorial"]}},
                    "required": ["tab"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_simulation",
                "description": "Run a flood simulation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "hobli": {"type": "string"},
                        "algorithm": {"type": "string", "enum": ["ga", "aco", "pso", "all"]},
                        "rainfall_mm": {"type": "integer"},
                        "evacuation_mode": {"type": "boolean"},
                        "use_traffic": {"type": "boolean"}
                    },
                    "required": ["hobli"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ask_clarification",
                "description": "Ask the user to clarify options.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["message", "options"]
                }
            }
        }
    ]

    # Truncate system prompt for Groq's smaller context window
    truncated_prompt = system_instruction[:4000] if len(system_instruction) > 4000 else system_instruction

    # Build clean messages — Groq only accepts roles: system, user, assistant
    clean_messages = [{"role": "system", "content": truncated_prompt}]
    for msg in messages:
        role = msg.get("role", "user")
        if role not in ("user", "assistant", "system"):
            role = "user"
        content = msg.get("content", "")
        if not content:
            continue  # Groq rejects empty content
        clean_messages.append({"role": role, "content": content})

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": clean_messages,
                    "tools": groq_tools,
                    "tool_choice": "auto",
                    "temperature": 0.1
                },
                timeout=20.0
            )

            if resp.status_code != 200:
                error_body = resp.text
                print(f"Groq API error {resp.status_code}: {error_body[:500]}")
                return {"type": "message", "content": f"Groq fallback error (HTTP {resp.status_code}). Please try again in a moment.", "options": []}

            data = resp.json()
            choice = data["choices"][0]["message"]

            if choice.get("tool_calls"):
                tc = choice["tool_calls"][0]["function"]
                func_name = tc["name"]
                args = json.loads(tc["arguments"])

                if func_name == "ask_clarification":
                    return {
                        "type": "message",
                        "content": args.get("message", "Which option do you prefer?"),
                        "options": args.get("options", [])
                    }
                return {
                    "type": "tool_call",
                    "name": func_name,
                    "arguments": args
                }

            content = choice.get("content") or "I couldn't process that request."
            return {"type": "message", "content": content, "options": []}

    except Exception as e:
        print(f"Groq fallback exception: {e}")
        return {"type": "message", "content": f"Both Gemini and Groq are unavailable. Please try again in a moment.", "options": []}
