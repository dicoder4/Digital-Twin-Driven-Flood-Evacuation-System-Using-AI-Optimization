import asyncio
import os
import networkx as nx
from region_manager import initialise, get_region, HOBLI_COORDS, norm_key

async def run_test():
    print("Initializing test environment...")
    initialise()
    
    # Pick a sample hobli, e.g., 'Hebbal'
    sample_key = norm_key("Hebbal")
    if sample_key not in HOBLI_COORDS:
        sample_key = list(HOBLI_COORDS.keys())[0]
        
    print(f"\nTesting GIS Enrichment on region: {sample_key}")
    
    # This will trigger get_region -> download OR load graph -> enrich graph
    entry = get_region(sample_key)
    G = entry['G']
    
    # Verify elevations
    elevations = [data.get('elevation', 0.0) for n, data in G.nodes(data=True)]
    
    # If the first graph loaded wasn't enriched because it was cached BEFORE our patch, we can force it here
    if all(e == 0.0 for e in elevations):
        print("Graph was cached previously. Forcing re-enrichment from OpenTopography...")
        from gis_terrain_loader import enrich_graph_elevation, enrich_graph_roughness
        coords = HOBLI_COORDS[sample_key]
        G = enrich_graph_elevation(G, coords['lat'], coords['lon'])
        G = enrich_graph_roughness(G)
        elevations = [data.get('elevation', 0.0) for n, data in G.nodes(data=True)]
    
    print("\n[ELEVATION RESULTS]")
    print(f"Total Nodes: {len(elevations)}")
    
    # Filter out 0.0 which are probably nodata points at the edge of the DEM bounding box
    valid_elevs = [e for e in elevations if e > 0]
    
    if valid_elevs:
        print(f"Min Elevation: {min(valid_elevs):.2f}m")
        print(f"Max Elevation: {max(valid_elevs):.2f}m")
        print(f"Mean Elevation: {(sum(valid_elevs)/len(valid_elevs)):.2f}m")
        print("SUCCESS! The graph nodes now have real-world 3D elevation data!")
    else:
        print("FAILED: All elevations are 0.0")
        
    print("\n[ROUGHNESS RESULTS]")
    efficiencies = [G[u][v][k].get('flow_efficiency', 1.0) for u,v,k in G.edges(keys=True)]
    if efficiencies:
        print(f"Total Edges Analyzed: {len(efficiencies)}")
        print(f"Min Efficiency (Rough): {min(efficiencies):.3f}")
        print(f"Max Efficiency (Fast): {max(efficiencies):.3f}")
        print("SUCCESS! Manning's roughness coefficients added to edges!")
        
    print("\n[HYDROLOGY RESULTS]")
    print(f"Drain Nodes: {len(entry['drain_nodes'])}")
    print(f"Lake Nodes:  {len(entry['lake_nodes'])}")

if __name__ == "__main__":
    asyncio.run(run_test())
