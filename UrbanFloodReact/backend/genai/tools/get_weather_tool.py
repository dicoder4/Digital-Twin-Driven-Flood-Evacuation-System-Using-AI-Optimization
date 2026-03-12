"""
get_weather_tool.py
────────────────────
MCP-style tool: resolve hobli, fetch weather, clamp rainfall to valid range.

This tool is called by the Ollama agent when the user's intent is to get
weather data for a hobli before running a simulation.

Tool schema (for Ollama tool-calling JSON):
{
  "name": "get_weather",
  "description": "Fetch real-time or historical rainfall data for a Bengaluru hobli. Always returns a rainfall_mm value clamped to the historically valid range for that hobli.",
  "parameters": {
    "type": "object",
    "properties": {
      "hobli_name":  {"type": "string",  "description": "Name of the hobli (e.g. 'Sarjapura', 'Marathahalli')"},
      "mode":        {"type": "string",  "enum": ["realtime", "historical"], "description": "Whether to fetch live weather or historical archive"},
      "days_back":   {"type": "integer", "description": "For historical mode: how many days to look back (default 1)"}
    },
    "required": ["hobli_name", "mode"]
  }
}
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Ensure backend root is on path ────────────────────────────────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from genai.param_resolver import resolve_hobli, clamp_rainfall
from genai.weather_client import WeatherClient

# ── Ollama tool descriptor (used in ollama_agent.py tool list) ────────────────
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Fetch real-time or historical rainfall data for a Bengaluru hobli. "
            "Always returns a rainfall_mm value clamped to the historically valid "
            "range for that hobli — never an arbitrary number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "hobli_name": {
                    "type":        "string",
                    "description": "Name of the hobli (e.g. 'Sarjapura', 'Marathahalli', 'Jala')",
                },
                "mode": {
                    "type":        "string",
                    "enum":        ["realtime", "historical"],
                    "description": "Use 'realtime' for current weather; 'historical' for past rainfall.",
                },
                "days_back": {
                    "type":        "integer",
                    "description": "For historical mode only: days to look back (default 1).",
                },
            },
            "required": ["hobli_name", "mode"],
        },
    },
}


def run(hobli_name: str, mode: str = "realtime", days_back: int = 1) -> dict:
    """
    Execute the get_weather tool.

    Returns
    -------
    dict
        {
          "ok": bool,
          "hobli_info": {...},          # from param_resolver
          "weather": {...},             # from weather_client
          "rainfall_mm_clamped": float, # safe value to pass to simulation
          "rainfall_source": str,       # "realtime" | "historical" | "fallback"
          "clamp_note": str,            # human-readable note on clamping
          "error": str | None,
        }
    """
    # 1. Resolve hobli → coords + valid range
    hobli_info = resolve_hobli(hobli_name)
    if hobli_info is None:
        return {
            "ok": False,
            "error": f"Hobli '{hobli_name}' not found in coordinate map. "
                     f"Try a different spelling or check /regions for valid names.",
            "hobli_info": None,
            "weather": None,
            "rainfall_mm_clamped": None,
            "rainfall_source": None,
            "clamp_note": None,
        }

    # 2. Fetch weather
    client = WeatherClient.from_hobli_info(hobli_info)
    if mode == "realtime":
        weather = client.get_current()
    else:
        weather = client.get_historical(days_back=max(1, days_back))

    # 3. Clamp rainfall to valid range
    raw_mm = weather.get("precipitation_mm")
    if raw_mm is None:
        # Source failed — use historical mean as safe fallback
        raw_mm = hobli_info["rain_mean"]
        rainfall_source = "fallback"
        clamp_note = (
            f"Weather fetch failed; using historical mean "
            f"({raw_mm} mm) for {hobli_info['display']}."
        )
    else:
        rainfall_source = mode
        clamped = clamp_rainfall(raw_mm, hobli_info)
        clamp_note = None
        if clamped != raw_mm:
            clamp_note = (
                f"Raw value {raw_mm} mm was outside the valid range "
                f"[{hobli_info['rain_min']}–{hobli_info['rain_max']}] mm "
                f"for {hobli_info['display']}; clamped to {clamped} mm."
            )
        raw_mm = clamped

    return {
        "ok":                  True,
        "hobli_info":          hobli_info,
        "weather":             weather,
        "rainfall_mm_clamped": raw_mm,
        "rainfall_source":     rainfall_source,
        "clamp_note":          clamp_note,
        "error":               None,
    }
