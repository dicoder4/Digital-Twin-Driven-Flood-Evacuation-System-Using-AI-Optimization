import time
import requests
import concurrent.futures
from typing import List, Dict, Tuple, Optional

# Constants
TOMTOM_FLOW_API_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
MAX_CONCURRENT_REQUESTS = 10  # Prevent hitting rate limits aggressively

def fetch_traffic_for_segment(api_key: str, coord: Tuple[float, float]) -> Optional[Dict]:
    """
    Fetches traffic flow segment data for a single coordinate using TomTom API.
    coord: (lat, lon)
    Returns dictionary with speed data or None if failed.
    """
    lat, lon = coord
    params = {
        "point": f"{lat},{lon}",
        "unit": "KMPH",
        "thickness": 10,  # Road segment thickness to snap to
        "openLr": "false",
        "key": api_key
    }
    
    try:
        response = requests.get(TOMTOM_FLOW_API_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            flow_data = data.get("flowSegmentData", {})
            
            # Extract speeds
            current_speed = flow_data.get("currentSpeed")
            free_flow_speed = flow_data.get("freeFlowSpeed")
            current_time = flow_data.get("currentTravelTime")
            free_flow_time = flow_data.get("freeFlowTravelTime")
            
            if current_time and free_flow_time:
                return {
                    "current_speed": current_speed,
                    "free_flow_speed": free_flow_speed,
                    "current_time": current_time,
                    "free_flow_time": free_flow_time,
                    "lat": lat,
                    "lon": lon
                }
        elif response.status_code == 403:
            print(f"  [GA DEBUG] TomTom API forbidden for {lat},{lon}. Check API Key.")
        elif response.status_code == 429:
            print(f"  [GA DEBUG] TomTom API Rate Limited.")
        else:
             pass # other errors ignored for this segment
    except Exception as e:
        print(f"  [GA DEBUG] Error fetching traffic for {lat},{lon}: {e}")
        
    return None

def get_bulk_traffic_data(api_key: str, coords: List[Tuple[float, float]]) -> List[Dict]:
    """
    Synchronous wrapper to fetch traffic data for multiple coordinates using parallel workers.
    coords: List of (lat, lon) tuples representing midpoints of road segments.
    """
    if not api_key:
         print("  [GA DEBUG] TomTom API key not provided.")
         return []
         
    if not coords:
        return []

    print(f"  [GA DEBUG] Fetching TomTom traffic for {len(coords)} segments via ThreadPoolExecutor...")
    start_time = time.time()
    
    results = []
    
    # We use ThreadPoolExecutor to run multiple HTTP requests concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        # Submit all tasks to the thread pool
        futures = {executor.submit(fetch_traffic_for_segment, api_key, coord): coord for coord in coords}
        
        # As they complete, add them to our results array
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res is not None:
                results.append(res)
    
    elapsed = round(time.time() - start_time, 2)
    print(f"  [GA DEBUG] 🚥 TomTom fetched successfully: {len(results)}/{len(coords)} segments in {elapsed}s.")
    
    return results
