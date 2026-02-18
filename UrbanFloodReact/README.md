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
- **MapLibre Visualization**: Uses WebGL for smooth rendering of flood layers.
- **Animated Spread**: The flood propagation is animated step-by-step.
- **Controls**: Adjust rainfall, duration, and flow decay in real-time.

## How it works
- **Initialization**: Water is "injected" at identified drain locations (simulating overflow) and lake boundaries based on the rainfall amount.
- **Propagation**: In each time step, every node with water checks its connected neighbors. If a neighbor is at a lower elevation, a portion of the water (determined by the decay factor and slope steepness) flows down to that neighbor.
- **Accumulation**: If a node has no lower neighbors (a "sink"), water accumulates there.
- **Heatmap**: We visualize this depth as a color gradient (Green→Yellow→Red) growing outwards from the sources over time.
