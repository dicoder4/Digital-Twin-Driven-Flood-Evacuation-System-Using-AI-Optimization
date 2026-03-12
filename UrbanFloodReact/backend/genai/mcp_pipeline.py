"""
mcp_pipeline.py
───────────────
Orchestrator for the GenAI + MCP Weather pipeline.

This is the single entry-point for any NL request from the React frontend.
It:
  1. Classifies the user's intent (simulation / weather / informational).
  2. Routes to the appropriate agent (OllamaAgent or rule-based fallback).
  3. Handles the "rainfall sourcing dialogue" — asking the operator whether to
     use real-time or historical data before any simulation runs.
  4. For historical mode: presents 3 Ollama-reasoned scenarios → user picks one.
  5. After simulation: Ollama generates a narrative summary.
  6. Returns an async generator suitable for FastAPI StreamingResponse SSE.

Architecture
────────────
React Frontend
    │  POST /genai/chat  (message: str, session_id: str)
    ▼
mcp_pipeline.MCPPipeline.handle(message, session)
    │
    ├─► Intent = weather_query
    │       └─► get_weather_tool.run(hobli, mode)
    │
    ├─► Intent = simulation_request
    │       ├─► ask user: realtime or historical?
    │       ├─► [realtime]  → get_weather_tool → confirm → simulate
    │       ├─► [historical] → Ollama reasons over 3 IMD scenarios
    │       │               → user picks scenario → confirm → simulate
    │       └─► post-sim: Ollama narrative + SIM_META JSON token
    │
    └─► Intent = general / informational
            └─► OllamaAgent.chat(message)

Control tokens emitted in SSE stream (stripped by frontend):
  \\x00SIM_DONE:<hobli>:<rainfall_mm>   — triggers "View Map" banner
  \\x00SIM_META:<json_b64>             — passes full summary to SimResultPanel

Session management:
  Each browser session has its own OllamaAgent instance with its own history,
  keyed by session_id.  Sessions expire after SESSION_TTL_SECONDS.
"""

from __future__ import annotations

import json
import os
import sys
import time
import base64
from pathlib import Path
from typing import AsyncGenerator

# ── Ensure backend root is on path ────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from genai.ollama_agent import AsyncOllamaAgent
from genai.tools import get_weather_tool, run_simulation_tool
from genai import prompts

SESSION_TTL_SECONDS = 1800  # 30 minutes

import logging
log = logging.getLogger("mcp_pipeline")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [MCP] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

# ── Session store (in-memory, process-scoped) ─────────────────────────────────
_sessions: dict[str, dict] = {}  # session_id → {agent, last_active, state}


def _get_or_create_session(session_id: str) -> dict:
    """Return existing session dict or create a new one."""
    now = time.monotonic()

    # Evict expired sessions
    expired = [sid for sid, s in _sessions.items()
                if now - s["last_active"] > SESSION_TTL_SECONDS]
    for sid in expired:
        del _sessions[sid]

    if session_id not in _sessions:
        _sessions[session_id] = {
            "agent":       AsyncOllamaAgent(),
            "last_active": now,
            "state":       {},   # pipeline state machine per session
        }
    else:
        _sessions[session_id]["last_active"] = now

    return _sessions[session_id]


def reset_session(session_id: str):
    """Clear conversation history for a session."""
    log.info("reset_session: session_id=%s", session_id)
    if session_id in _sessions:
        _sessions[session_id]["agent"].reset()
        _sessions[session_id]["state"] = {}


# ── Intent classification ─────────────────────────────────────────────────────
# Simple keyword-based classifier so we don't need an extra LLM call for routing.

def _classify_intent(message: str) -> str:
    """
    Returns one of:
      'simulation_request'   — user wants to run a flood simulation
      'weather_query'        — user wants weather data only
      'status_query'         — user asks about simulation results
      'general'              — everything else
    """
    m = message.lower()
    sim_kws   = ["simulat", "run", "trigger", "flood", "evacuat", "model", "predict"]
    wx_kws    = ["weather", "rain", "rainfall", "precipitation", "forecast", "climate"]
    stat_kws  = ["result", "status", "how many", "evacuated", "summary", "report"]

    sim_score  = sum(1 for k in sim_kws  if k in m)
    wx_score   = sum(1 for k in wx_kws   if k in m)
    stat_score = sum(1 for k in stat_kws if k in m)

    # Simulation wins over weather when both present (e.g. "run sim with rainfall")
    if sim_score >= 1 and sim_score >= wx_score:
        return "simulation_request"
    if wx_score >= 1:
        return "weather_query"
    if stat_score >= 1:
        return "status_query"
    return "general"


