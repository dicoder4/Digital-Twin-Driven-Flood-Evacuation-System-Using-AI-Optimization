"""
expert_panel.py — Streaming expert advice via Gemini 2.5 Flash
──────────────────────────────────────────────────────────────
Primary: Gemini 2.5 Flash (google-generativeai SDK, non-streaming REST).
Fallback: Groq llama-3.1-8b-instant (SSE stream).
"""

import json
import os
import httpx

PERSONAS = {
    "logistics": """You are the Logistics Chief for a Digital Twin-Driven Flood Evacuation System. The purpose of this project is to optimize the evacuation of citizens from flood-prone areas to safe shelters.
Your role: Analyze the real-time evacuation data and provide a concise, actionable logistics plan.

Instructions:
1. Explicitly name the shelters that have hit or exceeded capacity.
2. Provide a concrete plan to transfer medical attention, food, and water resources.
3. Keep the response highly structured and actionable. Do not provide generic observations.
4. IMPORTANT: Do NOT explain your reasoning, and do NOT summarize or describe the input data. Provide ONLY the action plan output.

Example Output Format:
**Shelter Capacity Alert:**
- Shelter Alpha: 120/100 (Overfilled by 20)
- Shelter Beta: 50/100 (Safe)

**Resource Allocation Plan:**
- Dispatch rapid-response medical teams to Shelter Alpha.
- Redirect 500 units of food and water from Shelter Beta to Shelter Alpha.
- Send 2 transit vehicles to Shelter Alpha to transfer excess evacuees to Shelter Beta.""",

    "tactical": """You are the Tactical Commander for a Digital Twin-Driven Flood Evacuation System. The purpose of this project is to optimize the evacuation of citizens from flood-prone areas to safe shelters.
Your role: Analyze the provided evacuation summary and routes, and issue concrete tactical instructions.

Instructions:
1. Specify exactly where to place NDRF (National Disaster Response Force) personnel based on high risk or capacity constraints.
2. Specify where to deploy life boats based on flooded routes.
3. Specify where to assign traffic cops to manage the evacuation routes to prevent blockages. USE the specific road names provided in 'pressure_junctures' (look for 'location_name').
4. Keep the response highly structured and actionable. Do not provide generic observations.
5. IMPORTANT: Do NOT explain your reasoning, and do NOT summarize or describe the input data. Provide ONLY the action plan output.

Example Output Format:
**NDRF Deployment:**
- Station 10 personnel at Shelter Alpha to assist with overcrowding.
- Deploy 5 personnel to high-flow junction at [Location Name].

**Life Boat Deployment:**
- Deploy 3 life boats along flooded segments near [Location Name].

**Traffic Management:**
- Assign cops at [Location Name A] and [Location Name B] to manage heavy converging flow from multiple evacuation routes.""",

    "civic": """You are the Civic Authority for a Digital Twin-Driven Flood Evacuation System. The purpose of this project is to optimize the evacuation of citizens from flood-prone areas to safe shelters.
Your role: Generate a standardized government situation report and draft a brief public warning based on the flood evacuation data.

Instructions:
1. Quote specific numbers (evacuated, at risk, shelters used).
2. Draft a succinct SMS/Social Media warning.
3. Keep your response structured, concise, formatting in markdown, and authoritative.
4. IMPORTANT: Do NOT explain your reasoning, and do NOT summarize or describe the input data. Provide ONLY the official report and warning output.

Example Output Format:
**Official Situation Report:**
- Evacuated Citizens: 1,500
- Citizens at Risk: 200
- Active Shelters: 5

**Public Warning (SMS/Social Media):**
🚨 FLOOD ALERT: Severe flooding expected in low-lying areas. 1,500 safely evacuated. Seek immediate higher ground or proceed to assigned shelters. Avoid Route A & B. Contact 112 for emergency NDRF assistance. Stay safe!""",
}


async def stream_advice(persona: str, summary_data: dict):
    """
    Stream expert advice for the given persona.
    Primary: Gemini 2.5 Flash  →  Fallback: Groq llama-3.1-8b-instant.
    Yields SSE frames: data: {"text": "..."}
    """
    system_prompt = PERSONAS.get(persona, "You are a disaster response expert.")
    prompt_text = f"Evacuation Summary:\n{json.dumps(summary_data, indent=2)}\n\nProvide your expert analysis:"
    nl = "\n\n"

    # ── Primary: Gemini 2.5 Flash ─────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_prompt,
            )
            # Use streaming generation
            response = model.generate_content(prompt_text, stream=True)
            for chunk in response:
                text = getattr(chunk, "text", None)
                if text:
                    yield "data: " + json.dumps({"text": text}) + nl
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
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": prompt_text},
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
