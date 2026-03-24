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
  - **🚛 Logistics Chief**: Manages shelter operations and supply chains. This persona monitors real-time shelter occupancy to flag **CRITICAL (>90%)** overcrowding, identifies specific resource deficits (Medical Kits, Food Packets) by comparing demand against the scraped IDRN inventory, and coordinates inter-hobli resource transfers.
  - **⚓ Tactical Commander**: Orchestrates field operations and route safety. This persona analyzes the "Pressure Junctures" (bottlenecks) identified by the Digital Twin, deploys NDRF/SDRF teams to high-risk flood zones, and issues dynamic rerouting orders to minimize congestion on major evacuation arteries.
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

---

## Data Pipeline & Persona Engineering

The system uses a robust offline-first data pipeline to ground the GenAI models in real-world government data. This ensures the "AI Personas" act based on official standards and actual inventory, not training data hallucinations.

### 1. Knowledge Base Extraction (Setup Phase)
Before the system runs, we extract static knowledge from official PDF guidelines. These scripts are located in `backend/data/`:
- **Taxonomy Extraction** (`extract_resource_categories.py`):
  - **Source**: `Data_collection_format_for_Districts.pdf`
  - **Action**: Parses the official item hierarchy (Activities -> Categories -> Items).
  - **Output**: `resource_definitions.json` (The "Dictionary" of what constitutes a resource).
- **Standards Extraction** (`extract_guidelines.py`):
  - **Source**: `Guidelines on Relief during disaster.pdf`
  - **Action**: Uses **Gemini 2.5 Flash** (with fallback to Regex) to parse quantitative relief standards (e.g., "3.50 sq.m per person", "15L water/day").
  - **Output**: `resource_guidelines.json`. This provides the math for the **Logistics Chief's** gap analysis (calculating deficits based on population).

### 2. Inventory Ingestion (Periodic Updates)
The system digitizes raw availability reports into a geospatial database:
- **Scraper Utility** (`scrape_resources.py`):
  - **Source**: `result.pdf` (IDRN District Resource Report).
  - **Action**:
    1.  **Extract**: Tabular data using `pdfplumber`.
    2.  **Geocode**: Maps station addresses to Lat/Lon using `geopy` (ArcGIS) with a local cache (`known_resource_locations.json`) to minimize API calls.
    3.  **Classify**: Tags items as **Logistics** vs **Tactical** using the `resource_definitions.json` map.
  - **Output**: `idrn_resources_scraped.csv` (The master inventory file).

### 3. Runtime Context Engine
When a simulation finishes, the data is woven into a prompt:
- **Context Builder** (`backend/genai/context_builder.py`):
  - Merges **Live Simulation Data** (Occupancy, Flood Depths) with **Static Inventory** (from CSV).
  - Filters resource lists (up to ~200 items) sorted by proximity to the disaster zone.
  - Classifies shelters as CRITICAL, HIGH, or MODERATE based on the simulation's computed occupancy percentages.
- **Expert Panel** (`backend/genai/expert_panel.py`):
  - **Gap Analysis**: Deterministically compares the *available* inventory (CSV) against the *required* standards (`resource_guidelines.json`).
  - **Proximity Logic**: Uses Haversine distance to recommend the "Nearest Equipped Fire Station" for missing items.
  - **Persona Generation**: Feeds this strictly structured context to Gemini 2.5 Flash to generate the final role-specific reports.

### 4. Expert Persona Logic
Each report is generated using a distinct prompt architecture designed to produce actionable, field-ready intelligence:

#### 🚛 Logistics Chief Report
**Objective**: Supply Chain Management & Gap Analysis
- **Status Logic**: The system calculates a "Pressure Index" for availability.
  - 🟢 **STABLE**: P1 items (Water, Medical, Boats) exist within 5km and cover >50% of demand.
  - 🟡 **STRAINED**: Items exist but are geographically dispersed (requires transport).
  - 🔴 **CRITICAL**: Absolute zero stock in the entire inventory.
