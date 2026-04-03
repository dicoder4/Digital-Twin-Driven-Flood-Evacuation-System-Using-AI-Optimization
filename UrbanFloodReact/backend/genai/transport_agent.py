import math
from typing import List, Dict, Any

from .transport_gtfs_mcp_server import (
    _nearest_stops_from_gtfs,
    _routes_for_stop
)

def compute_bus_evacuation_plan(evacuation_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Takes an ACO evacuation plan and maps each route to a specific bus manifest 
    using the GTFS data. Groups evacuees by origin bus stop and destination shelter.
    """
    print(f"DEBUG [transport_agent]: compute_bus_evacuation_plan called with {len(evacuation_plan)} routes")
    bus_plan = []
    bus_capacity = 50
    bus_id_counter = 1

    grouped_routes: Dict[str, Any] = {}

    for i, route in enumerate(evacuation_plan):
        path_points = route.get("path", route.get("path_points", []))
        if not path_points or not isinstance(path_points, list):
            continue
        
        origin_lon, origin_lat = path_points[0]
        
        # Find nearest bus stop to the origin
        try:
            stops = _nearest_stops_from_gtfs(origin_lat, origin_lon, top_n=1)
        except Exception:
            stops = []
            
        if not stops:
            continue
            
        stop = stops[0]
        stop_id = stop.get("stop_id")
        stop_name = stop.get("name", "Unknown Stop")
        
        evacuees_count = route.get("pop", route.get("evacuees", 0))
        if evacuees_count <= 0:
            continue
            
        to_shelter = route.get("to_shelter", "Unknown Shelter")
        
        group_key = f"{stop_id}::{to_shelter}"
        if group_key not in grouped_routes:
            # Fetch routes serving this exact stop
            routes = _routes_for_stop(stop_id, max_routes=1)
            route_name = "Emergency Shuttle"
            if routes:
                r = routes[0]
                # In BMTC GTFS, the actual route name (e.g., 500D) is often in route_id
                route_name = r.get("route_id") or r.get("short_name") or r.get("long_name") or "Emergency Shuttle"
            
            grouped_routes[group_key] = {
                "stop_id": stop_id,
                "stop_name": stop_name,
                "to_shelter": to_shelter,
                "evacuees_count": 0,
                "route_name": route_name,
                "path_points": path_points
            }
        
        grouped_routes[group_key]["evacuees_count"] += evacuees_count

    # Calculate how many full/partial buses are needed for each aggregated group
    for gp in grouped_routes.values():
        evacuees_count = gp["evacuees_count"]
        # Filter off empty coordinate arrays just to be safe for MapLibre
        valid_path = gp["path_points"] if len(gp["path_points"]) >= 2 else []
        
        num_buses = (evacuees_count + bus_capacity - 1) // bus_capacity
        
        for j in range(num_buses):
            load = bus_capacity if j < num_buses - 1 else (evacuees_count % bus_capacity) or bus_capacity
            
            bus_plan.append({
                "bus_id": f"BUS-{bus_id_counter:03d}",
                "route_name": gp["route_name"],
                "origin_stop_name": gp["stop_name"],
                "evacuees": load,
                "to_shelter": gp["to_shelter"],
                "path_points": valid_path
            })
            bus_id_counter += 1
            
    # Sort the bus plan: Actual routes first, then Emergency Shuttles
    bus_plan.sort(key=lambda x: 1 if x["route_name"] == "Emergency Shuttle" else 0)
    
    # Reassign sequential bus IDs after sorting for a cleaner manifest
    for idx, bus in enumerate(bus_plan):
        bus["bus_id"] = f"BUS-{idx + 1:03d}"
            
    print(f"DEBUG [transport_agent]: returning manifest with {len(bus_plan)} buses")
    return {"status": "success", "manifest": bus_plan, "total_buses": len(bus_plan)}
