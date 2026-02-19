
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union

def create_elevation_grid(edges_gdf, resolution=50):
    """
    Creates a grid of elevation points based on road network nodes and edges.
    In a real app, this would query a DEM (Digital Elevation Model).
    Here, we interpolate/extrapolate from the graph nodes or just mock it relative to a 'river' or center.
    """
    if edges_gdf is None or edges_gdf.empty:
        return gpd.GeoDataFrame(columns=['geometry', 'elevation'], crs="EPSG:4326")

    # Get bounds
    minx, miny, maxx, maxy = edges_gdf.total_bounds
    
    # Create grid points
    x = np.linspace(minx, maxx, resolution)
    y = np.linspace(miny, maxy, resolution)
    xv, yv = np.meshgrid(x, y)
    
    # Flatten
    points = [Point(px, py) for px, py in zip(xv.flatten(), yv.flatten())]
    
    # Mock Elevation: 
    # Assume lower elevation near the center or specific "water" nodes?
    # For now, let's just make a simple bowl shape or slope for demo.
    # Linear slope from South-West (Low) to North-East (High) + some noise
    # Normalized coords
    norm_x = (xv.flatten() - minx) / (maxx - minx)
    norm_y = (yv.flatten() - miny) / (maxy - miny)
    
    # Elevation from 0m to 8m (Flatter terrain for meaningful flooding at 5m)
    # 0 at bottom-left, 8 at top-right
    # Add some randomness
    elevations = (norm_x + norm_y) * 4 + np.random.rand(len(points)) * 0.5
    
    grid_gdf = gpd.GeoDataFrame({'elevation': elevations}, geometry=points, crs=edges_gdf.crs)
    
    # Buffer points to create cells for visualization (optional, or just return points)
    # Better to return Polygons for the flood layer
    # Calculate cell size
    cell_w = (maxx - minx) / resolution
    cell_h = (maxy - miny) / resolution
    
    # Create square polygons centered on points
    polys = []
    for pt in points:
        polys.append(Polygon([
            (pt.x - cell_w/2, pt.y - cell_h/2),
            (pt.x + cell_w/2, pt.y - cell_h/2),
            (pt.x + cell_w/2, pt.y + cell_h/2),
            (pt.x - cell_w/2, pt.y + cell_h/2)
        ]))
        
    grid_gdf['geometry'] = polys
    return grid_gdf

