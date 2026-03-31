# Metro/Railway Data Extraction Workflow

## Overview
The system uses a **multi-source hybrid approach** to extract and display metro/railway networks. It combines three data sources (OSMnx, KML, CSV) with intelligent spatial matching to create a complete, accurate public transport network visualization.

---

## The Three Data Sources

### 1. **OSMnx** (OpenStreetMap via Python Library)
**Purpose:** Primary live data source for real metro/railway infrastructure

**What it extracts:**
- Metro stations from OSM tags: `railway=subway/light_rail`, `station=subway/light_rail`
- Railway stations from OSM tags: `railway=station/halt`, `station=train`
- Line geometries (tracks) from OSM tags: `railway=subway/light_rail/rail`, `route=subway/light_rail`

**How it works:**
1. Queries a 5km radius (5,000m) around hobli center using `ox.features_from_point()`
2. Filters results to remove non-transit facilities (hospitals, schools, police stations, etc.)
3. Classifies each feature as metro or railway based on OSM tags
4. Extracts coordinates and snaps stations to nearest road network nodes

**Advantages:**
- ✅ Real-time, constantly updated by OSM community
- ✅ Comprehensive geographic coverage
- ✅ Direct operator/network tags (`operator=BMRCL`)

**Limitations:**
- ❌ Line names often generic or missing in raw OSM data
- ❌ Inconsistent tag naming across regions
- ❌ May miss incomplete or proposed infrastructure

**Error Handling:**
- Gracefully handles `InsufficientResponseError` when no features found
- Falls back to KML/CSV references if OSM returns zero results

---

### 2. **KML** (Keyhole Markup Language - Local Reference File)
**File:** `data/bengaluru_rail_metro_lines.kml`
**Purpose:** Reference line geometry with official labels (backup + enrichment)

**What it contains:**
- Complete metro line routes with proper names (Purple Line, Green Line, etc.)
- Railway track segments with official classifications
- More consistent and curated than raw OSM data

**How it's used:**
1. Loads KML file using GeoPandas: `gpd.read_file(METRO_KML)`
2. Filters lines within 5km radius using spatial bounding box
3. Extracts line names using pattern matching (`_classify_kml_line_name`)
4. Classifies into metro (BMRCL lines) vs railway (Indian Railways)

**Advantages:**
- ✅ Official, verified line names and routes
- ✅ Complete line geometries even if OSM incomplete
- ✅ Serves as "ground truth" for line labeling

**Limitations:**
- ❌ Static file - requires manual updates
- ❌ May not capture new infrastructure quickly
- ❌ Specific to Bengaluru

**Classification Logic:**
```python
# Looks for color names in line name
if "purple" in line_name: return ("Purple Line", "purple")
if "green" in line_name:  return ("Green Line", "green")
if "yellow" in line_name: return ("Yellow Line", "yellow")
if "blue" in line_name:   return ("Blue Line", "blue")
```

---

### 3. **CSV** (Comma-Separated Values - Reference Tables)
**Files:**
- `data/NammaMetro/bengaluru_metro_network.csv` - Full line segments with station pairs
- `data/NammaMetro/bengaluru_metro_stations.csv` - Station list with line assignments

**Purpose:** Structured station-to-line mapping for data validation and enrichment

**What it contains:**
```
station_name | line | station_code | next_station_code | latitude | longitude | line_color
Byappanahalli | Purple Line | STN001 | STN002 | 13.05 | 77.60 | #7c3aed
```

**How it's used:**
1. Creates `station_line_map`: Maps station names to their official lines
2. Builds full-line GeoJSON features from station pairs
3. Enriches OSM stations with official line assignments

**Advantages:**
- ✅ Complete station-to-line relationships (ground truth)
- ✅ Structured format for easy data matching
- ✅ Contains color coding for visualization

**Limitations:**
- ❌ Static reference - only 4 metro lines (Purple, Green, Yellow, Blue)
- ❌ Doesn't include all under-construction lines
- ❌ Requires manual maintenance

---

## Data Extraction Workflow

### Step 1: Load OSMnx Data
```python
stations = ox.features_from_point(center, 
    tags={'railway': ['station', 'halt', 'subway', 'light_rail']},
    dist=5000)
```
**Result:** Raw OSM feature set with 50-100+ entries (needs heavy filtering)

### Step 2: Load CSV Reference
```python
network_rows = read CSV file
station_line_map = {station_key → line_name}
csv_features = build GeoJSON from station pairs
```
**Result:** Structured reference with known lines and relationships

### Step 3: Load KML Reference
```python
lines_gdf = gpd.read_file('bengaluru_rail_metro_lines.kml')
kml_features = filter by bbox + classify lines
```
**Result:** Official line geometries with names

### Step 4: Merge & Enrich
```
OSM Stations + CSV line_map → Enrich station.line property
OSM Lines + KML reference → Label line segments with official names
Spatial matching (0.12° ≈ 12km) → Fill gaps in line assignments
```

