# transport_gtfs_mcp_server.py
# A small Transportation MCP server that reads GTFS to answer:
#   - nearest_bus_stop(lat, lon, top_n)
#   - fetch_bus_details(lat, lon)           -> routes serving the nearest bus stop
#   - nearest_metro_station(lat, lon, top_n)
#   - fetch_metro_details(lat, lon)         -> basic info for nearest metro station
#
# Routing note:
#   In floods your graph weights change—keep ALGO_ROUTE_URL (or GTFS_MCP_HTTP_URL) ready.
#   You can later add a 'plan_evac_route' tool that POSTs to ALGO_ROUTE_URL or relays to a GTFS‑MCP server.
#
# Data sources bundled in code (update as you get better feeds):
#   BMTC GTFS static (Mobility Database / TUMI mirror):                       (public)  [GTFS zip]
#     https://storage.googleapis.com/storage/v1/b/mdb-latest/o/in-karnataka-bangalore-metropolitan-transport-corporation-bmtc-gtfs-2013.zip?alt=media  # [1](https://hub.tumidata.org/dataset/gtfs-bengaluru)
#   Namma Metro (BMRCL) – Transport Data Hub portal (account may be required):       (portal)  [GTFS zip not pasted]
#     https://tdh.dult-karnataka.com/  # [3](https://tdh.dult-karnataka.com/)
#   Fallback for Metro stations (CSV list of station coordinates):                    (public)  [CSV]
#     https://www.kaggle.com/datasets/drahulsingh/namma-metro-stationsbengaluru      # [4](https://www.kaggle.com/datasets/drahulsingh/namma-metro-stationsbengaluru)
#
# Optional future integration:
#   gtfs‑mcp (HTTP/SSE) for in‑memory CSA routing & nearest-stop logic:
#   https://github.com/bribroder/gtfs-mcp  # [5](https://clemens.ms/enabling-geospatial-intelligence-in-llms-with-azure-maps-and-mcp/)

from __future__ import annotations
import os, io, csv, math, sys, json, time, zipfile, tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import requests

from mcp.server.fastmcp import FastMCP

# --------------------- CONFIG (all URLs in code as requested) ---------------------
# BMTC buses (GTFS local) — read directly from backend/data/bus_data/
DATA_DIR = Path(__file__).parent.parent / "data" / "bus_data"
BMTC_GTFS_SOURCE = "local_data_folder"

# BMRCL metro (GTFS) — if you have a downloadable zip URL from the Transport Data Hub, place it here.
# If left as None, we fall back to a public CSV of stations (coords only).
BMRCL_GTFS_ZIP_URL: Optional[str] = None  # e.g. "https://tdh.dult-karnataka.com/api/downloads/bmrcl_gtfs_latest.zip"

# Fallback CSV for station coordinates (Metro), used only when BMRCL_GTFS_ZIP_URL is None
BMRCL_STATIONS_CSV_URL = "https://raw.githubusercontent.com/plotly/datasets/master/2014_world_gdp_with_codes.csv"  # placeholder replaced below
# A tiny curated CSV we’ll inline at runtime if the above is not usable (few stations for demo)
_EMBEDDED_METRO_CSV = """name,lat,lon
MG Road,12.9756,77.6066
Trinity,12.9719,77.6193
Halasuru,12.9735,77.6288
Indiranagar,12.9784,77.6409
Vijayanagar,12.9720,77.5360
Majestic,12.9779,77.5727
KR Market,12.9656,77.5803
"""

# Optional future: point this at your “algo-runs” service for flood-weighted routing.
ALGO_ROUTE_URL: Optional[str] = None

# Optional future: if you run a GTFS‑MCP server over HTTP/SSE, put its MCP endpoint here.
GTFS_MCP_HTTP_URL: Optional[str] = None  # e.g. "http://localhost:8855/mcp"

# --------------------- Server init ---------------------
mcp = FastMCP("Bengaluru Transport (GTFS) MCP", json_response=True)

# --------------------- Utilities (lightweight) ---------------------
_CACHE: Dict[str, Path] = {}

def _haversine_km(a: Tuple[float,float], b: Tuple[float,float]) -> float:
    R=6371.0
    lat1,lon1,lat2,lon2 = map(math.radians, [a[0],a[1],b[0],b[1]])
    dlat, dlon = lat2-lat1, lon2-lon1
    x = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(x))

def _read_csv(filename: str, usecols: Optional[List[str]]=None) -> List[Dict[str,str]]:
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return []
        
    with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as f:
        rdr = csv.DictReader(f)
        rows=[]
        for row in rdr:
            if usecols:
                row = {k: row[k] for k in usecols if k in row}
            rows.append(row)
        return rows

def _nearest_stops_from_gtfs(lat: float, lon: float, top_n: int=3) -> List[Dict[str,Any]]:
    stops = _read_csv("stops.txt", ["stop_id","stop_name","stop_lat","stop_lon"])
    for s in stops:
        try:
            s["_d"] = _haversine_km((lat,lon),(float(s["stop_lat"]), float(s["stop_lon"])))
        except: s["_d"]=1e9
    stops.sort(key=lambda x: x["_d"])
    out=[]
    for s in stops[:max(1,top_n)]:
        out.append({
            "stop_id": s["stop_id"],
            "name": s["stop_name"],
            "lat": float(s["stop_lat"]),
            "lon": float(s["stop_lon"]),
            "distance_km": round(s["_d"],3)
        })
    return out

