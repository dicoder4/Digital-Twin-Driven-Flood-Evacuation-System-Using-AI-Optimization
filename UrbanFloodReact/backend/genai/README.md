# GenAI Module - Urban Flood Evacuation System

This directory contains the Generative AI (GenAI) integration scripts that power the intelligent advisory, natural language chat, and MCP-based agentic access for the Digital Twin-Driven Flood Evacuation System.

## Overview of Components

### 1. Context Builder (`context_builder.py`)
Enriches raw simulation output into structured context for LLM consumption:
- Classifies shelter severity: **CRITICAL** (≥90%), **HIGH** (≥60%), **MODERATE**, **EMPTY**
- Computes evacuation route statistics (avg/max/min distances, routes to critical shelters)
- Provides a `shelter_overview` with remaining capacity totals

### 2. Panel of Experts (`expert_panel.py`)
Streams actionable intelligence from three distinct AI personas:
- **Logistics Chief**: Analyzes shelter capacity and proposes resource allocation/transfer plans.
- **Tactical Commander**: Inspects evacuation routes and issues NDRF deployment instructions.
- **Civic Authority**: Generates situation reports and drafts public warnings.

**Model Fallback Chain:**
1. **Groq API** (`llama-3.1-8b-instant`) — primary, cloud-hosted, ~750 tok/s
2. **Ollama** (`llama3.2:latest`) — fallback 1 (peer's machine)
3. **Ollama** (`gemma3:1b`) — fallback 2 (local, 815 MB)

### 3. Evacuation Chat (`evacuation_chat.py`)
Free-form natural language Q&A about the evacuation simulation data:
- User asks "Why is Hebbal School overloaded?" → LLM answers using only simulation context
- Same Groq → Ollama fallback chain
- Streaming SSE response

### 4. MCP Evacuation Server (`mcp_evacuation_server.py`)
Exposes the GenAI module as **MCP tools and resources** for agentic AI access:

**Tools:**
| Tool | Description |
|---|---|
| `get_simulation_state` | Returns current simulation summary & shelter overview |
| `get_shelter_status` | Detailed shelter occupancy with severity classification |
| `get_route_summary` | Evacuation route statistics (distances, group sizes) |
| `get_expert_analysis(persona)` | AI expert advice (logistics/tactical/civic) |
| `ask_evacuation_question(question)` | Free-form Q&A about evacuation data |

**Resources:**
| URI | Description |
|---|---|
| `evacuation://simulation/summary` | Raw simulation summary as JSON |
| `evacuation://simulation/context` | Enriched context (with severity, route stats) as JSON |

**Usage:**
```bash
python genai/mcp_evacuation_server.py       # stdio transport (default)
```

### 5. MCP Weather Integration (`mcp_weather_server.py` & `mcp_weather_client.py`)
Fetches real-time weather information using the Model Context Protocol (MCP):
- **`mcp_weather_client.py`**: Connects to `@modelcontextprotocol/server-weather` via stdio
- **`mcp_weather_server.py`**: FastMCP server exposing `get_current_weather` as a tool

## Setup Instructions

1. **Environment Variables**: Make sure your `.env` file contains your Groq API key:
   ```env
   GROQ_API_KEY=your_key_here
   ```
2. **Offline Fallback**: Ensure Ollama is installed with `llama3.2:latest` or `gemma3:1b` pulled.
3. **MCP Requirements**: `pip install mcp` for the MCP server/client SDK.
