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
* Contributions welcome via pull requests!!

---
