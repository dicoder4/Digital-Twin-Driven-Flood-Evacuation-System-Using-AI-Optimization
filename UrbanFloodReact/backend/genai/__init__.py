"""
genai/ — GenAI + MCP Weather Pipeline for Urban Flood Digital Twin
─────────────────────────────────────────────────────────────────
Sub-package layout:
  mcp_pipeline.py       — Orchestrator: routes NL requests → tools
  weather_client.py     — Open-Meteo weather fetcher (no API key)
  param_resolver.py     — Hobli name → centroid coords + valid rainfall range
  ollama_agent.py       — Ollama (llama3) chat loop with tool-calling
  tools/
    get_weather_tool.py     — MCP tool: fetch real-time/historical weather
    run_simulation_tool.py  — MCP tool: trigger flood simulation
"""
