"""
ollama_agent.py
───────────────
Ollama (llama3) chat agent with structured tool-calling for the Urban Flood
Digital Twin.  Communicates with the local Ollama server at localhost:11434.

Design principles
─────────────────
1.  TOOL-FIRST: The agent MUST call get_weather before run_simulation.
    Rainfall is never set to an arbitrary value — it always comes from the
    weather server or the historical sampler via param_resolver.
2.  GUIDED MODE: When intent is ambiguous, the agent asks the operator for
    confirmation before proceeding with any simulation.
3.  STREAMING: Responses are yielded as SSE data chunks so the React frontend
    can stream them in real time.

Supported intents (detected by the model):
  • "run simulation for <hobli>"   → guided_simulation intent
  • "what is the weather in <h>"   → weather_query intent
  • "explain / tell me about"      → informational intent
  • anything else                  → general_chat intent

Usage (standalone):
    from genai.ollama_agent import OllamaAgent
    agent = OllamaAgent()
    for chunk in agent.chat("Run flood simulation for Sarjapura"):
        print(chunk, end="", flush=True)

Usage (FastAPI SSE):
    async def genai_stream(message: str):
        agent = OllamaAgent()
        async for chunk in agent.astream(message):
            yield f"data: {json.dumps({'text': chunk})}\\n\\n"
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Generator, AsyncGenerator

# ── Ensure backend root is on path ────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from genai.tools import get_weather_tool, run_simulation_tool
from genai.prompts import build_system_prompt

# ── Ollama config ─────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL",    "llama3.2:latest")
OLLAMA_TIMEOUT  = int(os.environ.get("OLLAMA_TIMEOUT", "120"))

# ── Tool registry ─────────────────────────────────────────────────────────────
_TOOLS = [
    get_weather_tool.TOOL_SCHEMA,
    run_simulation_tool.TOOL_SCHEMA,
]

_TOOL_HANDLERS = {
    "get_weather":    get_weather_tool.run,
    "run_simulation": run_simulation_tool.run,
}

# ── System prompt (sourced from prompts.py) ──────────────────────────────────
_SYSTEM_PROMPT = build_system_prompt()


class OllamaAgent:
    """
    Stateful chat agent backed by Ollama (llama3).

    Parameters
    ----------
    model   : str   Ollama model name (default: llama3)
    history : list  Pre-seeded conversation history (optional)
    """

    def __init__(self, model: str = OLLAMA_MODEL, history: list | None = None):
        self.model   = model
        self.history: list[dict] = history or []

    # ── Low-level Ollama API calls ────────────────────────────────────────────

    def _call_ollama(self, messages: list[dict], stream: bool = False) -> dict | Generator:
        """POST to /api/chat and return parsed response (or stream generator)."""
        payload = {
            "model":    self.model,
            "messages": messages,
            "tools":    _TOOLS,
            "stream":   stream,
            "options":  {"temperature": 0.3, "num_predict": 1024},
        }
        body = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        if stream:
            def _gen():
                with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                    for line in resp:
                        line = line.decode("utf-8").strip()
                        if line:
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError:
                                pass
            return _gen()
        else:
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                return json.loads(resp.read())

    def _is_available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    # ── Tool execution ────────────────────────────────────────────────────────

    def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        """Run the requested tool and return its result as a JSON string."""
        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = handler(**tool_args)
            return json.dumps(result, indent=2)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ── Main chat loop ────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> Generator[str, None, None]:
        """
        Synchronous generator — yields text chunks as the agent reasons,
        calls tools, and forms its final response.

        Yields
        ------
        str : Text fragments suitable for display / SSE streaming.
        """
        # Check Ollama availability first
        if not self._is_available():
            yield (
                "⚠️ **Ollama server not reachable** at `localhost:11434`.\n\n"
                "Please start Ollama with:\n```\nollama serve\n```\n"
                "Then ensure llama3 is downloaded:\n```\nollama pull llama3\n```"
            )
            return

        # Build messages
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})

        # ── Agentic tool-calling loop ─────────────────────────────────────────
        max_iterations = 5
        for iteration in range(max_iterations):
            try:
                response = self._call_ollama(messages, stream=False)
            except Exception as exc:
                yield f"\n\n❌ Ollama error: {exc}"
                return

            msg = response.get("message", {})
            tool_calls = msg.get("tool_calls", [])

            if tool_calls:
                # Agent wants to call a tool
                assistant_msg = {
                    "role":       "assistant",
                    "content":    msg.get("content", ""),
                    "tool_calls": tool_calls,
                }
                messages.append(assistant_msg)

                if msg.get("content"):
                    yield msg["content"] + "\n\n"

                for tc in tool_calls:
                    fn   = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    yield f"🔧 **Calling tool:** `{name}`\n"
                    yield f"```json\n{json.dumps(args, indent=2)}\n```\n\n"

                    tool_result = self._execute_tool(name, args)

                    # Parse result for a quick human-readable summary
                    try:
                        result_dict = json.loads(tool_result)
                        yield _format_tool_result(name, result_dict)
                    except Exception:
                        pass

                    messages.append({
                        "role":    "tool",
                        "content": tool_result,
                    })

            else:
                # No more tool calls — final response
                final_content = msg.get("content", "")
                # Update history for stateful conversations
                self.history.append({"role": "user",      "content": user_message})
                self.history.append({"role": "assistant",  "content": final_content})
                # Keep history bounded (last 20 turns)
                if len(self.history) > 40:
                    self.history = self.history[-40:]
                yield final_content
                return

        yield "\n\n⚠️ Agent reached maximum iterations without a final response."

    def reset(self):
        """Clear conversation history."""
        self.history.clear()


# ── Async wrapper for FastAPI ─────────────────────────────────────────────────

class AsyncOllamaAgent(OllamaAgent):
    """
    Async wrapper around OllamaAgent for use in FastAPI async generators.
    Since Ollama calls are synchronous HTTP, we run them in an executor.
    """

    async def astream(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Async generator — yields text chunks for FastAPI StreamingResponse.
        Wraps the sync chat() generator using asyncio.
        """
        import asyncio
        loop = asyncio.get_event_loop()

        # Collect all chunks from the sync generator in an executor
        # We can't lazily stream because run_in_executor needs the whole fn.
        # For true streaming with Ollama, use the stream=True path.
        chunks = []

        def _run():
            for chunk in self.chat(user_message):
                chunks.append(chunk)

        await loop.run_in_executor(None, _run)
        for chunk in chunks:
            yield chunk

    async def astream_one_shot(
        self,
        prompt: str,
        system: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Lightweight single-turn Ollama call with no history and no tools.
        Used by mcp_pipeline.py for structured reasoning prompts (e.g.
        historical scenario analysis, post-simulation narrative).

        Parameters
        ----------
        prompt : str
            The full user-turn content (usually a complete prompt template).
        system : str | None
            Optional system message override.  Defaults to build_system_prompt().

        Yields
        ------
        str : Text fragments from the model response.
        """
        import asyncio
        import urllib.request
        import json

        sys_msg = system if system is not None else build_system_prompt()
        messages = [
            {"role": "system",  "content": sys_msg},
            {"role": "user",    "content": prompt},
        ]
        payload = {
            "model":    self.model,
            "messages": messages,
            "stream":   False,
            "options":  {"temperature": 0.4, "num_predict": 768},
        }
        body = json.dumps(payload).encode()
        req  = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        loop = asyncio.get_event_loop()
        chunks: list[str] = []

        def _call():
            try:
                with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                    data = json.loads(resp.read())
                    content = data.get("message", {}).get("content", "")
                    if content:
                        chunks.append(content)
            except Exception as exc:
                chunks.append(f"\n\n⚠️ Ollama reasoning error: {exc}")

        await loop.run_in_executor(None, _call)
        for chunk in chunks:
            yield chunk


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_tool_result(tool_name: str, result: dict) -> str:
    """
    Convert a tool result dict into a concise markdown summary for display.
    """
    if not result.get("ok", True):
        return f"❌ **Tool error:** {result.get('error', 'Unknown error')}\n\n"

    if tool_name == "get_weather":
        weather     = result.get("weather", {})
        hobli_info  = result.get("hobli_info", {})
        rain_mm     = result.get("rainfall_mm_clamped", "N/A")
        clamp_note  = result.get("clamp_note", "")
        source      = result.get("rainfall_source", "")

        lines = [
            f"📍 **Hobli:** {hobli_info.get('display', 'Unknown')} ({hobli_info.get('district', '')})",
            f"🌧️ **Rainfall (validated):** {rain_mm} mm  _(source: {source})_",
            f"🌡️ **Temperature:** {weather.get('temp_c', 'N/A')} °C",
            f"💨 **Wind:** {weather.get('wind_speed_kmh', 'N/A')} km/h",
            f"📋 **Condition:** {weather.get('description', 'N/A')}",
            f"📊 **Valid range for this hobli:** {hobli_info.get('rain_min', 'N/A')}–{hobli_info.get('rain_max', 'N/A')} mm",
        ]
        if clamp_note:
            lines.append(f"⚠️ {clamp_note}")
        return "\n".join(lines) + "\n\n"

    elif tool_name == "run_simulation":
        summary = result.get("summary", {})
        lines = [
            f"✅ **Simulation complete** — {result.get('hobli', '')} @ {result.get('rainfall_mm', '')} mm",
            f"🏃 **Evacuated:** {summary.get('total_evacuated', 'N/A'):,}",
            f"⚠️ **At risk remaining:** {summary.get('total_at_risk_remaining', 'N/A'):,}",
            f"📈 **Success rate:** {summary.get('success_rate_pct', 'N/A')}%",
            f"🧬 **Algorithm:** {summary.get('algorithm', 'N/A')}",
            f"⏱️ **Time:** {summary.get('ga_execution_time', 'N/A')}s",
        ]
        return "\n".join(lines) + "\n\n"

    return ""