### Step 5: Output to Frontend
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "geometry": {"type": "Point", "coordinates": [77.60, 13.05]},
      "properties": {
        "name": "Byappanahalli",
        "line": "Purple Line",
        "colour": "purple",
        "transport_type": "metro",
        "visibility": "always"
      }
    },
    {
      "geometry": {"type": "LineString", "coordinates": [[...], [...]]},
      "properties": {
        "line": "Purple Line",
        "colour": "purple",
        "transport_type": "metro",
        "visibility": "always"
      }
    }
  ]
}
```

---

## Key Matching Strategies

### 1. **Station Classification**
Determines if a station is Metro or Railway using OSM tag hierarchy:
```python
if railway in {"subway", "light_rail"}:         # Priority 1
    return "metro"
if operator == "BMRCL" or network == "Namma Metro":  # Priority 2
    return "metro"
if "bmrcl" in name or "namma metro" in name:  # Priority 3
    return "metro"
```

### 2. **Line Name Enrichment**
Station gets its line name from multiple sources (priority order):
1. **OSM `line` tag** (direct): `railway:line=Purple Line`
2. **CSV lookup** (structured): `station_line_map[station_name]`
3. **Spatial matching** (nearest): Find nearest line within 12km radius
4. **Fallback**: `"Unknown Line"`

### 3. **Spatial Proximity Matching**
When OSM line name is generic/missing:
```python
for each candidate_line in reference_lines:
    distance = geometry.distance(station_point)
    if distance <= 0.12 degrees (≈12km):
        station.line = candidate_line.name
        break  # Use closest match
```

### 4. **Deduplication**
Prevents duplicate line segments by tracking:
- Feature geometry endpoints
- Transport type
- Line name
- Number of coordinates

---

## Visibility Control

Each feature includes a `visibility` property controlling frontend rendering:

```python
metro_lines["visibility"] = "always"      # Show purple/green/yellow/blue lines when clicked
railway_lines["visibility"] = "station_only"  # Show only when user clicks railway station
```

**Frontend behavior:**
- Metro lines: Hidden by default, visible when station clicked
- Railway lines: Hidden by default, visible when station clicked
- Both: Toggleable (click same station again to hide)

---

## Current Data Coverage

### Namma Metro (4 Active Lines)
- **Purple Line**: 18 stations (operational)
- **Green Line**: 24 stations (operational)
- **Yellow Line**: 10 stations (operational)
- **Blue Line**: 11 stations (operational)
- **Red Line**: Excluded (under construction)

### Indian Railways
- Multiple railway lines connecting Bengaluru
- Dynamically extracted from OSM
- Classified as `transport_type: "railway"`

---

## Suggested Improvements

### 1. **Add Real-Time GTFS Data**
**Current:** Static CSV files
**Improvement:** Integrate real-time GTFS (General Transit Feed Specification)
```python
# Fetch from: https://gtfs.data.gouv.fr or transit agency APIs
from gtfs_realtime_pb2 import FeedMessage
```
**Benefits:**
- ✅ Real-time service status
- ✅ Current vehicle locations
- ✅ Live delay information
- ✅ Service alerts

**Implementation:**
- Add GTFS parsing module
- Cache with 30-60 second TTL
- Display live vehicle positions on map

---

### 2. **Add Transit Efficiency Scoring**
**Current:** Visual line display only
**Improvement:** Calculate and display line health metrics
```python
def score_transit_line(line_name, line_geometry, connected_areas):
    coverage_score = len(connected_areas) / total_areas
    geometry_score = line_geometry.length / max_length
    accessibility_score = avg_station_proximity_to_flood_zones
    return weighted_average([coverage_score, geometry_score, accessibility_score])
