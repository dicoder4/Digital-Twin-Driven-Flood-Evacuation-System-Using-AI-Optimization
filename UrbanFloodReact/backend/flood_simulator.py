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
    Storm-water drain influence reduces/increases water depth per step
    based on drain proximity, capacity, and condition.
    """
    def __init__(self, G, drain_nodes=None, lake_nodes=None, stormwater_drains=None):
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
        # New attribute for progressive rainfall
        self.rainfall_per_step_m = 0.0

        # ── Storm-water drain integration ────────────────────────────────
        # stormwater_drains: list of DrainSegment dicts from drain_data.py
        self.stormwater_drains = stormwater_drains or []
        self._drain_influence_summary = {}   # populated by set_drain_influence()
        self._drain_influence_active = False

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

    def set_progressive_rainfall(self, total_rainfall_mm: float, steps: int):
        """Set up progressive rainfall over the given steps."""
        self.rainfall_per_step_m = total_rainfall_mm / steps / 1000.0
        # Reset water depths to zero
        nx.set_node_attributes(self.G, 0.0, 'water_depth')
        print(f"  [flood_sim] Progressive rainfall: {total_rainfall_mm} mm over {steps} steps, "
              f"{self.rainfall_per_step_m*1000:.2f} mm per step")

    def set_drain_influence(self, influence_summary: dict):
        """
        Activate storm-water drain influence on flood propagation.

        ``influence_summary`` is the return value of
        ``drain_data.compute_drain_influence_metrics()`` which has already
        set per-node attributes (drainage_capacity, ponding_risk, etc.)
        on ``self.G``.
        """
        self._drain_influence_summary = influence_summary
        self._drain_influence_active = influence_summary.get("nodes_influenced", 0) > 0
        n_drains = influence_summary.get("drain_count", 0)
        n_infl = influence_summary.get("nodes_influenced", 0)
        print(f"  [flood_sim] Drain influence {'ACTIVE' if self._drain_influence_active else 'INACTIVE'}: "
              f"{n_drains} drains, {n_infl} nodes influenced")

    def _apply_drain_influence(self, current_depths: dict):
        """
        Modify water depths based on storm-water drain proximity and condition.

        For each node with ``drainage_capacity > 0``:
          - Functioning drains: remove water proportional to capacity factor,
            proximity, and slope toward the drain.
          - Blocked / overflowing drains (ponding_risk > 0.6): *add* a small
            overflow contribution representing back-flow from clogged channels.

        Physical justification:
          A 1.5 m wide × 1 m deep open channel under gravity flow can carry
          roughly 1.5 m³/s (Manning's eq with n=0.015, slope=0.001). Over a
          5-second computational sub-step this drains ~7.5 m³, equivalent to
          reducing the water column by ~0.005 m over a 50 m × 30 m cell.
          The ``drainage_capacity`` factor (0–0.3) already encodes proximity
          decay, condition, and elevation, so we apply it directly as a
          fractional removal per step.
        """
        if not self._drain_influence_active:
            return

        drained_total = 0.0
        overflow_total = 0.0

        for node in self.G.nodes():
            depth = current_depths.get(node, 0.0)
            if depth <= 0.0:
                continue

            cap = self.G.nodes[node].get("drainage_capacity", 0.0)
            ponding = self.G.nodes[node].get("ponding_risk", 0.5)

            if cap > 0:
                # ── Functioning drain nearby: remove water ───────────────
                # Scale removal by current depth so drains are more effective
                # in shallow water (realistic: drains struggle with deep inundation).
                depth_factor = min(1.0, 0.3 / max(depth, 0.01))
                removal = depth * cap * depth_factor
                removal = min(removal, depth)  # never go negative
                current_depths[node] = depth - removal
                drained_total += removal

            if ponding > 0.6:
                # ── Blocked drain overflow: add water ────────────────────
                # Small overflow contribution from clogged channels backing up.
                overflow = self.rainfall_per_step_m * (ponding - 0.5) * 0.15
                current_depths[node] = current_depths.get(node, 0.0) + overflow
                overflow_total += overflow

    def propagate_flood_step(self, decay_factor=0.5):
        # 1. Add incremental rainfall
        if self.rainfall_per_step_m > 0:
            for node in self.G.nodes:
                self.G.nodes[node]['water_depth'] = self.G.nodes[node].get('water_depth', 0.0) + self.rainfall_per_step_m

        # 1b. Apply storm-water drain influence (removes/adds water)
        if self._drain_influence_active:
            pre_drain_depths = nx.get_node_attributes(self.G, 'water_depth')
            self._apply_drain_influence(pre_drain_depths)
            nx.set_node_attributes(self.G, pre_drain_depths, 'water_depth')

        # 2. Existing propagation logic (unchanged)
        current_depths = nx.get_node_attributes(self.G, 'water_depth')
        elevations = nx.get_node_attributes(self.G, 'elevation')
        if not elevations:
            elevations = {n: 0.0 for n in self.G.nodes()}
        for n in self.G.nodes():
            if n not in elevations:
                elevations[n] = 0.0

        depth_transfers = {n: 0.0 for n in self.G.nodes()}
        for node in self.G.nodes():
            if node not in current_depths:
                continue
            water_depth = current_depths[node]
            if water_depth <= 0.005:  # Lower surface retention threshold to 5mm to support light rains
                continue
            node_head = elevations[node] + water_depth
            neighbors = list(self.G.neighbors(node))
            lower_head_neighbors = []
            total_head_diff = 0
            for n in neighbors:
                n_elev = elevations.get(n, 0.0)
                n_water = current_depths.get(n, 0.0)
                n_head = n_elev + n_water
                if n_head < node_head:
                    head_diff = node_head - n_head
                    lower_head_neighbors.append((n, head_diff))
                    total_head_diff += head_diff
            if not lower_head_neighbors:
                continue
            flow_out = water_depth * decay_factor
            total_outflow = 0.0
            per_neighbour = []
            for n, diff in lower_head_neighbors:
                fraction = diff / total_head_diff
                n_elev = elevations.get(n, 0.0)
                node_elev = elevations.get(node, 0.0)
                slope_factor = 1.0 + min(abs(node_elev - n_elev) / 10.0, 2.0)
                edge_data = self.G.get_edge_data(node, n, default={})
                if isinstance(edge_data, dict) and 0 in edge_data:
                    edge_data = edge_data[0]
                efficiency = edge_data.get('flow_efficiency', 1.0)
                amount = flow_out * fraction * slope_factor * efficiency
                per_neighbour.append((n, amount))
                total_outflow += amount
            scale = min(1.0, water_depth / total_outflow) if total_outflow > 0 else 1.0
            for n, amount in per_neighbour:
                scaled_amount = amount * scale
                depth_transfers[node] -= scaled_amount
                depth_transfers[n] += scaled_amount
        for n, delta in depth_transfers.items():
            new_depth = max(0.0, current_depths.get(n, 0.0) + delta)
            current_depths[n] = new_depth
            
            # --- NEW: Track historical max depth ---
            prev_max = self.G.nodes[n].get('max_water_depth', 0.0)
            if new_depth > prev_max:
                self.G.nodes[n]['max_water_depth'] = new_depth

        nx.set_node_attributes(self.G, current_depths, 'water_depth')
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
        Identify nodes where max historical water depth > threshold and there are people present.
        Returns a list of (node_id, population)
        """
        at_risk = []
        for n in self.G.nodes():
            current_depth = self.G.nodes[n].get('water_depth', 0.0)
            max_depth = max(self.G.nodes[n].get('max_water_depth', 0.0), current_depth)
            
            pop = self.node_populations.get(n, 0)
            if max_depth > depth_threshold_m and pop > 0:
                at_risk.append((n, pop))
        return at_risk

    def calculate_flood_impact(self):
        """
        Calculate flood impact. Returns 3 tiered MultiPolygons for Low, Medium, High depth.
        This allows cleaner "polygon" visualization than thousands of circles.
        """
        node_depths = nx.get_node_attributes(self.G, 'water_depth')
        
        # Buckets for levels
        level1_geoms = [] # Shallow (0.005m - 0.5m)
        level2_geoms = [] # Moderate (0.5m - 1.5m)
        level3_geoms = [] # Deep (> 1.5m)
        
        # Base buffer size (larger for unioning) approx 30m
        base_buffer = 0.0003 
        
        for n, depth in node_depths.items():
            if depth < 0.005: continue  # Render anything above 5mm
            
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
        road_geoms, road_risks, road_depths, road_hashes = [], [], [], []

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
                road_hashes.append((u, v)) # store for node id extraction

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
                'depth_cm': road_depths,
                'u_id': [h[0] for h in road_hashes],
                'v_id': [h[1] for h in road_hashes]
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
