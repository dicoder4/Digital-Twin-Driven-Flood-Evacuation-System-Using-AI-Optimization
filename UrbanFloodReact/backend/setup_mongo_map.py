import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import networkx as nx
import osmnx as ox
from pymongo import MongoClient, GEOSPHERE

# Ensure the backend directory is in the path to import local modules
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))

import gis_terrain_loader

env_path = current_dir.parent / '.env'
load_dotenv(dotenv_path=env_path)

MONGO_URL = os.getenv("MONGO_URL2") or os.getenv("MONGO_URI2")
if not MONGO_URL:
    print("CRITICAL: MONGO_URL not found in environment variables.")
    sys.exit(1)

def get_db():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    return client.get_database("flood_evacuation_db")

def create_geojson_from_edge(u, v, data, G):
    """Ensure the edge has a valid GeoJSON LineString."""
    if "geometry" in data:
        # It's a shapely LineString
        coords = list(data["geometry"].coords)
    else:
        # It's a straight line between u and v
        u_node = G.nodes[u]
        v_node = G.nodes[v]
        coords = [[u_node['x'], u_node['y']], [v_node['x'], v_node['y']]]
    return {"type": "LineString", "coordinates": coords}

def main():
    db = get_db()
    
    print("==================================================")
    print("1. Downloading Bangalore Map via OpenStreetMap")
    print("==================================================")
    # Use a large bounding box or place name. Bangalore, India works well.
    try:
        G = ox.graph_from_place('Bangalore, India', network_type='drive')
        print(f"Downloaded graph: {len(G.nodes)} nodes, {len(G.edges)} edges.")
    except Exception as e:
        print(f"Failed to download map: {e}")
        sys.exit(1)

    # Calculate center and radius for GIS enrichment
    lats = [data['y'] for _, data in G.nodes(data=True)]
    lons = [data['x'] for _, data in G.nodes(data=True)]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)
    
    # Approx radius in meters to cover the bounding box
    import math
    from shapely.geometry import Point
    
    # Calculate approx distance from center to a corner using haversine or just estimate
    # A generous 30km radius covers Bangalore city limits easily.
    city_radius_m = 30000 
    
    print("\n==================================================")
    print("2. Enriching Graph with Elevation (OpenTopography)")
    print("==================================================")
    # This caches in MongoDB (dem_cache) automatically via the gis module
    G = gis_terrain_loader.enrich_graph_elevation(G, center_lat, center_lon, city_radius_m)

    print("\n==================================================")
    print("3. Enriching Graph with Surface Roughness")
    print("==================================================")
    G = gis_terrain_loader.enrich_graph_roughness(G)

    print("\n==================================================")
    print("4. Fetching Hydrology Data (Drains & Lakes)")
    print("==================================================")
    drain_nodes, lake_nodes = [], []
    try:
        # This might take a while for 30km radius. Overpass has timeouts.
        drain_nodes, lake_nodes = gis_terrain_loader.get_gis_hydrology_nodes(G, center_lat, center_lon, city_radius_m)
    except Exception as e:
        print(f"Warning: Failed to fetch hydrology data for the whole city. {e}")
        print("Proceeding without drain/lake tagging...")

    drain_set = set(drain_nodes)
    lake_set = set(lake_nodes)

    print("\n==================================================")
    print("5. Processing and Uploading Nodes to MongoDB")
    print("==================================================")
    nodes_collection = db["city_nodes"]
    nodes_collection.drop() # Clear old data
    
    node_docs = []
    for n, data in G.nodes(data=True):
        doc = {
            "_id": n,
            "x": data['x'],
            "y": data['y'],
            "elevation": data.get("elevation", 0.0),
            "is_drain": n in drain_set,
            "is_lake": n in lake_set,
            "location": {
                "type": "Point",
                "coordinates": [data['x'], data['y']]
            }
        }
        node_docs.append(doc)
        
    if node_docs:
        nodes_collection.insert_many(node_docs)
        nodes_collection.create_index([("location", GEOSPHERE)])
        print(f"Successfully inserted {len(node_docs)} nodes.")

    print("\n==================================================")
    print("6. Processing and Uploading Edges to MongoDB")
    print("==================================================")
    edges_collection = db["city_edges"]
    edges_collection.drop() # Clear old data
    
    edge_docs = []
    for u, v, k, data in G.edges(data=True, keys=True):
        highway = data.get("highway", "residential")
        if isinstance(highway, list): highway = highway[0]
            
        doc = {
            "_id": f"{u}_{v}_{k}",
            "u": u,
            "v": v,
            "k": k,
            "length": data.get("length", 0.0),
            "highway": highway,
            "flow_efficiency": data.get("flow_efficiency", 1.0),
            "location": create_geojson_from_edge(u, v, data, G)
        }
        # Keep any other useful attributes
        if "maxspeed" in data:
            doc["maxspeed"] = data["maxspeed"]
        if "lanes" in data:
            doc["lanes"] = data["lanes"]
            
        edge_docs.append(doc)
        
    if edge_docs:
        # Chunk the insertions to avoid memory/BSON limits
        chunk_size = 50000
        for i in range(0, len(edge_docs), chunk_size):
            edges_collection.insert_many(edge_docs[i:i+chunk_size])
        
        edges_collection.create_index([("location", GEOSPHERE)])
        print(f"Successfully inserted {len(edge_docs)} edges.")

    print("\n==================================================")
    print("DONE! Bangalore Map is now fully stored in MongoDB")
    print("==================================================")

if __name__ == "__main__":
    main()
