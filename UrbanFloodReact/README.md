# Urban Flood Model Use Guide

This project uses a decoupled architecture for high performance:
- **Backend**: FastAPI (Python) for physics simulation.
- **Frontend**: React + MapLibre for high-performance visualization.

## Setup Instructions

### 1. Backend Setup
Navigate to the `backend` folder and install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

Run the backend server:
```bash
uvicorn main:app --reload
```
The API will be available at `http://localhost:8000`.

### 2. Frontend Setup
Open a new terminal, navigate to the `frontend` folder, and install dependencies:
```bash
cd frontend
npm install
```

Run the development server:
```bash
npm run dev
```
Open the link (usually `http://localhost:5173`) in your browser.

## Features
- **Multi-Hobli Support**: Hierarchical region selection (District → Taluk → Hobli) for Bengaluru Urban and Rural.
- **Lazy Loading**: Automatic downloading and disk-caching of road networks (OSMnx) for the selected region.
- **Historical Rainfall Data**: Simulation based on real meteorological data from May, June, and July datasets.
- **Road Risk Assessment**: Real-time coloring of road segments based on calculated flood depth (Green: Passable, Yellow: Caution, Red: Dangerous).
- **MapLibre Visualization**: Uses a light CartoDB Positron basemap for a clean, Google Maps-like aesthetic.
- **SSE Real-time Updates**: Server-Sent Events (SSE) provide a smooth, step-by-step animation of flood propagation.

## How it works
- **Region Initialization**: Selecting a Hobli triggers the backend to load its road network. If not cached, it downloads data from OpenStreetMap.
- **Rainfall Input**: 
  - **Manual**: Adjust rainfall (mm) using a slider.
  - **Historical**: Select a specific date from history to auto-populate rainfall levels and see calculated "Risk Departure" badges.
- **Physics Propagation**: 
  - Water is "injected" at drains and lake boundaries.
  - In each time step, water flows to neighbors with lower elevation, adjusted by the **Flow Decay** factor.
- **Visualization**: 
  - **Flood Area**: A gradient poly-layer showing general flood extent.
  - **Road Overlay**: Specific road segments are highlighted and colored based on depth thresholds (e.g., >15cm is High risk).
- **Legend**: A dynamic legend in the bottom-right corner provides context for the color mappings.

## Flooding
- **Initialization**: Water is "injected" at identified drain locations (simulating overflow) and lake boundaries based on the rainfall amount.
- **Propagation**: In each time step, every node with water checks its connected neighbors. If a neighbor is at a lower elevation, a portion of the water (determined by the decay factor and slope steepness) flows down to that neighbor.
- **Accumulation**: If a node has no lower neighbors (a "sink"), water accumulates there.
- **Heatmap**: We visualize this depth as a color gradient (Green→Yellow→Red) growing outwards from the sources over time.
