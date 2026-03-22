# Digital Twin Driven Flood Evacuation System

A real-time flood evacuation planning system that combines digital twin technology with Google Maps traffic data to optimize emergency response.

## About

This project implements a sophisticated flood evacuation system that:
- Simulates flood scenarios using dynamic elevation models
- Provides multiple evacuation routing algorithms
- Supports both emergency responders and citizens
- Visualizes flood impact and evacuation routes
- Includes role-based access control
- Google Maps API integration for efficient safe center finding

## Features

- 🌊 Real-time flood simulation
- 🚗 Live traffic integration with Google Maps
- 🗺️ Interactive mapping with Folium
- 🚦 Multiple evacuation algorithms:
  - Dijkstra's Algorithm
  - A* Search
  - Quanta Adaptive Routing
  - Bidirectional Search
- 👥 Role-based user interfaces:
  - Emergency Responder Dashboard
  - Citizen Interface
- 📊 Risk assessment and recommendations
- 🏥 Safe center identification and capacity management
- 🆘 SOS alerting and Evacuation Plan Notifications

---

# Branch: `genai-agents` - Enhanced Decision Support System

This branch introduces an **AI-driven "Panel of Experts"** to provide real-time, context-aware strategic advice during flood simulations. By integrating Google Gemini 2.5 Flash and specialized data-scraping pipelines, the system now offers actionable reports from three distinct personas.

## 🤖 New AI Modules & Workflow

### 1. Panel of Experts (Backend: `genai/expert_panel.py`)
Orchestrates three AI personas, each with a unique system prompt and responsibility:
*   **🚚 Logistics Chief**: Manages supply chains, allocates verified IDRN resources (Food, Medical, Transport), and identifies shortages.
*   **⚔️ Tactical Commander**: Directs SAR (Search & Rescue) assets like boats/helicopters based on flood depth and infrastructure damage.
*   **📢 Civic Authority**: Drafts public warnings (SMS templates) and official government situation reports.

**Key Technical Features:**
*   **Streamed Responses**: Uses Server-Sent Events (SSE) to stream AI advice token-by-token to the frontend.
*   **Enriched Context**: Feeds the AI with real-time simulation stats (people at risk, safe routes) + verified local resources.
*   **Strict Hallucination Control**: The AI is restricted to *only* suggest resources that exist in our scraped database.

### 2. Context Builder (`genai/context_builder.py`)
Acts as the middleware between the raw simulation engine (`service.py`) and the AI.
*   **Proximity Filtering**: Automatically filters the 15,000+ item database to find resources within 5km/15km of the affected Hobli.
*   **Aggregated Stats**: Converts complex graph data into human-readable summaries (e.g., "300 people stranded in Zone A") for the LLM.

---

## 🏗️ Data Pipeline: From PDF to Structured Knowledge

We created a custom ETL (Extract, Transform, Load) pipeline to digitize unstructured government data into queryable formats.

### A. Resource Scraping (`backend/data/scrape_resources.py`)
*   **Source**: `result.pdf` (IDRN Disaster Resource Inventory).
*   **Method**: Uses `pdfplumber` to extract tables of available equipment (Boats, JCBs, Generators).
*   **Geocoding**: Integrates `geopy.ArcGIS` to convert textual addresses (e.g., "Fire Station, Rajajinagara") into precise Latitude/Longitude coordinates.
*   **Output**: 
    *   `idrn_resources_scraped.csv`: Raw master list.
    *   `logistics_resources.csv` & `tactical_resources.csv`: Split datasets for specific agents.

### B. Category Extraction (`backend/data/extract_resource_categories.py`)
*   **Source**: `Data_collection_format_for_Districts.pdf`.
*   **Method**: Regex-based parsing to build a taxonomy of valid resources.
*   **Output**: `resource_definitions.json` — A hierarchical dictionary mapping items (e.g., "Life Jacket") to categories (e.g., "Search & Rescue").

### C. Guideline Extraction (`backend/data/extract_guidelines.py`)
*   **Source**: Government Relief Manuals (PDF).
*   **Method**: Uses **Gemini 2.5 Flash** to read the PDF and extract key allocation rules (e.g., "3.5 sq.m space per person", "3L water/day").
*   **Output**: `resource_guidelines.json` — Used by the AI to validate if the current shelter capacity meets official standards.

---

## 💻 Frontend Enhancements (`UrbanFloodReact/frontend`)

### 1. Panel of Experts UI (`components/PanelOfExperts.jsx`)
*   **Interactive Tabs**: Switch between Logistics, Tactical, and Civic views.
*   **Live Markdown Rendering**: Displays the AI's formatted tables and checklists beautifully.
*   **Expandable Reports**: Modal view for reading detailed strategic plans.

### 2. Live Inventory Browser
*   **New Modal**: Users can now browse the *actual* database of resources for the active location.
*   **Filters**: 
    *   **Type**: Logistics vs Tactical.
    *   **Distance**: Immediate (<5km), Extended (5-15km), Distant (>15km).

---

## 📂 File Structure Changes

| Path | Description |
| :--- | :--- |
| **`backend/genai/`** | **New Folder**: Contains all logic for the AI Agents. |
| `├── expert_panel.py` | Main service for generating advice. |
| `├── context_builder.py` | Prepares simulation data for the LLM. |
| **`backend/data/`** | **Enhanced**: Now includes scraping scripts and output JSONs. |
| `├── scrape_resources.py` | ETL script for IDRN PDF -> CSV. |
| `├── resource_definitions.json` | JSON taxonomy of relief items. |
| `├── logistics_resources.csv` | Processed inventory for Logistics Chief. |
| `├── tactical_resources.csv` | Processed inventory for Tactical Commander. |
| **`backend/main.py`** | Added endpoints `/expert-advice-stream` and `/resources/{location}`. |


## Project Structure

```
MiniProject2026/
├── app.py                    # Main Streamlit application
├── auth_components.py        # Authentication and user management
├── citizen_interface.py      # Citizen-facing interface
├── evacuation_algorithms.py  # Evacuation routing algorithms
├── evacuation_runner.py      # Evacuation simulation executor
├── flood_simulator.py        # Flood simulation engine
├── network_utils.py          # Network analysis utilities
├── osm_features.py          # OpenStreetMap integration
├── risk_assessment.py        # Risk analysis and recommendations
├── traffic_utils.py         # Google Maps traffic integration
└── visualization_utils.py    # Visualization components
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/dicoder4/MiniProject2026.git
cd MiniProject2026
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables:
- Create a `.env` file in the project root
- Add your Google Maps API key:
```
GOOGLE_MAPS_API_KEY=your_api_key_here
```
- Add your MONGO_URL
- Add other credentials, tokens that are required for email and SMS notifications 

## Usage

1. Start the Streamlit application:
```bash
streamlit run app.py
```

2. Access the system:
- Emergency Responder Interface: http://localhost:8501
- Default credentials:
  - Admin: admin/admin123
  - Responder: responder/resp123

## Development Setup

### Prerequisites
- Python 3.8 or higher
- GDAL library
- Active internet connection
- Google Maps API key

### Testing
Run the test suite:
```bash
python -m pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- OpenStreetMap for geographical data
- Google Maps for traffic integration
- Streamlit for the web interface
- Folium for map visualization

## Developers

* Aditri B Ray
* Anisha Ajit 
* Diya D Shah
* Contributions welcome via pull requests!

---
