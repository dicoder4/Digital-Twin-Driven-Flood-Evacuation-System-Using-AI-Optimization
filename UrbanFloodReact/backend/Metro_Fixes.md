  # Metro Network and Flood Status Fixes

  This document summarises the key fixes applied to resolve issues with metro line rendering and station flooding status in the Urban Flood Digital Twin.

  ## 1. Metro Line Rendering – Mislabeled Segments at Intersections

  ### Problem
  When selecting a metro line (e.g., Green line), stray segments belonging to other lines (e.g., Yellow line) appeared on the map, especially at intersections like RV Road and Jayadeva. This was caused by incorrect labelling of OSM line segments during backend processing.

  ### Root Cause
  The system merged OSM-extracted line geometries with reference datasets (KML, CSV) using spatial proximity.
  - At crossings, an **OSM segment** of the Yellow line could be physically closer to the Green reference line, causing it to be **mislabeled** as “Green”.
  - Merging logic then included this mislabeled segment in the Green line’s geometry, and the error propagated to the map.

  ### Solution
  - **Authoritative GeoJSON**: Switched to `metro-lines-stations.geojson` as the exclusive source for metro line geometries.
  - **OSM Removal**: Remove all OSM line extraction, KML merging, and label enrichment for lines (stations still use OSM and csv files for coordinate snapping only).
  - **Description Mapping**: Use the `description` field in the GeoJSON to correctly classify line colour (e.g., “purple”, “green”, “yellow”).
  - **Structure**: Store lines as a `FeatureCollection` with normalized `line` and `colour` properties for consistent frontend styling.

  ---

  ## 2. Metro Station Flood Status – Sensitivity Tuning

  ### Problem
  The metro station flood status was oscillating or reacting too slowly to rapid changes in flood intensity due to the Exponential Moving Average (EMA) smoothing parameters.

  ### Fix
  The smoothing factor for the EMA calculation in `service.py` was adjusted:
  - **Previous Weighting**: `0.65` Previous / `0.35` Current (Overly stable).
  - **New Weighting**: **`0.5` Previous / `0.5` Current** (Balanced sensitivity).


