# UrbanFloodReact GenAI Module (`SimHelper`)

The **GenAI** module acts as the conversational and intelligent orchestrator for the Urban Flood Digital Twin System. Powered by a local Ollama agent (`llama3`), it bridges the gap between natural language user requests (from emergency responders or city officials) and the complex, technical backend simulation algorithms (Genetic Algorithm, Ant Colony Optimization, Particle Swarm Optimization).

It is designed with strict **safety, truthfulness, and transparency** principles. The agent refuses to guess arbitrary simulation parameters (like rainfall levels) and strictly sources all driving data from historically validated records or live meteorological sources. 

## Features

- **Natural Language Interaction:** Allows users to request flood simulations, ask about current weather conditions, and review shelter network statuses conversationally.
- **Guided Dialogue for Parameter Sourcing:** When a user requests a simulation, the agent guides them through a step-by-step state machine to determine the most accurate rainfall parameter (either utilizing real-time live data via Open-Meteo or historical Indian Meteorological Department (IMD) monsoon statistics).
- **Automated Weather Grounding:** Automatically resolves informal regional names (like "kr pura") to exact GPS coordinates, bounding all rainfall values to historically possible ranges to prevent unrealistic ("hallucinated") scenarios.
- **SSE Streaming Support:** Integrated closely with FastAPI SSE (Server-Sent Events) to provide real-time, typewriter-effect interaction loops in the React frontend.
- **Narrative AI Summarisation:** Post-simulation, the agent writes tailored narrative insights, analyzing shelter occupancy limits, route bottlenecks, and evacuation success percentages.

## Core Architecture

### `mcp_pipeline.py`
The overarching entry point and State Machine orchestrator.
- Evaluates the user's intent: Simulation vs Weather vs General Info.
- Manages browser-session conversational states (handling `SESSION_TTL`, awaiting user inputs for mode/scenario).
- Emits formatted SSE output (markdown tables, text chunks, mapping tokens like `\x00SIM_META:`) to the React frontend.

### `ollama_agent.py`
The intelligence core of the module.
- Represents a stateful session communicating with the locally hosted `llama3.2:latest` server running on port `11434`.
- Employs a strict "Tool-First" ideology, ensuring it utilizes `get_weather` and `run_simulation` programmatically.
- Exposes `astream` and `astream_one_shot` iterators for FastAPI to consume and stream seamlessly.

### `param_resolver.py`
The semantic mapping engine.
- Contains the fuzzy-matching logic to resolve "fuzzy" operator inputs (e.g., "Sarjapura") to the exact backend region definitions (e.g., "sarjapura-1").
- Enforces the absolute **Rainfall Hard Cap**, computing statistically valid `min / max / mean / std` boundaries dynamically utilizing `region_manager` data to ensure simulations remain physically realistic.

### `weather_client.py`
The meteorological adapter.
- Interfaces freely with Open-Meteo APIs (Archive and Forecast).
- Implements Geocoding fallbacks for dynamically mapping arbitrary regions.
- Supplies the agent with `precipitation_mm`, `temperature`, `wind_speed`, and qualitative `description` data.

### `prompts.py`
A centralized string repository ensuring decoupling of code and copy.
- Defines the core "SimHelper System Prompt", establishing the strict agent rules.
- Contains markdown layout templates for standard outputs (e.g., Metric Tables, Shelter Configurations, Historical Reasonings).

### `tools/` Directory
Contains the strictly-defined function signature descriptors (`TOOL_SCHEMA`) for Ollama's native tool-calling protocol.
- **`get_weather_tool.py`**: Executes the `load_weather` lifecycle, fetching from `weather_client` and aggressively clamping the resulting rainfall using `param_resolver` constraints.
- **`run_simulation_tool.py`**: Orchestrates the underlying backend system. POSTs to `/load-region` to cache the routing graph, then initiates an asynchronous SSE connection with `/simulate-stream` to track the GA/ACO/PSO algorithms and generate the final evacuation reports.
