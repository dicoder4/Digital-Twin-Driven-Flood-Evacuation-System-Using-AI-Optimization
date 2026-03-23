import math
from typing import List, Dict, Any

from .transport_gtfs_mcp_server import (
    _nearest_stops_from_gtfs,
    _routes_for_stop
)

def compute_bus_evacuation_plan(evacuation_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Takes an ACO evacuation plan and maps each route to a specific bus manifest 
    using the GTFS data.
    """
    print(f"DEBUG [transport_agent]: compute_bus_evacuation_plan called with {len(evacuation_plan)} routes")
    bus_plan = []
    bus_capacity = 50
    bus_id_counter = 1

    for i, route in enumerate(evacuation_plan):
        print(f"DEBUG [transport_agent] route {i}: keys={list(route.keys())}")
        path_points = route.get("path", route.get("path_points", []))
        if not path_points:
            print(f"DEBUG [transport_agent] route {i}: skipping because path_points is empty")
            continue
        
        # Origin is the first point in path_points (which is [lon, lat])
        origin_lon, origin_lat = path_points[0]
        print(f"DEBUG [transport_agent] route {i}: origin=({origin_lon}, {origin_lat})")
        
        # Find nearest bus stop to the origin
        try:
            stops = _nearest_stops_from_gtfs(origin_lat, origin_lon, top_n=1)
        except Exception as e:
            print(f"DEBUG [transport_agent] route {i}: _nearest_stops_from_gtfs exception: {e}")
            stops = []
            
        if not stops:
            print(f"DEBUG [transport_agent] route {i}: no stops found")
            continue
            
        stop = stops[0]
        stop_id = stop.get("stop_id")
        stop_name = stop.get("name", "Unknown Stop")
        
        # Fetch routes serving this exact stop
        routes = _routes_for_stop(stop_id, max_routes=1)
        route_name = "Emergency Shuttle"
        if routes:
            r = routes[0]
            route_name = r.get("short_name") or r.get("long_name") or "Emergency Shuttle"
            
        # The ACO plan defines population under "pop" or "evacuees"
        evacuees_count = route.get("pop", route.get("evacuees", 0))
        print(f"DEBUG [transport_agent] route {i}: evacuees_count={evacuees_count}")
        if evacuees_count <= 0:
            print(f"DEBUG [transport_agent] route {i}: skipping because evacuees_count is {evacuees_count}")
            continue
            
        to_shelter = route.get("to_shelter", "Unknown Shelter")
        
        # Calculate how many full/partial buses are needed
        num_buses = (evacuees_count + bus_capacity - 1) // bus_capacity
        
        for j in range(num_buses):
            # The last bus gets the remainder, earlier buses get full capacity
            load = bus_capacity if j < num_buses - 1 else (evacuees_count % bus_capacity) or bus_capacity
            
            # Create a dedicated bus trip
            bus_plan.append({
                "bus_id": f"BUS-{bus_id_counter:03d}",
                "route_name": route_name,
                "origin_stop_name": stop_name,
                "evacuees": load,
                "to_shelter": to_shelter,
                "path_points": path_points
            })
            bus_id_counter += 1
        print(f"DEBUG [transport_agent] route {i}: success, added {num_buses} buses")
            
    print(f"DEBUG [transport_agent]: returning manifest with {len(bus_plan)} buses")
    return {"status": "success", "manifest": bus_plan, "total_buses": len(bus_plan)}
