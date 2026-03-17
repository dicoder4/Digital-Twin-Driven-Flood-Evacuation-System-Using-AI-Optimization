# GenAI Module - Urban Flood Evacuation System

This directory contains the Generative AI (GenAI) integration scripts that power the intelligent advisory, natural language chat, and MCP-based agentic access for the Digital Twin-Driven Flood Evacuation System.

## Overview of Components

### 1. Context Builder (`context_builder.py`)
Enriches raw simulation output into structured tactical context:
- **Pressure Junctures**: Identifies critical bottlenecks where multiple evacuation paths converge or high volume meets flood risk.
- **Route Depth**: Provides detailed path information for the **top 25** evacuation groups (origin node, volume, distance).
- **Shelter Severity**: Classifies shelters: **CRITICAL** (≥90%), **HIGH** (≥60%), **MODERATE**, **EMPTY**.
- **Data Availability**: Injects notes for the LLM regarding what is (and isn't) available (e.g., street names vs. node IDs).

### 2. Panel of Experts (`expert_panel.py`)
Streams actionable intelligence via **Gemini 2.5 Flash** (fallback to Groq):
- **Logistics Chief**: Analyzes shelter capacity/inflow and proposes resource transfer plans.
- **Tactical Commander**: Inspects evacuation routes and **Pressure Junctures** to issue NDRF/Traffic deployment instructions.
- **Civic Authority**: Generates situation reports and drafts official public warnings.

### 3. Evacuation Chat (`evacuation_chat.py`)
Free-form natural language Q&A grounded in simulation data:
- **Grounded Answers**: Uses the enriched context (routes, pressure points, shelters) to prevent hallucinations.
- **Streaming SSE**: Real-time response generation via Gemini 2.5 Flash.

### 4. MCP Evacuation Server (`mcp_evacuation_server.py`)
Exposes the GenAI module as **MCP tools and resources** for agentic AI access:

**Tools:**
| Tool | Description |
|---|---|
| `get_simulation_state` | Returns current summary, success rate, and weighted success. |
| `get_shelter_status` | Detailed shelter occupancy with severity classification. |
| `get_route_summary` | Statistics + specific details for top evacuation routes. |
| `get_pressure_junctures` | Lists detected bottlenecks (converging paths & flood risk). |
| `get_realtime_weather` | Fetches live rainfall/temp data for the region (Open-Meteo). |
| `generate_evacuation_strategy`| LLM-generated tactical plan based on digital twin state. |
| `ask_evacuation_question` | Free-form Q&A about evacuation data. |

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

1. **Environment Variables**: Make sure your `.env` file contains:
   ```env
   GEMINI_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key
   ```
2. **MCP Requirements**: `pip install mcp` and `google-generativeai` for the SDKs.


---

## GenAI Integration — App Copilot & Expert Agent

The system features a dual-agent GenAI architecture designed to simplify complex workflows and provide deep analytical insights into evacuation outcomes.

### 1. App Copilot (Agentic Navigation & Control)

The **App Copilot** is an agentic LLM that lives in the main dashboard. It can "drive" the application by interpreting natural language commands and calling specific UI tools.

- **Capabilities**:
  - **Fuzzy Location Matching**: "Take me to Hebbel" automatically resolves to "Hebbal" and selects the region in the sidebar.
  - **Parameter Tuning**: "Set rainfall to 200mm and turn on live traffic" instantly updates the configuration state.
  - **Workflow Automation**: "Run a comparison for Marathahalli" will select the region, set the algorithm to 'All', and trigger the parallel simulation.
  - **Real-Time Weather**: "Set rainfall to match current weather" calls the weather tool and updates parameters instantly.
  - **Interactive Options**: When a command is ambiguous, the Copilot presents clickable "Option Chips" (e.g., *[☁️ Use real-time rainfall]* or *[📊 Start Compare Mode]*) to guide the user.

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

### Route Recommendations Changes
- Digital Twin Integration: The context_builder translates real-time coordinates, flood depths, and shelter capacities into a structured tactical summary.
- Routing Integration: Every specific route (top 25 paths) is now "visible" to the AI, including origin nodes, destination names, and population volumes.
- Strategy Generation: The system doesn't just show data; it performs mathematical preprocessing to identify Pressure Junctures (bottlenecks) and feeds these to the LLM for tactical planning.
- Expert Personas: You have specialized agents (Logistics Chief, Tactical Commander, Civic Authority) that utilize this data for structured, professional reporting.

### Running the MCP Server
To expose the Digital Twin to external agents:
1. Ensure the main FastAPI backend is running (`uvicorn main:app`).
2. Start the MCP server:
   ```bash
   cd backend/genai
   python mcp_evacuation_server.py
   ```
The server will communicate over `stdio` by default, making it easy to plug into Claude Desktop's configuration.