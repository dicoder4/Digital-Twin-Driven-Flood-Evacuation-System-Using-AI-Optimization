"""
OSM enrichment for citizen routing.
Fetches street names from OSM and attaches to corridor edges.
Handles edge (node-pair) name lookups efficiently.
"""
import osmnx as ox
import networkx as nx
from shapely.geometry import Point, LineString, box
import logging

logger = logging.getLogger(__name__)


def enrich_edges_with_names(
    G: nx.DiGraph,
    edges_mongodb: list,
    src_lat: float,
    src_lon: float,
    dst_lat: float,
    dst_lon: float,
    buffer_deg: float = 0.05  # ~5km at equator
) -> dict:
    """
    Fetch OSM data for the corridor and attach street names to edges.
    Returns dict mapping edge (u, v, k) to street name.

    Handles cases where:
    - OSM data is unavailable (returns empty dict)
    - Network is disconnected (partial enrichment is OK)
    - Names contain special characters (stored as-is)

    Args:
        G: NetworkX DiGraph (for node coordinates)
        edges_mongodb: List of edge dicts from MongoDB
        src_lat, src_lon, dst_lat, dst_lon: Route endpoints
        buffer_deg: Buffer around route for OSM query

    Returns:
        { (u, v, k): "Street Name" } mapping, or empty dict on error
    """
    try:
        # 1. Define query area (small buffer around corridor)
        min_lat = min(src_lat, dst_lat) - buffer_deg
        max_lat = max(src_lat, dst_lat) + buffer_deg
        min_lon = min(src_lon, dst_lon) - buffer_deg
        max_lon = max(src_lon, dst_lon) + buffer_deg

        logger.info(f"Fetching OSM street data for corridor ({min_lat:.4f},{min_lon:.4f}) to ({max_lat:.4f},{max_lon:.4f})")

        # 2. Query OSM street network
        try:
            # Use north, south, east, west format
            G_osm = ox.graph_from_bbox(north=max_lat, south=min_lat, east=max_lon, west=min_lon, network_type='drive', simplify=True)
        except Exception as e:
            logger.warning(f"OSM query failed: {e}. Proceeding without street names.")
            return {}

        if G_osm is None or len(G_osm.edges()) == 0:
            logger.warning("OSM query returned empty graph. Proceeding without street names.")
            return {}

        # 3. Build lookup: edge location → name
        # OSM edges have (u, v, key) structure; extract names
        osm_names = {}
        for u, v, key, data in G_osm.edges(keys=True, data=True):
            # Get edge geometry from OSM
            if 'geometry' in data:
                geom = data['geometry']
            else:
                u_data = G_osm.nodes[u]
                v_data = G_osm.nodes[v]
                geom = LineString([(u_data['x'], u_data['y']), (v_data['x'], v_data['y'])])

            # Get street name (OSM name can be a list)
            name = data.get('name', 'Unnamed Street')
            if isinstance(name, list):
                name = name[0] if name else 'Unnamed Street'
            osm_names[geom] = name

        # 4. Match MongoDB edges to OSM names by proximity
        edge_names = {}
        for edge in edges_mongodb:
            u, v = edge['u'], edge['v']
            k = edge.get('k', 0)
            edge_key = (u, v, k)

            # Get edge geometry from MongoDB
            if 'location' in edge and edge['location'].get('type') == 'LineString':
                coords = edge['location']['coordinates']
                edge_geom = LineString(coords)

                # Find nearest OSM edge by centroid proximity
                best_name = None
                best_dist = float('inf')

                for osm_geom, name in osm_names.items():
                    dist = edge_geom.centroid.distance(osm_geom.centroid)
                    if dist < best_dist and dist < 0.001:  # ~100m at equator
                        best_dist = dist
                        best_name = name

                if best_name:
                    edge_names[edge_key] = best_name

        logger.info(f"Enriched {len(edge_names)} / {len(edges_mongodb)} edges with street names")
        return edge_names

    except Exception as e:
        logger.error(f"OSM enrichment failed: {e}", exc_info=True)
        return {}


def get_edge_name(
    u: int,
    v: int,
    k: int,
    enrichment_map: dict,
    fallback_highway: str = "road"
) -> str:
    """
    Get street name for an edge, with fallback to highway type.

    Args:
        u, v, k: Edge identifiers
        enrichment_map: From enrich_edges_with_names()
        fallback_highway: Highway type if no name found

    Returns:
        Street name or formatted highway type
    """
    edge_key = (u, v, k)
    if edge_key in enrichment_map:
        return enrichment_map[edge_key]

    # Fallback to formatted highway type
    if fallback_highway:
        return fallback_highway.replace("_", " ").title()
    return "Road"