class DynamicFloodSimulator:
    def __init__(self, elev_gdf, edges, nodes, station, lat, lon, peak_flood_level=10.0, initial_people=50):
        self.elev_gdf = elev_gdf
        self.edges = edges
        self.nodes = nodes
        self.center_point = Point(lon, lat)
        self.input_peak_flood_level = float(peak_flood_level)
        
        # Generate random people
        self.people_gdf = self._generate_people(initial_people)
        
    def _generate_people(self, count):
        """Generate random people on the road network."""
        if self.edges is None or self.edges.empty:
            return gpd.GeoDataFrame(columns=['person_id', 'geometry'], crs="EPSG:4326")
            
        minx, miny, maxx, maxy = self.edges.total_bounds
        people = []
        for i in range(count):
            # Random point
            px = np.random.uniform(minx, maxx)
            py = np.random.uniform(miny, maxy)
            people.append({'person_id': i, 'geometry': Point(px, py)})
            
        return gpd.GeoDataFrame(people, crs=self.edges.crs)

    def update_people_count(self, count):
        current = len(self.people_gdf)
        if count > current:
            # Add more
            new_people = self._generate_people(count - current)
            # Adjust IDs
            start_id = self.people_gdf['person_id'].max() + 1 if not self.people_gdf.empty else 0
            new_people['person_id'] = range(start_id, start_id + len(new_people))
            self.people_gdf = pd.concat([self.people_gdf, new_people], ignore_index=True)
        elif count < current:
            # Remove some
            self.people_gdf = self.people_gdf.iloc[:count]

    def _calculate_flood_impact(self, flood_fraction=0.0):
        """
        Calculate flood based on elevation.
        flood_fraction: 0.0 to 1.0 (Percentage of Peak Flood Level)
        """
        # 1. Determine current water height
        current_water_level = self.input_peak_flood_level * flood_fraction
        
        print(f"[DEBUG] Flood Calc: Frac={flood_fraction:.2f}, WaterLvl={current_water_level:.2f}, Peak={self.input_peak_flood_level}")

        # 2. Identify Flooded Cells (Elevation < Water Level)
        if self.elev_gdf is not None and not self.elev_gdf.empty:
             flooded_cells = self.elev_gdf[self.elev_gdf['elevation'] <= current_water_level]
             print(f"[DEBUG] Flooded Cells: {len(flooded_cells)} / {len(self.elev_gdf)}")
        else:
             flooded_cells = gpd.GeoDataFrame()
             print("[DEBUG] Elevation Grid is EMPTY")
             
        # 3. Create Flood Geometries (Intensity layers?)
        # For simplicity, just one layer for now, or maybe graded
        # Let's do a simple gradient: Deep (> 0.5 depth) vs Shallow
        
        flood_gdf = gpd.GeoDataFrame(columns=['geometry', 'intensity'], crs=self.edges.crs)
        
        if not flooded_cells.empty:
            # Union all flooded cells
            # To make it look nice, we can assign intensity based on depth
            # Depth = Water Level - Elevation
            flooded_cells = flooded_cells.copy()
            flooded_cells['depth'] = current_water_level - flooded_cells['elevation']
            flooded_cells['intensity'] = flooded_cells['depth'] / (self.input_peak_flood_level or 1.0)
            flooded_cells['intensity'] = flooded_cells['intensity'].clip(0, 1)

            # Simplify: Just return the flooded area polygons with average intensity?
            # Or simplified geometry
            
            # Optimization: Unary Union is expensive if many cells.
            # But grid is regular.
            # Let's just return the cells directly if resolution is low, or union logic
            
            # Let's bin intensity for visual bands
            # > 0.8 max depth, > 0.4 max depth
            # But user wants "clean" look.
            
            # Just union everything for the "Water" shape
            water_poly = unary_union(flooded_cells.geometry)
            if water_poly.geom_type == 'Polygon':
                water_poly = MultiPolygon([water_poly])
                
            flood_gdf = gpd.GeoDataFrame({'geometry': [water_poly], 'intensity': [flood_fraction]}, crs=self.edges.crs)


        # 4. Flooded People
        flooded_people_ids = []
        safe_people_ids = []
        flooded_people_gdf = gpd.GeoDataFrame()
        safe_people_gdf = gpd.GeoDataFrame()

        if not self.people_gdf.empty and not flood_gdf.empty:
            # Spatial Join or Check contains
            # Since flood_gdf is complex, verify geometry validity
            flood_union = flood_gdf.unary_union
            
            # Check which people are inside
            is_flooded = self.people_gdf.geometry.within(flood_union)
            flooded_people_gdf = self.people_gdf[is_flooded]
            safe_people_gdf = self.people_gdf[~is_flooded]
            print(f"[DEBUG] People Flooded: {len(flooded_people_gdf)} / {len(self.people_gdf)}")
            
        else:
            safe_people_gdf = self.people_gdf

        # 5. Blocked Roads
        blocked_edges = gpd.GeoDataFrame()
        if not self.edges.empty and not flood_gdf.empty:
             # Check distinct roads intersecting flood
             flood_union = flood_gdf.unary_union
             is_blocked = self.edges.intersects(flood_union)
             blocked_edges = self.edges[is_blocked].copy()
             blocked_edges['risk'] = 'high' # Simple risk model

        return {
            "flood_gdf": flood_gdf,
            "blocked_edges": blocked_edges,
            "flooded_people": flooded_people_gdf,
            "safe_people": safe_people_gdf
        }
