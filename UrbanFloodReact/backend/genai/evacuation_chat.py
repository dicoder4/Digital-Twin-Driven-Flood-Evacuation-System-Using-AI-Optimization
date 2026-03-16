"""
evacuation_chat.py — Free-form NL chat about evacuation data
────────────────────────────────────────────────────────────
Streaming endpoint: takes a user question + enriched context,
returns a grounded answer via Groq / Ollama.
"""

import json
import httpx
import os

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
7. Use Markdown for formatting (bold, tables, etc.)."""


async def stream_chat(question: str, context_data: dict):
    """
    Stream an answer to a free-form user question about the evacuation.
    Uses the same Groq -> Ollama fallback chain as expert_panel.py.
    """
    context_text = json.dumps(context_data, indent=2)
    user_prompt = "Evacuation Context:" + "\n" + context_text + "\n\nUser Question: " + question

    groq_api_key = os.getenv("GROQ_API_KEY")
    nl = "\n\n"

    # ── Primary: Groq ─────────────────────────────────────────────
    if groq_api_key:
        groq_url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer " + groq_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
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
                                    choices = data.get("choices", [])
                                    if choices:
                                        content = choices[0].get("delta", {}).get("content", "")
                                        if content:
                                            yield "data: " + json.dumps({"text": content}) + nl
                                except json.JSONDecodeError:
                                    continue
                        return
                    else:
                        fallback_msg = "_(Groq API error, falling back to offline model...)_" + nl
                        yield "data: " + json.dumps({"text": fallback_msg}) + nl
        except Exception:
            conn_msg = "_(Groq connection failed, falling back to offline model...)_" + nl
            yield "data: " + json.dumps({"text": conn_msg}) + nl

    # ── Fallback: Ollama (llama3.2 -> gemma3:1b) ──────────────────
    ollama_url = "http://localhost:11434/api/generate"

    async def _try_ollama_chat(model_name: str):
        payload = {
            "model": model_name,
            "system": CHAT_SYSTEM_PROMPT,
            "prompt": user_prompt,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream("POST", ollama_url, json=payload, timeout=None) as response:
                    if response.status_code != 200:
                        err_bytes = b""
                        async for chunk in response.aiter_bytes():
                            err_bytes += chunk
                        err_msg = err_bytes.decode()
                        if "model" in err_msg.lower() and "not found" in err_msg.lower():
                            yield False
                            return
                        err_payload = json.dumps({"text": "_(Ollama error: " + err_msg + ")_" + nl})
                        yield "data: " + err_payload + nl
                        return
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk_data = json.loads(line)
                                chunk_text = chunk_data.get("response", "")
                                if chunk_text:
                                    yield "data: " + json.dumps({"text": chunk_text}) + nl
                                if chunk_data.get("done"):
                                    return
                            except json.JSONDecodeError:
                                continue
        except Exception as exc:
            yield exc

    # Try llama3.2
    model_not_found = False
    async for chunk in _try_ollama_chat("llama3.2:latest"):
        if chunk is False:
            model_not_found = True
            break
        if isinstance(chunk, Exception):
            break
        yield chunk
    if not model_not_found:
        return

    # Try gemma3:1b
    switch_msg = json.dumps({"text": "_(llama3.2 not found, switching to gemma3:1b...)_" + nl})
    yield "data: " + switch_msg + nl
    async for chunk in _try_ollama_chat("gemma3:1b"):
        if chunk is False or isinstance(chunk, Exception):
            dead_msg = json.dumps({"text": "_(All models unavailable. Set GROQ_API_KEY or run Ollama.)_"})
            yield "data: " + dead_msg + nl
            return
        yield chunk