- **Allocation Strategy**: The prompt forces a strict **One-Row-Per-Shelter** table to prevent double-counting.
- **Sourcing Protocol**: Resources are drawn in concentric rings:
  1.  **Immediate (<5km)**: Instant deployment (e.g., Local Fire Station).
  2.  **Extended (5–15km)**: Short-haul transport (e.g., District Hospital).
  3.  **Distant (>15km)**: Long-haul logistics (e.g., State Depot).
- **Output**: A precise list of **"What We Have"** vs. **"What We Need"**, including specific quantities (e.g., "Need 24 Oxygen Cylinders").

#### ⚔️ Tactical Commander Report
**Objective**: Field Operations & Rescue Coordination
- **Threat Zoning**: The model groups individual "Pressure Junctures" (flooded nodes) into named **Zones** (e.g., "Z-01: Northwest Approach Road").
- **Mission Planning**: Instead of a shopping list, it generates a **Mission Table** (`M-01`, `M-02`...) specifying:
  - **Where**: The exact location (human-readable address, avoiding raw Node IDs).
  - **What**: The specific tactical action (e.g., "Clear debris blockage", "Evacuate 40 stranded").
  - **Who**: The specific asset assigned (e.g., "NDRF Team A from Yelahanka").
- **Asset Inventory**: Focuses strictly on operational gear (Boats, Cutters, Life Jackets, NBC Equipment), ignoring logistics items like food.
- **Sector Command**: Clusters multiple shelters into geographic **Sectors** (Alpha, Bravo) to streamline command-and-control for large-scale evacuations.

## Autonomous Early Warning Pipeline (Sentinel)

The **Sentinel Pipeline** (`weather_watcher.py` & `AutomationPanel.jsx`) is a native, autonomous event-driven architecture that continuously monitors live atmospheric data and triggers programmatic simulation and response protocols natively without human intervention.

### Core Components

1. **`weather_watcher.py` (The Daemon)**
   An asynchronous background daemon running parallel to your FastAPI event loop. 
   - **Trigger Mechanism:** Natively pings the `mcp-weather-server` every 15 seconds to evaluate precipitation logic for an actively targeted Hobli constraint. 
   - **Registry Match:** Maps incoming targeted names (e.g. `Uttarahalli-1`) against the `HOBLI_COORDS` registry array.
   - **Simulation Hook:** Evaluates `precip >= threshold`. If the parameter threshold is breached, it immediately sets off an autonomous frontend socket ping.

2. **`AutomationPanel.jsx` (The UI Controller)**
   A secure, interfaceable control panel embedded directly into the React App (`App.jsx`).
   - **Target Parameters:** Allows the **Disaster Response Authority (DRA)** to select a specific Hobli and set a `Warning Threshold [mm/h]`.
   - **Arm/Disarm:** A single secure Power button sends an HTTP POST configuration to the daemon, arming the listener pipeline. 

### How to Use the Sentinel

1. Open the UI and click the **Sentinel (CloudRain Icon)** tab on the sidebar.
2. Under **Target Hobli Partition**, select your testing environment (e.g., `Uttarahalli-1`).
3. Set your **Warning Threshold** (e.g., `10.0` mm/h).
4. Click the circular **Power** button to **ARM** the Sentinel.
5. In the **Sentinel Subroutine Log**, you will securely see the system polling Open-Meteo's arrays every 15 seconds. Example: `Live scan - Uttarahalli-1: 0.0mm (Clear)`.

Once the live rainfall passes your set threshold (or if you artificially set the threshold to `0.0` for a demo):
- The log will flash a `🚨 THRESHOLD EVENT!`.
- The daemon will autonomously disarm itself (`active = False`) to prevent CPU-locking simulation spam.
- The UI will instantly force-trigger `sim.start()` to map out and render Evacuation Routes and algorithm paths natively on your digital twin dashboard.

---

