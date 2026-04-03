# 🚇 Bengaluru Metro Network & Stations Dataset

This dataset provides a structured representation of the Bengaluru (Namma Metro) system, including station metadata and full network connectivity.

It is designed to support developers, researchers, and students working on transportation systems, smart city solutions, and data-driven metro applications.

---

## 📂 Dataset Contents

### 1. bengaluru_metro_stations.csv

Contains basic information about metro stations.

Columns:

* station_name: Name of the metro station
* station_code: Unique short code for each station
* line: Metro line (Purple Line, Green Line, Yellow Line)

---

### 2. bengaluru_metro_network.csv

Represents the metro network as a graph with connectivity and geographic information.

Columns:

* station_code: Unique station identifier
* station_name: Name of the station
* line: Metro line name
* sequence: Order of station within the line
* is_interchange: Indicates if station is an interchange (1 = Yes, 0 = No)
* next_station_code: Code of next station in route (NULL if terminal station)
* latitude: Geographic latitude
* longitude: Geographic longitude
* distance_to_next_km: Distance to next station in kilometers
* line_color: Hex color representing the metro line

---

## 🌐 Key Features

* Complete metro network structure (graph-based representation)
* Geographic coordinates for mapping and visualization
* Distance between consecutive stations using Haversine formula
* Interchange station modeling
* Multi-line support (Purple, Green, Yellow lines)

---

## 💡 Use Cases

This dataset can be used for:

* Metro network visualization (Leaflet, Mapbox, GIS tools)
* Route optimization (Shortest path algorithms like Dijkstra)
* Transportation analytics and simulations
* Smart city and urban mobility research
* Integration with ridership datasets for demand prediction
* Building metro ticketing or navigation systems

---

## 🔗 Integration

This dataset can be combined with metro ridership datasets available on Kaggle to perform:

* Passenger demand prediction
* Peak hour analysis
* Congestion modeling

---

## ⚠️ Notes

* Terminal stations have `next_station_code = NULL`
* Distances are calculated between consecutive stations
* Coordinates are manually curated and verified for accuracy

---

## 📜 License

You can use this dataset for educational, research, and development purposes.

---

## 🙌 Contribution

This dataset was created to address the lack of structured metro datasets available publicly and to help the developer and research community build real-world transportation solutions.

If you use this dataset, consider giving credit or sharing your work.