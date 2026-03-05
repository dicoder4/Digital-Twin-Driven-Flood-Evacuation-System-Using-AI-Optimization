import numpy as np
import geopandas as gpd
import random
from shapely.geometry import Point, LineString, Polygon, MultiPolygon
from shapely.ops import unary_union
import matplotlib.cm as cm
from matplotlib.colors import to_hex
import osmnx as ox
import networkx as nx

class UrbanFloodSimulator:
    """
    Physics-based Urban Flood Simulator (SWMM-simplified).
    Uses hydraulic head (Elevation + Water Depth) to propagate water flow.
    """
    def __init__(self, G, drain_nodes=None, lake_nodes=None):
        self.G = G
        if drain_nodes is not None and len(drain_nodes) > 0:
            self.drain_nodes = list(drain_nodes) 
        else:
            self.drain_nodes = []
            
        if lake_nodes is not None and len(lake_nodes) > 0:
            self.lake_nodes = list(lake_nodes)
        else:
            self.lake_nodes = []
            
        self.people_gdf = gpd.GeoDataFrame(columns=['person_id', 'geometry'], crs=G.graph['crs'])
        self.current_people_count = 0
        self.node_populations = {} # node_id -> person_count
        self.shelter_occupancy = {} # shelter_id -> person_count
        self.total_evacuated = 0

    def initialize_flood(self, rainfall_mm):
        """
        Apply uniform rainfall to all nodes. 
        (Legacy method, kept for compatibility if needed, but we will use drain logic)
        """
        rainfall_m = rainfall_mm / 1000.0
        nx.set_node_attributes(self.G, rainfall_m, 'water_depth')
        return self.G

    def initialize_from_drains(self, rainfall_mm):
        """
        Initialize flooding starting from drain nodes AND lake nodes.
        Drain nodes get high water level representing overflow.
        Lake nodes get EXTRA high water level to force spread.
        """
        # Reset all to 0
        nx.set_node_attributes(self.G, 0.0, 'water_depth')
        
        if not self.drain_nodes and not self.lake_nodes:
            # Fallback
            elevs = nx.get_node_attributes(self.G, 'elevation')
            if elevs:
                 sorted_nodes = sorted(elevs, key=elevs.get)
                 self.drain_nodes = sorted_nodes[:10]
            else:
                 self.drain_nodes = list(self.G.nodes())[:10]

        # 1. Drains Overflow
        drain_head = (rainfall_mm / 1000.0) * 25.0 
        for node in self.drain_nodes:
            self.G.nodes[node]['water_depth'] = drain_head
            
        # 2. Lake Overflow (Simulate Breach/High Level)
        # Give lakes masssive head to force flow outward strongly
        lake_head = (rainfall_mm / 1000.0) * 100.0
        for node in self.lake_nodes:
             # Only if node exists in graph (should be checked by nearest_nodes but safety first)
             if self.G.has_node(node):
                self.G.nodes[node]['water_depth'] = lake_head
            
        return self.G

    def propagate_flood_step(self, decay_factor=0.5):
        """
        Propagate water based on Hydraulic Head (Elevation + Water Depth).
        Water flows from High Head to Low Head.
        """
        current_depths = nx.get_node_attributes(self.G, 'water_depth')
        elevations = nx.get_node_attributes(self.G, 'elevation')
        
        # Ensure elevation data exists
        if not elevations:
             elevations = {n: 0.0 for n in self.G.nodes()}
        for n in self.G.nodes():
            if n not in elevations: elevations[n] = 0.0

        new_depths = current_depths.copy()

        # For every node with water
        for node in self.G.nodes():
            if node not in current_depths: continue
            
            water_depth = current_depths[node]
            if water_depth <= 0.001: continue 

            node_head = elevations[node] + water_depth
            
            neighbors = list(self.G.neighbors(node))
            lower_head_neighbors = []
            total_head_diff = 0

            # Find neighbors with LOWER TOTAL HEAD
            for n in neighbors:
                n_elev = elevations.get(n, 0.0)
                n_water = current_depths.get(n, 0.0)
                n_head = n_elev + n_water
                
                if n_head < node_head:
                    # Drive flow by head difference
                    head_diff = node_head - n_head
                    lower_head_neighbors.append((n, head_diff))
                    total_head_diff += head_diff

            if not lower_head_neighbors:
                continue

            # Distribute water
            # Flow amount depends on how much water is available 'above' the neighbor's head?
            # Simplified: Move a fraction of the water depth
            flow_out = water_depth * decay_factor

            for n, diff in lower_head_neighbors:
                fraction = diff / total_head_diff
                amount = flow_out * fraction
                
                # Check safeguards: Don't drain below neighbor's head (basic equalization)
                # But for simple viz, just moving mass is fine.
                
                if node in new_depths:
                    new_depths[node] -= amount
                if n in new_depths:
                    new_depths[n] += amount
        
        # Continuous visual rain on drains? 
        # Optional: Add small increment to drains to simulate continuous overflow
        # for d in self.drain_nodes:
        #     new_depths[d] += 0.01 

        nx.set_node_attributes(self.G, new_depths, 'water_depth')
        return self.G

    def distribute_population(self, total_pop):
        """
        Distribute population across graph nodes.
        For simplicity, we distribute evenly across all nodes, but this could be
        weighted by degree or land use.
        """
        nodes = list(self.G.nodes())
        if not nodes: return
        
        per_node = total_pop // len(nodes)
        rem = total_pop % len(nodes)
        
        self.node_populations = {n: per_node for n in nodes}
        # Distribute remainder
        for i in range(rem):
            self.node_populations[nodes[i]] += 1
            
        print(f"  [flood_sim] Distributed {total_pop} people across {len(nodes)} nodes")

    def get_at_risk_nodes(self, depth_threshold_m=0.15):
        """
        Identify nodes where water depth > threshold and there are people present.
        Returns a list of (node_id, population)
        """
        node_depths = nx.get_node_attributes(self.G, 'water_depth')
        at_risk = []
        for n, depth in node_depths.items():
            pop = self.node_populations.get(n, 0)
            if depth > depth_threshold_m and pop > 0:
                at_risk.append((n, pop))
        return at_risk

    def calculate_flood_impact(self):
        """
        Calculate flood impact. Returns 3 tiered MultiPolygons for Low, Medium, High depth.
        This allows cleaner "polygon" visualization than thousands of circles.
        """
        node_depths = nx.get_node_attributes(self.G, 'water_depth')
        
        # Buckets for levels
        level1_geoms = [] # Shallow (0.05m - 0.5m)
        level2_geoms = [] # Moderate (0.5m - 1.5m)
        level3_geoms = [] # Deep (> 1.5m)
        
        # Base buffer size (larger for unioning) approx 30m
        base_buffer = 0.0003 
        
        for n, depth in node_depths.items():
            if depth < 0.05: continue
            
            pt = Point(self.G.nodes[n]['x'], self.G.nodes[n]['y'])
            poly = pt.buffer(base_buffer + (depth * 0.00005)) # slightly larger for deep nodes
            
            if depth > 1.5:
                level3_geoms.append(poly)
                level2_geoms.append(poly) # Layering approach: Deep also exists in Med/Shallow layers?
                level1_geoms.append(poly) # No, let's keep them separate or stacked. 
                # Stacked is safer for coverage.
            elif depth > 0.5:
                level2_geoms.append(poly)
                level1_geoms.append(poly)
            else:
                level1_geoms.append(poly)
                
        features = []
        
        # Union and create features
        # Level 1 (Base Shallow Layer)
        if level1_geoms:
            l1_poly = unary_union(level1_geoms)
            if l1_poly.geom_type == 'Polygon': l1_poly = MultiPolygon([l1_poly])
            features.append({'geometry': l1_poly, 'intensity': 0.2})
            
        # Level 2 (Mid Layer)
        if level2_geoms:
            l2_poly = unary_union(level2_geoms)
            if l2_poly.geom_type == 'Polygon': l2_poly = MultiPolygon([l2_poly])
            features.append({'geometry': l2_poly, 'intensity': 0.6})
            
        # Level 3 (Deep Layer - Top)
        if level3_geoms:
            l3_poly = unary_union(level3_geoms)
            if l3_poly.geom_type == 'Polygon': l3_poly = MultiPolygon([l3_poly])
            features.append({'geometry': l3_poly, 'intensity': 1.0})
            
        if not features:
            flood_gdf = gpd.GeoDataFrame(columns=['geometry', 'intensity'], crs=self.G.graph['crs'])
        else:
            flood_gdf = gpd.GeoDataFrame(features, crs=self.G.graph['crs'])

        # --- Flooded roads layer (absolute depth thresholds) ---
        road_geoms, road_risks, road_depths = [], [], []

        for u, v, k, data in self.G.edges(keys=True, data=True):
            u_depth = node_depths.get(u, 0.0)
            v_depth = node_depths.get(v, 0.0)
            avg_depth_m = (u_depth + v_depth) / 2.0
            avg_depth_cm = avg_depth_m * 100.0

            if avg_depth_cm > 5.0:  # Only show roads with > 5cm water
                if 'geometry' in data:
                    geom = data['geometry']
                else:
                    geom = LineString([
                        (self.G.nodes[u]['x'], self.G.nodes[u]['y']),
                        (self.G.nodes[v]['x'], self.G.nodes[v]['y'])
                    ])

                road_geoms.append(geom)
                road_depths.append(round(avg_depth_cm, 1))

                # Absolute thresholds — not relative — so colors spread meaningfully
                if avg_depth_cm < 20.0:
                    road_risks.append('low')     # green  — passable
                elif avg_depth_cm < 50.0:
                    road_risks.append('medium')  # yellow — caution
                else:
                    road_risks.append('high')    # red    — dangerous

        if road_geoms:
            roads_gdf = gpd.GeoDataFrame({
                'geometry': road_geoms,
                'risk': road_risks,
                'depth_cm': road_depths
            }, crs=self.G.graph['crs'])
        else:
            roads_gdf = gpd.GeoDataFrame(
                columns=['geometry', 'risk', 'depth_cm'],
                crs=self.G.graph['crs']
            )

        return {
            'flood_gdf': flood_gdf,
            'roads_gdf': roads_gdf
        }