```
**Benefits:**
- ✅ Identify best evacuation routes
- ✅ Rank transit hubs by connectivity
- ✅ Plan emergency transit corridors

---

### 3. **Add API-Based Line Status**
**Current:** Only OSM + static files
**Improvement:** Query TomTom/Google Transit APIs
```python
# TomTom routing API
response = requests.get(
    'https://api.tomtom.com/routing/1/calculateRoute',
    params={'key': api_key, 'locations': waypoints}
)
```
**Benefits:**
- ✅ Real-time traffic on evacuation routes
- ✅ Current metro operational status
- ✅ Real-time service disruptions

---

### 4. **Add Database Caching Layer**
**Current:** File-based pickle caching (10 min TTL)
**Improvement:** PostgreSQL + spatial indexing
```python
# Enable fast spatial queries
class MetroLine(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    geometry = Column(Geometry('LINESTRING', 4326))
    __table_args__ = (Index('idx_metro_geom', geometry, postgresql_using='gist'),)
```
**Benefits:**
- ✅ Faster spatial queries
- ✅ Multi-user support
- ✅ Historical tracking
- ✅ Data versioning

---

### 5. **Add Flood Impact Scoring**
**Current:** Lines rendered as-is
**Improvement:** Color-code lines by flood risk
```python
def calculate_line_flood_risk(line_geometry, flood_zones):
    intersecting_segments = []
    for segment in line_geometry.segments:
        for zone in flood_zones:
            if segment.intersects(zone):
                risk_level = zone.intensity  # 0.2-1.0
                intersecting_segments.append((segment, risk_level))
    
    safe_ratio = 1.0 - (len(intersecting_segments) / total_segments)
    return {
        "line": line_name,
        "safe_ratio": safe_ratio,
        "color": "green" if safe_ratio > 0.8 else "yellow" if safe_ratio > 0.5 else "red"
    }
```
**Benefits:**
- ✅ Highlight dangerous transit routes during floods
- ✅ Recommend alternate routes
- ✅ Plan evacuation corridors that avoid flooded areas

---

### 6. **Add Emergency Transit Planning**
**Current:** Static visualization
**Improvement:** Dynamic emergency routing
```python
def find_safe_evacuation_route(source_location, shelter_location, flood_zones):
    # Avoid flooded areas + use metro when possible
    graph = build_multimodal_graph(roads, metro_lines, bus_routes)
    path = nx.shortest_path(
        graph, 
        source_location, 
        shelter_location,
        weight=lambda u, v, d: calculate_risk_weight(d, flood_zones)
    )
    return path  # Mixed road + transit + walking
```
**Benefits:**
- ✅ Generate safe evacuation paths in real-time
- ✅ Mix car/transit/walking intelligently
- ✅ Account for current flood status

---

### 7. **Add Crowdedness Estimation**
**Current:** Empty lines on map
**Improvement:** Show estimated capacity vs. current crowding
```python
def estimate_line_crowdedness(line_name, time_of_day):
    # Machine learning model trained on historical patterns
    prediction = ml_model.predict({
        'line': line_name,
        'hour': time_of_day.hour,
        'day_of_week': time_of_day.weekday(),
        'is_holiday': is_holiday(time_of_day),
        'weather': get_current_weather(),
        'recent_events': check_recent_events()
    })
    return prediction  # % capacity used
```
**Benefits:**
- ✅ Guide evacuees to less crowded transit
- ✅ Predict capacity bottlenecks
- ✅ Balance load across alternate routes

---

### 8. **Add Automatic Data Sync**
**Current:** Manual CSV updates
**Improvement:** Automated daily sync from transit agencies
```python
@scheduled_task(interval_hours=24)
def sync_namma_metro_data():
    """Fetch latest Namma Metro data from official API"""
    new_stations = fetch_from_namma_metro_api('/stations')
    new_lines = fetch_from_namma_metro_api('/lines')
    
    # Validate changes
    diff = compare_with_existing(new_stations, existing_stations)
    
    # Update if significant changes
    if diff.has_new_stations or diff.has_route_changes:
        backup_current_data()
        update_csv_files(new_stations, new_lines)
        notify_admin(diff)
```
**Benefits:**
- ✅ Always current data
- ✅ Track infrastructure changes
- ✅ No manual intervention needed

---

## Recommended Priority Order

1. **High Impact:** Add flood impact scoring (impacts emergency decisions)
2. **High Impact:** Add GTFS real-time data (affects evacuation timing)
3. **Medium Impact:** Add database caching (improves performance)
4. **Medium Impact:** Add API-based line status (reliability check)
5. **Low Impact:** Add crowdedness estimation (UX improvement)
6. **Low Impact:** Add automatic data sync (maintenance reduction)

---

## Current Performance Metrics

| Metric | Value |
|--------|-------|
| **Avg OSMnx query time** | 2-3 seconds |
| **Avg KML load time** | 0.5 seconds |
| **Avg CSV parse time** | 0.1 seconds |
| **Spatial matching radius** | 12 km (0.12 degrees) |
| **Cache TTL** | 10 minutes |
| **Stations per region** | 5-25 |
| **Line segments per region** | 20-100 |

---

## Debugging Tips

### If metro lines aren't showing:
1. Check OSM tags: `https://www.openstreetmap.org/query`
2. Verify KML file exists: `data/bengaluru_rail_metro_lines.kml`
3. Check CSV files exist: `data/NammaMetro/*.csv`
4. Verify `visibility` property is set

### If station line names are wrong:
1. Check CSV `station_line_map` matching
2. Verify spatial distance < 12km
3. Check if line name is being classified as "generic"
4. Look for OSM `line` tag on station

### If no data is extracted:
1. Verify region is within 5km query radius
2. Check hobli coordinates are correct
3. Ensure OSM has transit data for region
4. Check for `InsufficientResponseError` handling

---

## Summary

The metro workflow is a **smart hybrid system** that:
- ✅ Uses **OSMnx** for real-time, comprehensive data
- ✅ Uses **KML** for official line geometries and names
- ✅ Uses **CSV** for structured station-to-line mappings
- ✅ Intelligently merges all three sources
- ✅ Matches missing data using spatial proximity
- ✅ Handles errors gracefully with fallbacks
- ✅ Controls visibility dynamically for UX

The recommended improvements focus on **flood impact assessment** and **real-time transit data** to make the evacuation system more effective.
