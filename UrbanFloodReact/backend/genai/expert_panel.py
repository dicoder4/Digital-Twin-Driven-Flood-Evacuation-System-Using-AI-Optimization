import json
import httpx
import os

async def stream_advice(persona: str, summary_data: dict):
    prompts = {
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
3. Specify where to assign traffic cops to manage the evacuation routes to prevent blockages.
4. Keep the response highly structured and actionable. Do not provide generic observations.
5. IMPORTANT: Do NOT explain your reasoning, and do NOT summarize or describe the input data. Provide ONLY the action plan output.

Example Output Format:
**NDRF Deployment:**
- Station 10 personnel at Shelter Alpha to assist with overcrowding.
- Deploy 5 personnel to the Main Bridge for crowd control.

**Life Boat Deployment:**
- Deploy 3 life boats along Route A due to high water levels.

**Traffic Management:**
- Assign cops at Intersection X and Y to redirect traffic away from flooded routes.""",
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
    
    system_prompt = prompts.get(persona, "You are a disaster response expert.")
    prompt_text = f"Evacuation Summary:\n{json.dumps(summary_data, indent=2)}\n\nProvide your expert analysis:"

    groq_api_key = os.getenv("GROQ_API_KEY")
    
    if groq_api_key:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        # We use a fast conversational model for this, you could switch to llama3-70b-8192 if needed
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            "stream": True
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
                                    choices = data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield f"data: {json.dumps({'text': content})}\n\n"
                                except json.JSONDecodeError:
                                    continue
                        return  # Successfully streamed via Groq, exit function
                    else:
                        yield f"data: {json.dumps({'text': f'_(Groq API error {response.status_code}, falling back to offline model...)_\\n\\n'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'text': f'_(Groq connection failed, falling back to offline model...)_\\n\\n'})}\n\n"

    # Offline Fallback to Ollama
    payload = {
        "model": "llama3.2:latest",
        "system": system_prompt,
        "prompt": prompt_text,
        "stream": True
    }
    
    url = "http://localhost:11434/api/generate"
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=payload, timeout=None) as response:
                if response.status_code != 200:
                    err_msg = ""
                    async for chunk in response.aiter_bytes():
                        err_msg += chunk.decode()
                    yield f"data: {json.dumps({'text': f'Error from Ollama: {err_msg}'})}\n\n"
                    return
                
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            chunk_text = data.get("response", "")
                            if chunk_text:
                                yield f"data: {json.dumps({'text': chunk_text})}\n\n"
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        yield f"data: {json.dumps({'text': f'Failed to connect to local Ollama (llama3.2:latest). Ensure Ollama is running.\\nError: {str(e)}'})}\n\n"