def _extract_hobli(message: str) -> str | None:
    """
    Heuristic hobli extractor — looks for 'for/in/at <Hobli>' patterns,
    then falls back to fuzzy-matching any word in the message against
    known hobli keys.
    Returns the raw string or None.
    """
    import re
    patterns = [
        r"for\s+([\w\s\-\.]+?)(?:\s+hobli|\s+area|\s+region|\.|$)",
        r"in\s+([\w\s\-\.]+?)(?:\s+hobli|\s+area|\s+region|\.|$)",
        r"at\s+([\w\s\-\.]+?)(?:\s+hobli|\s+area|\s+region|\.|$)",
    ]
    for pat in patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) >= 3:
                return candidate

    # Fallback: try every word/phrase in the message against the hobli resolver
    from genai.param_resolver import resolve_hobli
    # Try longest-first multi-word substrings then single words
    words = message.strip().split()
    # Try 3-word, 2-word, 1-word windows
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            candidate = " ".join(words[i:i + size])
            if len(candidate) < 3:
                continue
            # Skip pure simulation keywords
            if candidate.lower() in ("simulate", "run", "trigger", "flood", "model"):
                continue
            if resolve_hobli(candidate) is not None:
                return candidate
    return None


# ── Simulation parameter extractor ─────────────────────────────────────────────

def _extract_sim_params(message: str) -> dict:
    """
    Extract simulation parameters from a single natural-language message.
    Enables zero-dialogue simulation when the user provides all needed info.

    Returns a dict with keys (all may be None if not found):
      mode         : 'realtime' | 'historical' | None
      scenario     : 1 | 2 | 3 | None   (maps conservative/moderate/severe)
      rainfall_mm  : float | None        (when user types a specific value)
    """
    import re
    m = message.lower()

    # ── Mode ──────────────────────────────────────────────────────────────────
    realtime_kws  = ("realtime", "real-time", "real time", "current", "live", "now", "today")
    historical_kws = ("historical", "history", "imd", "past", "recorded", "archive")

    mode = None
    if any(k in m for k in realtime_kws):
        mode = "realtime"
    elif any(k in m for k in historical_kws):
        mode = "historical"

    # ── Scenario severity ─────────────────────────────────────────────────────
    low_kws    = ("low", "conservative", "mild", "light", "minor")
    medium_kws = ("moderate", "medium", "average", "typical", "normal")
    high_kws   = ("severe", "high", "extreme", "heavy", "intense", "major", "critical")

    scenario = None
    if any(k in m for k in high_kws):
        scenario = 3
    elif any(k in m for k in medium_kws):
        scenario = 2
    elif any(k in m for k in low_kws):
        scenario = 1

    # ── Direct mm value ───────────────────────────────────────────────────────
    rainfall_mm = None
    mm_match = re.search(r"(\d+\.?\d*)\s*mm", message, re.IGNORECASE)
    if mm_match:
        rainfall_mm = float(mm_match.group(1))

    return {"mode": mode, "scenario": scenario, "rainfall_mm": rainfall_mm}

