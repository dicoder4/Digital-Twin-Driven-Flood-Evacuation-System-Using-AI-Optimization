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


---

## GenAI Integration — App Copilot & Expert Agent

The system features a dual-agent GenAI architecture designed to simplify complex workflows and provide deep analytical insights into evacuation outcomes.

### 1. App Copilot (Agentic Navigation & Control)

The **App Copilot** is an agentic LLM that lives in the main dashboard. It can "drive" the application by interpreting natural language commands and calling specific UI tools.

- **Capabilities**:
  - **Fuzzy Location Matching**: "Take me to Hebbel" automatically resolves to "Hebbal" and selects the region in the sidebar.
  - **Parameter Tuning**: "Set rainfall to 200mm and turn on live traffic" instantly updates the configuration state.
  - **Workflow Automation**: "Run a comparison for Marathahalli" will select the region, set the algorithm to 'All', and trigger the parallel simulation.
  - **Interactive Options**: When a command is ambiguous, the Copilot presents clickable "Option Chips" (e.g., *[▶ Start with defaults]* or *[📊 Start Compare Mode]*) to guide the user.

- **Example Prompts**:
  - *"Go to Yelahanka and run GA with 180mm rainfall"*
  - *"I want to compare all algorithms for Hebbal with live traffic"*
  - *"Enable evacuation mode for Marathahalli"*

### 2. GenAI Expert Agent (Post-Simulation Analysis)

Once a simulation (single or comparison) finishes, the **GenAI Agent** provides a grounded analysis of the results. It is "context-aware," meaning it receives the exact occupancy, success rates, and route data from the current run.

- **Panel of Experts**: Three distinct AI personas provide specialised advice:
  - **🚛 Logistics Chief**: Focuses on shelter supply chains and occupancy management.
  - **⚓ Tactical Commander**: Analyzes route efficiency and flood-avoidance performance.
  - **📢 Civic Authority**: Drafts communication templates for public alerts based on the evacuation map.
- **Guided Analysis Chat**: Users can ask free-form questions about the simulation results.
  - *"Which algorithm performed the best and why?"*
  - *"Show me the most overloaded shelter."*
  - *"Why did 12 people fail to reach a safe zone in this scenario?"*

### 3. Multi-Model Fallback Architecture

To ensure high availability, the GenAI module uses a robust three-tier fallback system:

1.  **Primary: Google Gemini 2.5 Flash** — High-speed, high-context model used for tool use and complex reasoning.
2.  **Fallback 1: Groq (Llama 3.3 70B)** — Automatically triggered if Gemini hits rate limits (429) or quota exhaustion. Provides near-instant response times for tool-calling.
3.  **Fallback 2: Offline Ollama (Llama 3.2)** — If no internet/API keys are available, the system attempts to reach a local Ollama instance to keep the chat functional.

---

---

## MCP Integration — External AI Agent Access

The system includes a dedicated **Model Context Protocol (MCP)** server, allowing external AI agents (like Claude Desktop or other MCP-compatible bots) to interact directly with the Digital Twin's simulation data.

- **File**: `backend/genai/mcp_evacuation_server.py`
- **Purpose**: Exposes the private simulation state as a set of standardized "tools" and "resources" that any MCP-compatible agent can use to perform autonomous analysis.

### Available MCP Tools
- `get_simulation_state`: Returns a high-level summary of the latest run (success rate, evacuee counts).
- `get_shelter_status`: Lists all shelters with real-time occupancy and severity levels (🔴 CRITICAL, 🟢 MODERATE, etc.).
- `get_route_summary`: Provides technical stats on the computed evacuation paths.
- `get_expert_analysis`: Forces a specific persona (Logistics/Tactical/Civic) to analyze the current data.
- `ask_evacuation_question`: Allows the external agent to ask free-form questions about the dashboard's state.

### Running the MCP Server
To expose the Digital Twin to external agents:
1. Ensure the main FastAPI backend is running (`uvicorn main:app`).
2. Start the MCP server:
   ```bash
   cd backend/genai
   python mcp_evacuation_server.py
   ```
The server will communicate over `stdio` by default, making it easy to plug into Claude Desktop's configuration.