## Public Transport Agent (Fleet Deployment)

The **Public Transport Agent** acts as an automated logistics coordinator, bridging the gap between computed evacuation routes and real-world transit availability. It lives in the **Resources** tab (formerly AI Agent).

### How it Works
1.  **Route Analysis**: It takes the raw AI-optimised (ACO/GA/PSO) evacuation paths generated by the Digital Twin.
2.  **GTFS Integration**: It queries the BMTC GTFS database (via `transport_agent.py`) to find the nearest physical bus stops to the flood zones.
3.  **Intelligent Mapping**:
    - **Physical Routes**: Prioritizes real-world BMTC route numbers (e.g., `500D`, `335E`) by correctly mapping GTFS `route_id` fields.
    - **Emergency Shuttles**: If no commercial route exists for a specific stop, it designates a dynamic "Emergency Shuttle".
    - **Fleet Sorting**: Automatically sorts the manifest to show actual public transit routes at the top of the list for better logistical visibility.
4.  **Sequential Deployment**: Generates clean, sequential Fleet IDs (`BUS-001`, `BUS-002`...) after sorting, ensuring the manifest remains organized.
5.  **Performance (TTL Caching)**: Implements a high-speed, in-memory cache for GTFS data with a **10-minute TTL** and **file-mtime awareness**. This ensures sub-millisecond route matching while automatically detecting if the underlying GTFS files are updated on disk.

### How to Use
1.  Run a flood simulation on the main dashboard to generate evacuation paths.
2.  Switch to the **Resources** tab in the sidebar.
3.  Click the **Generate Fleet Manifest** button in the Public Transport Agent panel.
4.  An interactive manifest will render, showing deployed buses, passenger loads, and drop-off points. Clicking any row will **draw the bus's designated path** dynamically on the 3D map!

---

## Unified App Copilot (Omni-Modal AI)

The **App Copilot** is the central, unified intelligence interface for the entire Urban Flood Digital Twin. It possesses a full "App-Level Tools" payload, enabling it to act as both a **UI Navigator** and a **Disaster Data Analyst** simultaneously.

### How it Works
The Copilot is hooked into a deep integration loop (`app_copilot.py`). When you send a message, the LLM evaluates whether you want to click a button on the UI (Frontend Navigation) or request complex tactical intelligence from the backend databases (Backend Tools). It silently executes the targeted tool and returns natural, conversational insights in the unified interface.

### Useful Copilot Prompts

You can use the Copilot to control the app or analyze the disaster state. Here are some powerful prompts to try:

**Frontend Control & Simulation:**
- *"Take me to Hebbal and run the Genetic Algorithm with 180mm of rainfall."*
- *"Enable live traffic and start the ACO simulation."*
- *"Compare all algorithms for Yelahanka."*
- *"Switch to the Evacuation tab."*

**Tactical Analysis & Data Retrieval:**
- *"What is the capacity of the State Disaster Response Force shelter?"*
- *"List the top 3 most congested evacuation routes right now."*
- *"Generate an official public warning for the current situation."*
- *"Are there any critical pressure junctures causing bottlenecks?"*
- *"Which transit networks will be disabled by the 2-meter flood in Indiranagar?"*
- *"Identify the primary evacuation hubs for the Koramangala flood zone."*
- *"What is the safest route to the nearest shelter?"*
- *"Which junctions are experiencing the worst bottlenecks?"*
- *"How many evacuees are assigned to each shelter?"*
- *"Are there any shelters exceeding their capacity?"*
- *"Which optimization algorithm performed the best for this simulation?"*

**📌 Pinned Location Analysis (Map Integration):**
*The Copilot is spatially aware. Simply **click anywhere on the map** to drop a red "PINNED LOCATION", and the Copilot will automatically inherit those coordinates!*
- *"We need buses for immediate evacuation right here. What's available?"*
- *"Check for available transit networks at the pinned location."*
- *"Are there any bus stops near the selected location on the map?"*