def _compute_historical_scenarios(hobli_info: dict) -> tuple[float, float, float, int]:
    """
    Compute three rainfall scenarios from IMD historical records:
      scenario_low    ≈ 50th percentile
      scenario_medium ≈ 75th percentile
      scenario_high   ≈ 90th percentile

    Returns (low, medium, high, record_count)
    All values are clamped to [rain_min, rain_max].
    """
    from region_manager import RAINFALL_DATA
    from genai.param_resolver import clamp_rainfall

    all_records: list[dict] = []
    for match_key in hobli_info.get("matches", [hobli_info.get("key", "")]):
        all_records.extend(RAINFALL_DATA.get(match_key, []))

    values = sorted(
        float(r["actual_mm"])
        for r in all_records
        if r.get("actual_mm") is not None and float(r.get("actual_mm", 0)) > 0
    )
    n = len(values)

    rain_mean = hobli_info.get("rain_mean", 110.0)
    rain_std  = hobli_info.get("rain_std",  42.0)

    if n >= 5:
        low    = values[int(0.50 * (n - 1))]
        medium = values[int(0.75 * (n - 1))]
        high   = values[int(0.90 * (n - 1))]
    elif n >= 1:
        # Sparse data: use mean ± fractions of std
        low    = rain_mean - 0.3 * rain_std
        medium = rain_mean + 0.3 * rain_std
        high   = rain_mean + 0.8 * rain_std
    else:
        # No records: Bengaluru climatology fallback
        low, medium, high = 80.0, 120.0, 170.0

    low    = clamp_rainfall(low,    hobli_info)
    medium = clamp_rainfall(medium, hobli_info)
    high   = clamp_rainfall(high,   hobli_info)

    return low, medium, high, n


# ── Main pipeline class ───────────────────────────────────────────────────────