def _routes_for_stop(stop_id: str, max_routes: int=10) -> List[Dict[str,Any]]:
    # 1) stop_times -> trip_ids for this stop
    trips_for_stop=set()
    for row in _read_csv("stop_times.txt", ["trip_id","stop_id"]):
        if row["stop_id"]==stop_id:
            trips_for_stop.add(row["trip_id"])
    if not trips_for_stop:
        return []
    # 2) trips -> route_ids
    route_ids=set()
    for row in _read_csv("trips.txt", ["trip_id","route_id"]):
        if row["trip_id"] in trips_for_stop:
            route_ids.add(row["route_id"])
    # 3) routes -> names
    routes=[]
    for row in _read_csv("routes.txt", ["route_id","route_short_name","route_long_name"]):
        if row["route_id"] in route_ids:
            routes.append({
                "route_id": row["route_id"],
                "short_name": row.get("route_short_name") or "",
                "long_name": row.get("route_long_name") or ""
            })
    return routes[:max_routes]

def _metro_stations_fallback() -> List[Dict[str,Any]]:
    # [Temporarily disabled for Public Transport Agent expansion]
    # Try remote CSV (if you have a better one, set BMRCL_GTFS_ZIP_URL and read stops.txt instead)
    # try:
    #     r = requests.get(BMRCL_STATIONS_CSV_URL, timeout=20)
    #     r.raise_for_status()
    #     raise RuntimeError("Use embedded CSV")
    # except:
    #     rows=[]
    #     rdr = csv.DictReader(io.StringIO(_EMBEDDED_METRO_CSV))
    #     for row in rdr:
    #         rows.append({"name": row["name"], "lat": float(row["lat"]), "lon": float(row["lon"])})
    #     return rows
    return []

# --------------------- Resources ---------------------
@mcp.resource("gtfs://catalog")
def gtfs_catalog() -> str:
    return json.dumps({
        "bmtc_static_gtfs_source": BMTC_GTFS_SOURCE,
        "bmrcl_static_gtfs_url": BMRCL_GTFS_ZIP_URL,
        "bmrcl_stations_fallback_csv_used": BMRCL_GTFS_ZIP_URL is None
    }, ensure_ascii=False)

@mcp.resource("config://routing")
def routing_config() -> str:
    return json.dumps({"algo_route_url": ALGO_ROUTE_URL, "gtfs_mcp_http_url": GTFS_MCP_HTTP_URL}, ensure_ascii=False)

# --------------------- Prompt ---------------------
@mcp.prompt(title="Transport GTFS Data Plan")
def transport_prompt() -> str:
    return """Goal: For given coords (lat, lon) near Bengaluru, collect nearby public transport anchors for evacuation.
Use ONLY these tools on this server:
  - nearest_bus_stop(lat, lon, top_n=3)
  - fetch_bus_details(lat, lon)
Resources:
  - gtfs://catalog  -> lists GTFS URLs available
  - config://routing -> shows routing endpoints (for future plan_evac_route)
Return a compact JSON plan with steps to call those tools in order.
"""

# --------------------- Tools ---------------------
@mcp.tool()
def nearest_bus_stop(lat: float, lon: float, top_n: int = 3) -> Dict[str,Any]:
    """
    Find the nearest BMTC bus stops using GTFS static.
    """
    stops = _nearest_stops_from_gtfs(lat, lon, top_n=top_n)
    return {"stops": stops, "count": len(stops)}

@mcp.tool()
def fetch_bus_details(lat: float, lon: float) -> Dict[str,Any]:
    """
    For the nearest BMTC stop, list a few routes (short/long names).
    """
    stops = _nearest_stops_from_gtfs(lat, lon, top_n=1)
    if not stops:
        return {"error": "No stops found"}
    stop = stops[0]
    routes = _routes_for_stop(stop["stop_id"], max_routes=12)
    return {"nearest_stop": stop, "routes": routes}

def _nearest_from_list(lat: float, lon: float, items: List[Dict[str,Any]], key_lat="lat", key_lon="lon", name_key="name", top_n: int=3):
    for it in items:
        it["_d"] = _haversine_km((lat,lon), (float(it[key_lat]), float(it[key_lon])))
    items.sort(key=lambda x: x["_d"])
    out=[]
    for it in items[:max(1,top_n)]:
        out.append({
            "name": it.get(name_key,""),
            "lat": float(it[key_lat]),
            "lon": float(it[key_lon]),
            "distance_km": round(it["_d"],3)
        })
    return out

# Metro tools commented out as per DRA bus-only requirement
# @mcp.tool()
# def nearest_metro_station(lat: float, lon: float, top_n: int = 3) -> Dict[str,Any]:
#     ...

# @mcp.tool()
# def fetch_metro_details(lat: float, lon: float) -> Dict[str,Any]:
#     ...

if __name__ == "__main__":
    transport = "stdio" if (len(sys.argv) > 1 and sys.argv[1] == "stdio") else "streamable-http"
    mcp.run(transport=transport)

