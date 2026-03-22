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

# Branch: `genai-agents` — AI Decision Support System

This branch introduces an **AI-driven Panel of Experts** providing real-time strategic advice during flood simulations. Three specialised AI personas generate actionable field reports from verified government inventory data.

---

## 🤖 Personas

| Persona | Badge | Focus | Data Source |
| :--- | :---: | :--- | :--- |
| 🚚 Logistics Chief | `SUPPLY` | Shelter-by-shelter resource allocation, gap analysis, procurement | `logistics_resources.csv` only |
| ⚔️ Tactical Commander | `OPS` | Rescue zone assessment, mission orders, sector command | `tactical_resources.csv` only |
| 📢 Civic Authority | `COMMS` | Public SMS warnings, official situation reports | Simulation stats only |

**Key technical features:**
- **Persona-filtered inventory** — Each report only sees its own CSV. Logistics never sees SAR tools; Tactical never sees paramedics.
- **Definition-category enrichment** — Every item's IDRN code is looked up in `resource_definitions.json` to attach its official category/subcategory (e.g. Water Tank → `Health Services / Hygiene`).
- **Proximity-chained sourcing** — Allocations follow: IMMEDIATE (<5km) → EXTENDED (5–15km) → DISTANT (>15km) → Section 4b (not in inventory). Distant sources are flagged `⚠️ DISTANT` with convoy ETA.
- **Source/destination separation** — Fire station addresses and shelter names are injected as two separate labelled sections so the LLM never confuses supply origins with delivery destinations.
- **Streamed responses** — SSE token streaming. Primary: Gemini 2.5 Flash. Fallback: Groq llama-3.1-8b-instant.

---

## 📋 Report Sections

### Logistics (`📦 LOGISTICS REPORT`)
1. Situation Summary
2. Full Inventory Snapshot — all items by definition category, with closest source zone (📍/🚛/✈️) and shortfall
3. Shelter Allocation Plan — one row per shelter; per-item-group sources and ETAs
4a. Items Allocated but Now Depleted
4b. Items Never in Inventory — external procurement required
5. Mobilization Notes — staging, transport, distant convoy plan
📋 Field Reference Card (Karnataka relief standards — appended verbatim)

**Status levels:** `🟢 STABLE` P1 items cover ≥50% of shelters · `🟡 STRAINED` P1 items exist but insufficient · `🔴 CRITICAL` P1 items completely absent

### Tactical (`⚔️ TACTICAL OPS PLAN`)
- "How to Read" glossary explaining Zones, Missions, and Sectors in plain English
- Threat Matrix — human-readable location names only, no raw database node IDs
- Asset Inventory grouped by definition category with totals and ETAs
- Mission Orders — one row per mission with measurable objective, assigned assets, and ETA
- Sector Command — 3–4 geographic clusters, max 3 shelters listed per cell
- Unmet Needs — de-duplicated; only zero-stock items across all proximity zones

### Civic (`📢 CIVIC SITUATION REPORT`)
Official summary and SMS broadcast template using exact simulation figures.

---

## 🏗️ Data Pipeline

The entire knowledge base is built from raw government PDFs through a three-stage ETL pipeline.

### A. Resource Scraping — `backend/data/scrape_resources.py`

**Source:** `result.pdf` — the IDRN (India Disaster Resource Network) Disaster Resource Inventory for Bengaluru.

**Process:**
1. `pdfplumber` extracts equipment tables from the PDF (department name, item name, quantity, contact, phone)
2. `geopy.ArcGIS` geocodes each textual address (e.g. "Rajajinagara Fire Station, 1st Main Road") into precise latitude/longitude coordinates
3. Items are split into two CSVs based on operational role — logistics items (water, medical, transport, shelter) go to `logistics_resources.csv`; rescue and SAR items go to `tactical_resources.csv`

**Output stats:**
- 652 total items across Bengaluru's fire stations, hospitals, SDRF, and industrial depots
- 158 logistics items · 494 tactical items
- 25 unique source locations, all geocoded
- Coverage radius used at runtime: 50km search, returned sorted by distance