class MCPPipeline:
    """
    Stateless orchestrator — all state lives in the session store.

    Usage (FastAPI endpoint):
        pipeline = MCPPipeline()
        async for chunk in pipeline.handle(message, session_id):
            yield f"data: {json.dumps({'text': chunk})}\\n\\n"
    """

    async def handle(
        self,
        message:    str,
        session_id: str = "default",
    ) -> AsyncGenerator[str, None]:
        """
        Entry point for the React chat panel.
        Yields markdown text chunks for SSE streaming.
        """
        session = _get_or_create_session(session_id)
        agent   = session["agent"]
        state   = session["state"]

        intent = _classify_intent(message)
        log.info("handle: session=%s intent=%s msg=%r state_keys=%s",
                 session_id, intent, message[:60], list(state.keys()))

        # ── Branch: pending scenario selection (historical) ───────────────────
        if state.get("awaiting_scenario_selection"):
            log.debug("→ branch: awaiting_scenario_selection")
            async for chunk in self._handle_scenario_selection(message, state, agent):
                yield chunk
            return

        # ── Branch: pending rainfall confirmation ─────────────────────────────
        if state.get("awaiting_rainfall_confirmation"):
            log.debug("→ branch: awaiting_rainfall_confirmation")
            async for chunk in self._handle_rainfall_confirmation(message, state, session_id, agent):
                yield chunk
            return

        # ── Branch: pending mode selection (realtime vs historical) ───────────
        if state.get("awaiting_mode_selection"):
            log.debug("→ branch: awaiting_mode_selection")
            async for chunk in self._handle_mode_selection(message, state, agent):
                yield chunk
            return

        # ── Branch: simulation request ────────────────────────────────────────
        if intent == "simulation_request":
            log.debug("→ branch: simulation_request")
            async for chunk in self._handle_simulation_request(message, state, agent):
                yield chunk
            return

        # ── Branch: weather query ─────────────────────────────────────────────
        if intent == "weather_query":
            log.debug("→ branch: weather_query")
            async for chunk in self._handle_weather_query(message, agent):
                yield chunk
            return

        # ── Default: hand off to Ollama agent ─────────────────────────────────
        log.debug("→ branch: general/ollama fallback")
        async for chunk in agent.astream(message):
            yield chunk

    # ── Simulation request handler ────────────────────────────────────────────

    async def _handle_simulation_request(
        self, message: str, state: dict, agent: AsyncOllamaAgent
    ) -> AsyncGenerator[str, None]:
        """Step 1: extract hobli, then start the guided rainfall-source dialogue."""
        hobli_name = _extract_hobli(message)
        log.debug("_handle_simulation_request: extracted hobli=%r", hobli_name)

        if not hobli_name:
            async for chunk in agent.astream(message):
                yield chunk
            return

        from genai.param_resolver import resolve_hobli
        hobli_info = resolve_hobli(hobli_name)
        log.debug("_handle_simulation_request: resolve_hobli(%r) → %s",
                  hobli_name, hobli_info.get('display') if hobli_info else None)

        if hobli_info is None:
            yield (
                f"❓ I couldn't find **{hobli_name}** in the hobli coordinate map.\n\n"
                f"Please check the spelling or use the region selector in the main "
                f"dashboard. Common examples: *Sarjapura*, *Marathahalli*, *Jala*, "
                f"*Yelahanka*."
            )
            return

        state["pending_hobli_name"]    = hobli_name
        state["pending_hobli_display"] = hobli_info["display"]
        state["pending_hobli_info"]    = hobli_info
        state["original_message"]      = message

        # ── Extract extra params from the message ─────────────────────────────
        sim_params = _extract_sim_params(message)
        log.debug("_handle_simulation_request: sim_params=%s", sim_params)

        # ── FAST PATH: all necessary params found in the single prompt ─────────
        # Case A: direct mm value provided
        if sim_params["rainfall_mm"] is not None:
            from genai.param_resolver import clamp_rainfall
            rainfall_mm = clamp_rainfall(sim_params["rainfall_mm"], hobli_info)
            state["confirmed_rainfall_mm"]          = rainfall_mm
            state["confirmed_rainfall_source"]      = f"direct ({sim_params['rainfall_mm']} mm from prompt)"
            state["confirmed_rainfall_scenario"]    = ""
            state["awaiting_rainfall_confirmation"] = True
            log.info("_handle_simulation_request: fast-path via direct mm=%.1f", rainfall_mm)
            yield (
                f"## 🌊 Flood Simulation — {hobli_info['display']}\n\n"
                f"Using **{rainfall_mm} mm** rainfall from your prompt _(original: {sim_params['rainfall_mm']} mm, "
                f"clamped to valid range [{hobli_info['rain_min']}–{hobli_info['rain_max']}] mm)_.\n\n"
            )
            yield prompts.simulation_confirmation_prompt(
                hobli_display=hobli_info["display"],
                rainfall_mm=rainfall_mm,
                source=state["confirmed_rainfall_source"],
            )
            return

        # Case B: historical mode + scenario severity both specified
        if sim_params["mode"] == "historical" and sim_params["scenario"] is not None:
            low, medium, high, record_count = _compute_historical_scenarios(hobli_info)
            scenario_map = {1: ("conservative", low), 2: ("moderate", medium), 3: ("severe", high)}
            label, rainfall_mm = scenario_map[sim_params["scenario"]]
            state["confirmed_rainfall_mm"]          = rainfall_mm
            state["confirmed_rainfall_source"]      = f"historical-IMD-{label}"
            state["confirmed_rainfall_scenario"]    = label
            state["awaiting_rainfall_confirmation"] = True
            log.info("_handle_simulation_request: fast-path historical %s=%.1f mm", label, rainfall_mm)
            yield (
                f"## 🌊 Flood Simulation — {hobli_info['display']}\n\n"
                f"📈 Using **IMD historical {label} scenario** ({rainfall_mm} mm) — "
                f"drawn from {record_count} monsoon records.\n\n"
            )
            yield prompts.simulation_confirmation_prompt(
                hobli_display=hobli_info["display"],
                rainfall_mm=rainfall_mm,
                source=f"historical IMD ({label} scenario)",
                scenario_label=f"{label.capitalize()} — {rainfall_mm} mm",
            )
            return

        # Case C: realtime mode specified (no mm needed — fetch it)
        if sim_params["mode"] == "realtime":
            state["awaiting_mode_selection"] = True
            # Pre-answer the mode question and immediately process it
            async for chunk in self._handle_mode_selection("realtime", state, agent):
                yield chunk
            return

        # ── GUIDED PATH: not enough info — show full dialogue ─────────────────
        state["awaiting_mode_selection"] = True

        matches_note = ""
        if len(hobli_info["matches"]) > 1:
            matches_note = (
                f"\n\n> 📍 **Multiple variants found:** {', '.join(hobli_info['matches'])}. "
                f"I'll use **{hobli_info['display']}** (primary match)."
            )

        yield (
            f"## 🌊 Flood Simulation Request — {hobli_info['display']}\n\n"
            f"**Location:** {hobli_info['lat']:.4f}°N, {hobli_info['lon']:.4f}°E  \n"
            f"**District:** {hobli_info.get('district', 'N/A')}  \n"
        )
        yield prompts.rainfall_mode_question(
            hobli_display=hobli_info["display"],
            rain_min=hobli_info["rain_min"],
            rain_max=hobli_info["rain_max"],
            rain_mean=hobli_info["rain_mean"],
            rain_std=hobli_info["rain_std"],
            matches_note=matches_note,
        )


    # ── Mode selection ────────────────────────────────────────────────────────

    async def _handle_mode_selection(
        self, message: str, state: dict, agent: AsyncOllamaAgent
    ) -> AsyncGenerator[str, None]:
        """Step 2: user picked rainfall mode (realtime or historical)."""
        m = message.strip().lower()
        if m in ("1", "realtime", "real-time", "real time", "current", "live", "now"):
            mode = "realtime"
        elif m in ("2", "historical", "history", "past", "sample"):
            mode = "historical"
        else:
            yield "❓ Please type **1** (real-time) or **2** (historical) to choose the rainfall source."
            return

        hobli_display = state.get("pending_hobli_display", state.get("pending_hobli_name", ""))
        hobli_info    = state.get("pending_hobli_info", {})

        # ── REALTIME branch ───────────────────────────────────────────────────
        if mode == "realtime":
            yield f"\n⏳ Fetching real-time rainfall for **{hobli_display}** from Open-Meteo...\n\n"
            log.info("_handle_mode_selection: fetching realtime weather for %s", hobli_display)

            wx_result = get_weather_tool.run(hobli_display, mode="realtime")
            log.debug("_handle_mode_selection: wx_result ok=%s rainfall_mm_clamped=%s",
                      wx_result.get('ok'), wx_result.get('rainfall_mm_clamped'))

            if not wx_result.get("ok"):
                yield f"❌ Weather fetch failed: {wx_result.get('error')}\n\nFalling back to historical mean.\n\n"
                from genai.param_resolver import sample_historical
                rainfall_mm = sample_historical(hobli_info)
                source_note = "realtime-failed → historical mean fallback"
                weather, clamp_note = {}, ""
            else:
                rainfall_mm = wx_result["rainfall_mm_clamped"]
                source_note = "open-meteo realtime"
                weather     = wx_result.get("weather", {})
                clamp_note  = wx_result.get("clamp_note", "")

            state["confirmed_rainfall_mm"]          = rainfall_mm
            state["confirmed_rainfall_source"]      = source_note
            state["confirmed_rainfall_scenario"]    = ""
            state["awaiting_mode_selection"]        = False
            state["awaiting_rainfall_confirmation"] = True

            yield prompts.realtime_rainfall_table(
                hobli_display=hobli_display,
                rainfall_mm=rainfall_mm,
                source_note=source_note,
                condition=weather.get("description", "N/A"),
                temp_c=weather.get("temp_c", "N/A"),
                rain_min=hobli_info.get("rain_min", "N/A"),
                rain_max=hobli_info.get("rain_max", "N/A"),
                clamp_note=clamp_note,
            )
            yield prompts.simulation_confirmation_prompt(
                hobli_display=hobli_display,
                rainfall_mm=rainfall_mm,
                source=source_note,
            )

        # ── HISTORICAL branch — Ollama reasons over 3 scenarios ───────────────
        else:
            yield f"\n🔍 Analysing historical rainfall records for **{hobli_display}** (IMD monsoon data)...\n\n"
            log.info("_handle_mode_selection: computing 3 historical scenarios for %s", hobli_display)

            low, medium, high, record_count = _compute_historical_scenarios(hobli_info)
            log.info("_handle_mode_selection: scenarios low=%.1f medium=%.1f high=%.1f (%d records)",
                     low, medium, high, record_count)

            # Store scenarios in session state for later selection
            state["historical_scenarios"]     = {"low": low, "medium": medium, "high": high}
            state["awaiting_mode_selection"]  = False
            state["awaiting_scenario_selection"] = True

            # Build the reasoning prompt and send to Ollama
            reasoning_prompt = prompts.historical_scenario_reasoning_prompt(
                hobli_display=hobli_display,
                district=hobli_info.get("district", "Bengaluru"),
                record_count=record_count,
                rain_mean=hobli_info.get("rain_mean", 110.0),
                rain_std=hobli_info.get("rain_std", 42.0),
                rain_min=hobli_info.get("rain_min", 35.0),
                rain_max=hobli_info.get("rain_max", 220.0),
                scenario_low=low,
                scenario_medium=medium,
                scenario_high=high,
            )

            log.info("_handle_mode_selection: calling Ollama one-shot for scenario reasoning")
            async for chunk in agent.astream_one_shot(reasoning_prompt):
                yield chunk

    # ── Scenario selection ────────────────────────────────────────────────────

    async def _handle_scenario_selection(
        self, message: str, state: dict, agent: AsyncOllamaAgent
    ) -> AsyncGenerator[str, None]:
        """
        Step 3 (historical path): user picked one of the 3 rainfall scenarios.
        Accepts "1"/"conservative", "2"/"moderate", "3"/"severe".
        """
        m = message.strip().lower()
        scenarios = state.get("historical_scenarios", {})
        hobli_display = state.get("pending_hobli_display", state.get("pending_hobli_name", ""))
        hobli_info    = state.get("pending_hobli_info", {})

        scenario_map = {
            "1": ("conservative", scenarios.get("low",    80.0)),
            "conservative": ("conservative", scenarios.get("low",    80.0)),
            "low":          ("conservative", scenarios.get("low",    80.0)),
            "2": ("moderate", scenarios.get("medium", 120.0)),
            "moderate": ("moderate", scenarios.get("medium", 120.0)),
            "medium":   ("moderate", scenarios.get("medium", 120.0)),
            "3": ("severe", scenarios.get("high",   170.0)),
            "severe": ("severe", scenarios.get("high",   170.0)),
            "high":   ("severe", scenarios.get("high",   170.0)),
        }

        if m not in scenario_map:
            yield (
                "❓ Please type **1** (conservative), **2** (moderate), or **3** (severe) "
                "to select a rainfall scenario."
            )
            return

        label, rainfall_mm = scenario_map[m]
        log.info("_handle_scenario_selection: selected %s → %.1f mm", label, rainfall_mm)

        state["confirmed_rainfall_mm"]          = rainfall_mm
        state["confirmed_rainfall_source"]      = f"historical-IMD-{label}"
        state["confirmed_rainfall_scenario"]    = label
        state["awaiting_scenario_selection"]    = False
        state["awaiting_rainfall_confirmation"] = True

        yield prompts.simulation_confirmation_prompt(
            hobli_display=hobli_display,
            rainfall_mm=rainfall_mm,
            source=f"historical IMD ({label} scenario)",
            scenario_label=f"{label.capitalize()} — {rainfall_mm} mm",
        )

    # ── Rainfall confirmation ─────────────────────────────────────────────────

    async def _handle_rainfall_confirmation(
        self, message: str, state: dict, session_id: str, agent: AsyncOllamaAgent
    ) -> AsyncGenerator[str, None]:
        """Step 4: user confirmed — run simulation, or cancel."""
        m = message.strip().lower()

        if m in ("no", "cancel", "stop", "n", "abort"):
            state.clear()
            yield "✅ Simulation cancelled. You can start a new request anytime."
            return

        if m not in ("yes", "y", "ok", "proceed", "confirm", "run", "go"):
            yield "❓ Please type **yes** to confirm or **no** to cancel."
            return

        hobli_display = state.get("pending_hobli_display", state.get("pending_hobli_name", ""))
        rainfall_mm   = state.get("confirmed_rainfall_mm", 150.0)
        source        = state.get("confirmed_rainfall_source", "unknown")
        hobli_info    = state.get("pending_hobli_info", {})

        log.info("_handle_rainfall_confirmation: CONFIRMED — hobli=%s rainfall=%.1f mm source=%s",
                 hobli_display, rainfall_mm, source)

        state.clear()

        yield prompts.simulation_launch_message(hobli_display, rainfall_mm)

        # ── Run simulation in thread executor to avoid event-loop deadlock ────
        import asyncio
        loop = asyncio.get_event_loop()

        log.info("_handle_rainfall_confirmation: dispatching run_simulation_tool to thread executor")

        def _run_sim():
            return run_simulation_tool.run(
                hobli_name  = hobli_display,
                rainfall_mm = rainfall_mm,
                steps       = 20,
                algorithm   = "ga",
                use_traffic = True,   # always on for SimHelper sessions
            )

        result = await loop.run_in_executor(None, _run_sim)
        log.info("_handle_rainfall_confirmation: simulation returned ok=%s", result.get('ok'))

        if not result.get("ok"):
            yield f"❌ **Simulation failed:** {result.get('error')}\n"
            return

        summary  = result.get("summary", {})
        shelters = summary.get("shelter_reports", [])

        # ── Emit metrics table (from prompts.py) ─────────────────────────────
        yield prompts.simulation_metrics_table(
            hobli_display   = hobli_display,
            rainfall_mm     = rainfall_mm,
            algorithm       = summary.get("algorithm", "GA"),
            total_population= summary.get("simulation_population", 0),
            at_risk_initial = summary.get("total_at_risk_initial", 0),
            total_evacuated = summary.get("total_evacuated", 0),
            at_risk_remaining= summary.get("total_at_risk_remaining", 0),
            success_rate    = summary.get("success_rate_pct", 0),
            exec_time       = summary.get("ga_execution_time", "N/A"),
        )

        if shelters:
            yield prompts.shelter_occupancy_table(shelters)

        # ── Ollama narrative commentary ───────────────────────────────────────
        yield "\n\n---\n\n### 🤖 SimHelper Analysis\n\n"
        log.info("_handle_rainfall_confirmation: requesting Ollama narrative for results")
        narrative_prompt = prompts.sim_result_narrative_prompt(
            hobli_display  = hobli_display,
            rainfall_mm    = rainfall_mm,
            total_population = summary.get("simulation_population", 0),
            at_risk        = summary.get("total_at_risk_initial",   0),
            evacuated      = summary.get("total_evacuated",          0),
            still_at_risk  = summary.get("total_at_risk_remaining",  0),
            success_rate   = summary.get("success_rate_pct",         0),
            algorithm      = summary.get("algorithm", "GA"),
            exec_time      = summary.get("ga_execution_time",       0),
            shelter_count  = len(shelters),
        )
        async for chunk in agent.astream_one_shot(narrative_prompt):
            yield chunk

        # ── Ollama route insights (structured 4-section analysis) ─────────────
        evacuation_plan = result.get("evacuation_plan", [])
        yield "\n\n---\n\n### 🗺️ Route Analysis\n\n"
        log.info("_handle_rainfall_confirmation: requesting Ollama route insights")
        ri_prompt = prompts.route_insights_prompt(
            hobli_display   = hobli_display,
            rainfall_mm     = rainfall_mm,
            algorithm       = summary.get("algorithm", "GA"),
            total_evacuated = summary.get("total_evacuated", 0),
            success_rate    = summary.get("success_rate_pct", 0),
            shelters        = shelters,
            evacuation_plan = evacuation_plan,
        )
        async for chunk in agent.astream_one_shot(ri_prompt):
            yield chunk

        # ── Emit control tokens for frontend ─────────────────────────────────
        # SIM_DONE: triggers "View Map" banner + map navigation
        yield f"\x00SIM_DONE:{hobli_display}:{rainfall_mm}"

        # SIM_META: carries full summary JSON for the inline SimResultPanel
        meta_payload = {
            "hobli":          hobli_display,
            "rainfall_mm":    rainfall_mm,
            "summary":        summary,
            "shelters":       shelters[:10],  # top 10 for panel display
            "evacuation_plan": evacuation_plan[:50],  # zone assignments (capped)
        }
        meta_b64 = base64.b64encode(
            json.dumps(meta_payload).encode()
        ).decode()
        yield f"\x00SIM_META:{meta_b64}"

    # ── Weather query ─────────────────────────────────────────────────────────

    async def _handle_weather_query(
        self, message: str, agent: AsyncOllamaAgent
    ) -> AsyncGenerator[str, None]:
        """Weather-only query — route through Ollama so it can call get_weather."""
        async for chunk in agent.astream(message):
            yield chunk


# ── Module-level singleton ────────────────────────────────────────────────────
_pipeline_instance: MCPPipeline | None = None


def get_pipeline() -> MCPPipeline:
    """Return the module-level MCPPipeline singleton."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = MCPPipeline()
    return _pipeline_instance
