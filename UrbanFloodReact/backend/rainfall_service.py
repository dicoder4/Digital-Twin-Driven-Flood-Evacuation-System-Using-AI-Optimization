"""
Fetches live ward-level rainfall from KSNDMC (bengalurumeghasandesha.in).
Caches results for 5 minutes to avoid hammering the government endpoint.
Returns rainfall_mm dict and ward_centroids list.
"""
import httpx
import asyncio
import time
from math import radians, cos, sin, sqrt, atan2


_cache_mm: dict = {}
_cache_centroids: list = []
_last_fetch: float = 0.0
_lock = asyncio.Lock()
CACHE_TTL_SECONDS = 300

KSNDMC_URL = (
    "https://bengalurumeghasandesha.in:93"
    "/FloodForecastService.svc/Get_T_DataN"
)
KSNDMC_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bengalurumeghasandesha.in:93/city.htm?dtcode=01",
}


async def fetch_rainfall():
    """
    Fetches live rainfall from KSNDMC API.
    Returns (rainfall_mm, ward_centroids) tuple.
    On network failure, returns last cached data.
    On first-ever failure with empty cache, returns ({}, []).
    """
    global _cache_mm, _cache_centroids, _last_fetch

    async with _lock:
        if time.time() - _last_fetch < CACHE_TTL_SECONDS and _cache_mm:
            return _cache_mm, _cache_centroids

        try:
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                res = await client.post(
                    KSNDMC_URL,
                    json={"t_code": "01", "t_type": ""},
                    headers=KSNDMC_HEADERS,
                )
            res.raise_for_status()
            data = res.json()
            wards = data.get("Get_T_DataNResult", [{}])[0].get("GetTRGDataN", [])

            _cache_mm = {
                w["WARD_NAME"]: float(w.get("rain") or 0)
                for w in wards
            }
            _cache_centroids = [
                {
                    "ward": w["WARD_NAME"],
                    "hobli": w["HOBLINAME"],
                    "zone": w["ZONENAME"],
                    "lat": float(w["latitude"]),
                    "lon": float(w["longitude"]),
                    "rain_mm": float(w.get("rain") or 0),
                    "rain_time": w.get("rain_time", ""),
                }
                for w in wards
                if w.get("latitude") and w.get("longitude")
            ]
            _last_fetch = time.time()
        except Exception:
            pass

    return _cache_mm, _cache_centroids


def assign_wards_to_nodes(
    node_ids: list,
    node_coords: dict,
    ward_centroids: list,
) -> dict:
    """
    For each node, finds nearest ward centroid by haversine.
    Returns { node_id: ward_name }.
    """
    def haversine(lat1, lon1, lat2, lon2):
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return atan2(sqrt(a), sqrt(1 - a))

    ward_for_node = {}
    for nid in node_ids:
        lat, lon = node_coords[nid]
        if ward_centroids is not None and len(ward_centroids) > 0:
            nearest = min(
                ward_centroids,
                key=lambda w: haversine(lat, lon, w["lat"], w["lon"])
            )
            ward_for_node[nid] = nearest["ward"]
        else:
            ward_for_node[nid] = "unknown"
    return ward_for_node