**Why split into two CSVs?** The Logistics Chief and Tactical Commander operate in completely different domains. Sending the Logistics AI the full 652-item list caused it to allocate crow bars and diving suits to shelters. Sending the Tactical AI medical personnel and water tanks caused it to deploy doctors to flood rescue zones. The split ensures each persona only reasons about items it can actually use.

---

### B. Category Taxonomy — `backend/data/extract_resource_categories.py`

**Source:** `Data_collection_format_for_Districts.pdf` — the official government data collection template defining all valid disaster resource types.

**Process:** Regex-based parsing extracts a hierarchical taxonomy: each item is assigned a numeric code, a broad category, and a subcategory.

**Output: `resource_definitions.json`**

```
Search And Rescue  →  Cutters, Light Equipment, Lifting Equipment, Lighting, Heavy Engineering
Flood Rescue       →  Rescue Boats, Specialized Flood/Rescue Equipment
Health Services    →  Health Equipment, Portable Equipment, Lifesaving, Mobile Units, Hygiene
Shelters           →  Tents, Sheets, Fab Shelters, Rehabilitation Centers
Transportation     →  Light Vehicles, Medium Vehicle, Heavy Vehicle, Special Vehicles
Tele Communication →  Wireless System, Sat Phones, Mobile Phones, GPS, Video System
Nuclear Biological And Chemical  →  NBC Specialized Equipment, Portable Equipment
```

**How it's used at runtime:** Every row in both CSVs carries an `Item Code`. When resources are loaded for a disaster zone, each item's code is looked up against this taxonomy to attach its `def_cat` (e.g. `Health Services`) and `def_subcat` (e.g. `Hygiene`). The LLM prompt then groups items by these official categories rather than inventing its own groupings. Code match rate: **99.8%** (only Rope Ladder, code 328, has no definition entry).

---

### C. Relief Standards — `backend/data/extract_guidelines.py`

**Source:** Government of Karnataka Relief Manual (PDF).

**Process:** Gemini 2.5 Flash reads the PDF and extracts allocation rules, thresholds, and operational standards into structured JSON.

**Output: `resource_guidelines.json`**

This file serves two completely separate purposes in the system:

| Use | Function | What it contains | How AI uses it |
| :--- | :--- | :--- | :--- |
| Calculation input | `get_resource_guidelines()` | Numbers only: 3L drinking water/person/day, 20L hygiene/person/day, 3.5m²/person shelter, 1 toilet per 30 people | AI validates quantities — e.g. flags that 168 people need 504L/day of drinking water |
| Field reference card | `format_guidelines_reference_card()` | Full standards: water, food nutrition (pulse/cereals/egg/fat sources), shelter infrastructure requirements, sanitation distance rules, medical deployment, rescue priority order (children → women → elderly → differently-abled), camp security | Appended **verbatim** to the end of every report. AI is explicitly instructed not to use this section for calculations — it is purely for field officers to consult |

Keeping these two uses separate is important: if the AI tried to "apply" the full guidelines as calculation rules, it would over-constrain its allocations on items like food (not in the IDRN database) and shelter area (already governed by the shelter occupancy data from the simulation).

---

## 💻 Frontend — `PanelOfExperts.jsx`

- **Per-persona theming** — distinct colours for tables, headings, and modals (blue/amber/green)
- **Inline preview + expand modal** — compact view with full-screen modal option
- **Download buttons** — fully client-side, no backend route needed
  - **Word:** markdown → styled HTML → `.doc` blob (opens in Word/LibreOffice/Google Docs)
  - **PDF:** HTML rendered in new tab → browser `window.print()` → Save as PDF
- **Local Inventory Browser** — filterable modal by resource type and distance zone

---

## 📂 File Structure

```
backend/
├── genai/
│   ├── expert_panel.py          # Personas, resource loader, prompt builder, SSE streamer
│   └── context_builder.py       # Simulation data → LLM context
├── data/
│   ├── logistics_resources.csv  # 158 logistics items with coordinates
│   ├── tactical_resources.csv   # 494 tactical items with coordinates
│   ├── resource_definitions.json
│   └── resource_guidelines.json
└── main.py                      # /expert-advice-stream · /resources/{location}

frontend/src/components/
└── PanelOfExperts.jsx
```

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
