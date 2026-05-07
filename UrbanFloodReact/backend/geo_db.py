"""
MONGO_URI2 connection and corridor query functions.
Database: flood_evacuation_db
Collections: city_nodes, city_edges
"""
from motor.motor_asyncio import AsyncIOMotorClient
from math import radians, cos
import os


_geo_client = None


def get_geo_db():
    global _geo_client
    if _geo_client is None:
        uri = os.getenv("MONGO_URI2", "")
        if not uri:
            raise RuntimeError("MONGO_URI2 environment variable not set")
        if "&authSource=admin" not in uri:
            uri = uri + "&authSource=admin"
        _geo_client = AsyncIOMotorClient(uri)
    return _geo_client["flood_evacuation_db"]


def _make_bbox_polygon(min_lon, min_lat, max_lon, max_lat) -> dict:
    """Creates a GeoJSON Polygon from bounding box coordinates."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat], [max_lon, min_lat],
            [max_lon, max_lat], [min_lon, max_lat],
            [min_lon, min_lat]
        ]]
    }


def _build_corridor_bbox(src_lat, src_lon, dst_lat, dst_lon, buffer_km=1.0):
    """
    Computes bounding box for corridor including buffer.
    Returns (min_lon, min_lat, max_lon, max_lat).
    """
    deg_lat = buffer_km / 111.0
    deg_lon = buffer_km / (111.0 * cos(radians((src_lat + dst_lat) / 2)))
    return (
        min(src_lon, dst_lon) - deg_lon,
        min(src_lat, dst_lat) - deg_lat,
        max(src_lon, dst_lon) + deg_lon,
        max(src_lat, dst_lat) + deg_lat,
    )


async def fetch_corridor(src_lat, src_lon, dst_lat, dst_lon, buffer_km=1.0):
    """
    Fetches all edges and nodes within corridor bounding box.
    Returns (edges: list, nodes: list, bbox: tuple).
    """
    db = get_geo_db()
    min_lon, min_lat, max_lon, max_lat = _build_corridor_bbox(
        src_lat, src_lon, dst_lat, dst_lon, buffer_km
    )
    poly = _make_bbox_polygon(min_lon, min_lat, max_lon, max_lat)

    # Fetch edges intersecting corridor polygon
    edges = await db.city_edges.find(
        {"location": {"$geoIntersects": {"$geometry": poly}}}
    ).to_list(length=60000)

    # Collect all node IDs referenced by these edges
    node_ids = set()
    for e in edges:
        node_ids.update([e["u"], e["v"]])

    # Fetch node documents
    nodes = await db.city_nodes.find(
        {"_id": {"$in": list(node_ids)}}
    ).to_list(length=120000)

    return edges, nodes, (min_lon, min_lat, max_lon, max_lat)


async def find_nearest_node(lat, lon, max_dist_m=500):
    """
    Finds nearest city_node to a GPS point using geospatial index.
    Used for snapping src/dst coordinates to road network.
    Returns node dict or None if none found within max_dist_m.
    """
    db = get_geo_db()
    cursor = db.city_nodes.find({
        "location": {
            "$near": {
                "$geometry": {"type": "Point", "coordinates": [lon, lat]},
                "$maxDistance": max_dist_m
            }
        }
    }).limit(1)
    results = await cursor.to_list(length=1)
    return results[0] if results else None
