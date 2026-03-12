"""
run_simulation_tool.py
────────────────────────
MCP-style tool: trigger a flood simulation for a hobli via the backend API.

This tool is called by the MCP pipeline after the user confirms rainfall
parameters.  It POSTs to the FastAPI backend's /load-region endpoint first
(to ensure the graph is loaded), then streams /simulate-stream and returns
a summary dict when the stream completes.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

log = logging.getLogger("run_simulation_tool")

# ── Backend base URL ──────────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("FLOOD_BACKEND_URL", "http://localhost:8000")

# ── Ollama tool descriptor ────────────────────────────────────────────────────
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_simulation",
        "description": (
            "Trigger a flood simulation for a Bengaluru hobli using pre-validated "
            "rainfall parameters.  The hobli graph is lazy-loaded if needed.  "
            "Returns an evacuation summary with algorithm results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hobli_name": {
                    "type":        "string",
                    "description": "Display name of the hobli to simulate.",
                },
                "rainfall_mm": {
                    "type":        "number",
                    "description": "Rainfall in mm — must have been validated by get_weather first.",
                },
                "steps": {
                    "type":        "integer",
                    "description": "Simulation steps (default 20, range 5–50).",
                },
                "algorithm": {
                    "type":        "string",
                    "enum":        ["ga", "aco", "pso"],
                    "description": "Evacuation optimisation algorithm (default 'ga').",
                },
                "evacuation_mode": {
                    "type":        "boolean",
                    "description": "Scale population to 1% for quick testing.",
                },
                "use_traffic": {
                    "type":        "boolean",
                    "description": "Integrate TomTom live traffic into routing.",
                },
            },
            "required": ["hobli_name", "rainfall_mm"],
        },
    },
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _post_json(path: str, payload: dict) -> dict:
    """POST JSON to the local FastAPI backend. Returns parsed response dict."""
    url  = f"{BACKEND_URL}{path}"
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "UrbanFloodTwin/1.0"},
        method="POST",
    )
    log.debug("_post_json POST %s", url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        log.debug("_post_json response: %s", data)
        return data


def _build_qs(params: dict) -> str:
    """Build a URL-encoded query string from a dict."""
    return "&".join(
        f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
    )


def _stream_simulation(sim_params: dict) -> Optional[dict]:
    """
    Open /simulate-stream SSE endpoint and read until the final 'done' frame.

    Returns
    -------
    dict | None
        The final_report payload dict, or a dict with an 'error' key on failure,
        or None if the stream ended without a done frame.
    """
    qs  = _build_qs(sim_params)
    url = f"{BACKEND_URL}/simulate-stream?{qs}"
    log.info("_stream_simulation: connecting to %s", url)

    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    final_report = None

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            log.info("_stream_simulation: SSE connection open, reading frames...")
            buffer = b""
            frame_count = 0
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    log.info("_stream_simulation: stream closed after %d frames", frame_count)
                    break
                buffer += chunk
                while b"\n\n" in buffer:
                    event_bytes, buffer = buffer.split(b"\n\n", 1)
                    event_str = event_bytes.decode("utf-8").strip()
                    if not event_str.startswith("data:"):
                        continue
                    frame_count += 1
                    raw = event_str[5:].strip()
                    try:
                        payload = json.loads(raw)
                        if payload.get("done"):
                            log.info("_stream_simulation: received 'done' frame at frame %d", frame_count)
                            final_report = payload
                        elif frame_count % 5 == 0:
                            log.debug("_stream_simulation: step=%s/%s",
                                      payload.get("step"), payload.get("total"))
                    except json.JSONDecodeError:
                        pass  # ignore malformed SSE frames
    except urllib.error.URLError as exc:
        log.error("_stream_simulation: URLError — %s", exc)
        return {"error": f"URLError: {exc}"}
    except Exception as exc:
        log.error("_stream_simulation: unexpected error — %s", exc)
        return {"error": str(exc)}

    return final_report


# ── Public entry point ────────────────────────────────────────────────────────

def run(
    hobli_name:      str,
    rainfall_mm:     float,
    steps:           int  = 20,
    algorithm:       str  = "ga",
    evacuation_mode: bool = False,
    use_traffic:     bool = False,
) -> dict:
    """
    Execute the run_simulation tool.

    Workflow
    --------
    1. POST /load-region  — ensures the hobli road-graph is cached on the backend.
    2. GET  /simulate-stream (SSE) — streams flood steps + evacuation optimisation.
    3. Return a structured result summary dict.

    Returns
    -------
    dict  {"ok": bool, "hobli": str, "rainfall_mm": float,
           "algorithm": str, "summary": dict, "error": str|None}
    """
    steps = max(5, min(50, int(steps)))
    log.info("run: hobli=%s rainfall=%.1f steps=%d algo=%s evac=%s traffic=%s",
             hobli_name, rainfall_mm, steps, algorithm, evacuation_mode, use_traffic)

    # ── Step 1: Load region ───────────────────────────────────────────────────
    try:
        log.info("run: POST /load-region hobli=%s", hobli_name)
        load_resp = _post_json("/load-region", {"hobli": hobli_name})
        log.info("run: /load-region response status=%s", load_resp.get("status"))
        if load_resp.get("status") != "loaded":
            return {
                "ok":          False,
                "error":       f"Region load returned unexpected status: {load_resp}",
                "hobli":       hobli_name,
                "rainfall_mm": rainfall_mm,
                "algorithm":   algorithm,
                "summary":     None,
            }
    except Exception as exc:
        log.error("run: /load-region failed — %s", exc)
        return {
            "ok":          False,
            "error":       f"Could not reach backend at {BACKEND_URL}/load-region: {exc}",
            "hobli":       hobli_name,
            "rainfall_mm": rainfall_mm,
            "algorithm":   algorithm,
            "summary":     None,
        }

    # ── Step 2: Stream simulation ─────────────────────────────────────────────
    sim_params = {
        "hobli":           hobli_name,
        "rainfall_mm":     rainfall_mm,
        "steps":           steps,
        "algorithm":       algorithm,
        "evacuation_mode": str(evacuation_mode).lower(),
        "use_traffic":     str(use_traffic).lower(),
    }

    log.info("run: starting SSE stream /simulate-stream params=%s", sim_params)
    final_report = _stream_simulation(sim_params)

    if final_report is None:
        log.error("run: simulation stream ended without a 'done' frame")
        return {
            "ok":          False,
            "error":       "Simulation stream ended without a final 'done' frame. Check backend logs.",
            "hobli":       hobli_name,
            "rainfall_mm": rainfall_mm,
            "algorithm":   algorithm,
            "summary":     None,
        }

    if "error" in final_report:
        log.error("run: simulation returned error — %s", final_report["error"])
        return {
            "ok":          False,
            "error":       final_report["error"],
            "hobli":       hobli_name,
            "rainfall_mm": rainfall_mm,
            "algorithm":   algorithm,
            "summary":     None,
        }

    summary = final_report.get("summary", {})
    log.info("run: SUCCESS evacuated=%s success_rate=%s%%",
             summary.get("total_evacuated"), summary.get("success_rate_pct"))

    return {
        "ok":          True,
        "hobli":       hobli_name,
        "rainfall_mm": rainfall_mm,
        "algorithm":   algorithm,
        "summary":     summary,
        "error":       None,
    }
