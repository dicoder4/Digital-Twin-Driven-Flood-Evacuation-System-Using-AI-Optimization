import sys
import os
from pathlib import Path

# Fix python path
current = Path(__file__).resolve().parent
backend = current.parent / "UrbanFloodReact" / "backend"
sys.path.append(str(backend))

from region_manager import initialise, get_region, extract_metro_data, norm_key

def verify():
    # Set up data directory
    initialise()
    
    hobli = "Uttarahalli-1"
    key = norm_key(hobli)
    print(f"Loading region {hobli}...")
    get_region(key)
    
    print(f"Extracting metro for {hobli}...")
    
    # We pass include_rail=True to see both types
    result = extract_metro_data(key, True)
    
    metro_lines = result.get("metro_lines", {})
    features = metro_lines.get("features", [])
    
    print(f"Extraction complete. Found {len(features)} line segments.")
    
    # Check for color mapping
    colours = {}
    for f in features:
        c = (f.get("properties") or {}).get("colour")
        colours[c] = colours.get(c, 0) + 1
        
    print(f"Color distribution: {colours}")
    
    # Check for unknown or neutral fallback
    if "unknown" in colours:
        print(f"DEBUG: Found {colours['unknown']} 'unknown' segments.")
    if "purple" in colours:
        print(f"WARNING: Found {colours['purple']} 'purple' segments.")
    
    # Check if geojson segments made it in
    geojson_count = sum(1 for f in features if (f.get("properties") or {}).get("source") == "bmrcl_geojson")
    clipped_count = sum(1 for f in features if "clipped" in str((f.get("properties") or {}).get("source", "")))
    
    print(f"BMRCL GeoJSON segments (unclipped): {geojson_count}")
    print(f"Clipped segments from reference: {clipped_count}")

if __name__ == "__main__":
    verify()
