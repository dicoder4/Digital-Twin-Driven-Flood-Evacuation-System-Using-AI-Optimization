# GenAI Expansion: Multi-Server Intelligence Architecture

This document provides a structured explanation of the recent architectural changes within the `genai` folder, transforming it from a simulation-context provider into a multi-server Agentic Hub.

---

## 1. Architectural Evolution: Simple Context → Multi-Server MCP Hub

Originally, the GenAI module functioned as a standard RAG (Retrieval-Augmented Generation) pipeline. The current architecture has pivoted to a **Model Context Protocol (MCP)** ecosystem, where the Digital Twin state is exposed through specialized functional servers.

### Current GenAI Server Stack:
*   **`mcp_evacuation_server.py`**: The "Operational Core." Handles basic simulation data, shelter occupancy, and path summaries.
*   **`mcp_flood_intelligence_server.py`**: The "Strategic Brain." Added to provide deep reasoning over infrastructure health, multi-modal transport disruptions, and resource mapping.
*   **`gis_mcp_server.py`**: The "Spatial Analyst." Provides terrain-aware reasoning and elevation-based risk reporting.
*   **`transport_gtfs_mcp_server.py`**: The "Logistics Coordinator." Integrates real-world bus (GTFS) and metro/rail geometry for evacuation manifests.

---

## 2. Deep Dive: Flood Intelligence Server (New)

The `mcp_flood_intelligence_server.py` is the most significant recent addition, introducing tools that perform complex data aggregation before feeding context to the LLM:

### A. Metro Line Aggregated Health (`get_metro_status`)
- **Old way**: Agent saw raw flooded station nodes.
- **New way**: The server aggregates status (Safe/Caution/Unsafe) by line. It calculates a **Disruption Percentage** and assigns a color-coded health status (🔴 CRITICAL, 🟡 DEGRADED, 🟢 OPERATIONAL).
- **Benefit**: AI can now give advice like *"Avoid the Purple Line entirely; it is 60% disrupted,"* rather than listing individual stations.

### B. "Super-Hub" Resource Mapping (`get_shelter_resource_map`)
- **Innovation**: Instead of just listing shelters, this tool performs a distance-aware join between **Safe Shelters** and the **IDRN Resource Inventory**.
- **The "Super-Hub" Concept**: Shelters that have both **High Occupancy** and **Available Boats/Medical Gear** are tagged as Super-Hubs.
- **Benefit**: AI prioritizes deployment to these hubs where resources are needed most and easiest to distribute.

### C. Vulnerability Hotspots (`get_vulnerability_hotspots`)
- **Logic**: Identifies clusters where: `Flood Depth > 0.15m` AND `Pop. Density is high` AND `Distance to safe shelter > 1km`.
- **Actionable Output**: Recommends specific rescue assets (Boats vs. HCV vs. Foot rescue) based on the computed water depth.

---

## 3. Unified App Copilot & Expert Panel

The interaction layer has been unified across the `app_copilot.py` and `expert_panel.py`:

*   **Unified Tools (Function Calling)**: The Copilot can now toggle between UI commands (zoom, algorithm selection) and intelligence commands (fetching bottlenecks) in a single turn.
*   **Spatial Awareness**: The Copilot now inherits the "Pinned Location" from the map. If a user clicks a road and asks, *"Is this safe?"*, the Copilot automatically fetches coordinates and queries the simulation state for that specific point.
*   **Expert Personas**:
    *   **Logistics Chief**: Grounded in official PDF relief guidelines.
    *   **Tactical Commander**: Focused on "Pressure Junctures" and mission planning.
    *   **Civic Authority**: Focused on public warnings and official situation reports.

---

## 4. Multi-Model Reliability (Reliability Layer)

A three-tier fallback system was implemented to ensure the evacuation system works even during internet outages or quota limits:

1.  **Gemini 2.5 Flash (Cloud)**: Primary engine for complex reasoning and tool use.
2.  **Groq / Llama 3.3 70B (Cloud Fallback)**: Automatically triggered on `429` errors for near-instant latency.
3.  **Ollama / Llama 3.2 (Local Fallback)**: On-device model that triggers if cloud connectivity is lost, ensuring basic chat and guidance remain offline.

---

## 5. Metadata & State Sync

All servers communicate via a shared **`mcp_state.json`**. This allows the FastAPI simulation process (which is short-lived) to securely pass information to the long-lived MCP Servers without managing complex inter-process memory maps.
