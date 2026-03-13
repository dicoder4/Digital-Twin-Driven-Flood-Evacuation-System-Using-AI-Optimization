import json
import httpx

async def stream_advice(persona: str, summary_data: dict):
    prompts = {
        "logistics": "You are the Logistics Chief for a flood evacuation. Analyze the provided evacuation summary data. You MUST explicitly name the shelters that have hit or exceeded capacity. You MUST provide a concrete, actionable plan on how to transfer medical attention, food, and water resources to these specific overflowing shelters. Do not provide generic observations. Keep your response highly structured, actionable, and formatted in markdown.",
        "tactical": "You are the Tactical Commander for a flood evacuation. Analyze the provided evacuation summary and routes. You MUST provide concrete tactical instructions: exactly where to place NDRF personnel, where to deploy life boats, and where to assign traffic cops to manage the evacuation routes. Keep your response highly structured, actionable, and formatted in markdown. Do not provide generic observations.",
        "civic": "You are the Civic Authority for a flood evacuation. Generate a standardized government situation report and draft a brief public warning SMS/Social Media post based on the flood evacuation data. Quote specific numbers (evacuated, at risk, shelters used). Keep your response structured, concise, formatting in markdown, and authoritative.",
    }
    
    system_prompt = prompts.get(persona, "You are a disaster response expert.")
    prompt_text = f"Evacuation Summary:\n{json.dumps(summary_data, indent=2)}\n\nProvide your expert analysis:"

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
