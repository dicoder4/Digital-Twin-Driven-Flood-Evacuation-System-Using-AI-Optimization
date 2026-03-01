import math
import time
import requests
import numpy as np
import networkx as nx

class SetupMixin:
    def _fetch_google_traffic_speed(self, start_coord, end_coord):
        """
        Queries Google Routes API to get real-time speed between two points.
        Returns: duration_in_traffic (s)
        """
        base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.GOOGLE_API_KEY,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters"
        }
        body = {
            "origin": {"location": {"latLng": {"latitude": start_coord[0], "longitude": start_coord[1]}}},
            "destination": {"location": {"latLng": {"latitude": end_coord[0], "longitude": end_coord[1]}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL"
        }
        try:
            print(f"DEBUG: Requesting Google Traffic for {start_coord} -> {end_coord}")
            response = requests.post(base_url, json=body, headers=headers)
            if response.status_code != 200:
                 print(f"DEBUG: Google API Error {response.status_code}: {response.text}")
                 return None
                
            data = response.json()
            if "routes" in data and len(data["routes"]) > 0:
                duration_str = data["routes"][0].get("duration", "0s")
                duration_val = int(duration_str.replace("s", ""))
                print(f"DEBUG: Success! Duration: {duration_val}s")
                return duration_val
            else:
                 print(f"DEBUG: No routes found in response: {data}")
        except Exception as e:
            print(f"DEBUG: Exception during Google API call: {e}")
            return None
        return None

    def _update_graph_with_google_traffic(self):
        """
        Updates 'travel_time' on major roads using Google API.
        Only runs if use_google_traffic=True.
        """
        print("Fetching Google Traffic data (Limited to major roads)...")
        count = 0 
        limit = 50 # Safety limit, increased slightly
        
        for u, v, k, data in self.G.edges(keys=True, data=True):
            highway = data.get('highway', '')
            # Filter for highways/main roads
            if isinstance(highway, list): highway = highway[0]
            
            if highway in ['motorway', 'trunk', 'primary'] and count < limit:
                print(f"DEBUG: Checking traffic for edge {u}->{v} (Highway: {highway})")
                start = (self.G.nodes[u]['y'], self.G.nodes[u]['x'])
                end = (self.G.nodes[v]['y'], self.G.nodes[v]['x'])
                
                duration = self._fetch_google_traffic_speed(start, end)
                if duration:
                    # Store real-time traffic duration
                    self.G[u][v][k]['traffic_time'] = duration
                    count += 1
                
                # Small delay to prevent hitting API rate limits (QPS)
                time.sleep(0.1)
        print(f"Updated {count} road segments with real-time traffic.")
        self._traffic_segment_count = count

    def get_traffic_geojson(self):
        """
        Returns a GeoJSON FeatureCollection of major road edges that received
        real-time traffic data from Google. Each feature has:
          - congestion_factor: actual_time / free_flow_time (1.0 = free, >2 = congested)
          - highway: road type string
        Used by the frontend TrafficLayer to colour-code congested roads.
        """
        features = []
        for u, v, k, data in self.G.edges(keys=True, data=True):
            if 'traffic_time' not in data:
                continue
            ux, uy = self.G.nodes[u]['x'], self.G.nodes[u]['y']
            vx, vy = self.G.nodes[v]['x'], self.G.nodes[v]['y']
            base_len = data.get('length', 1.0)
            free_flow_time = max(0.1, base_len / 13.8)
            congestion_factor = round(min(5.0, data['traffic_time'] / free_flow_time), 2)
            features.append({
                'type': 'Feature',
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[ux, uy], [vx, vy]],
                },
                'properties': {
                    'congestion_factor': congestion_factor,
                    'highway': data.get('highway', 'primary'),
                    'traffic_time': data['traffic_time'],
                },
            })
        return {'type': 'FeatureCollection', 'features': features}

    def _add_flood_edge_weights(self):
        """
        Annotate every edge with 'flood_weight':
            flood_weight = length × (1 + FLOOD_PENALTY_FACTOR × avg_water_depth)
                           × (1 + TRAFFIC_PENALTY IF CONGESTED)
        """
        for u, v, k, data in self.G.edges(keys=True, data=True):
            base_len = data.get('length', 1.0)
            
            # 1. Flood Penalty
            depth_u = self.G.nodes[u].get('water_depth', 0.0)
            depth_v = self.G.nodes[v].get('water_depth', 0.0)
            avg_depth = (depth_u + depth_v) / 2.0
            flood_factor = (1.0 + self.FLOOD_PENALTY_FACTOR * avg_depth)
            
            # 2. Traffic Penalty (Google Data OR Simulation Fallback)
            traffic_factor = 1.0
            
            if 'traffic_time' in data:
                # If we have real data: Factor = Actual Time / Free Flow Time
                # Free flow estimate: length / 13.8m/s (50km/h)
                free_flow_time = max(0.1, base_len / 13.8) # Avoid division by zero
                actual_time = data['traffic_time']
                
                if actual_time > free_flow_time:
                     traffic_factor = min(5.0, actual_time / free_flow_time)
            
            # Combined Weight
            # We multiply length by these factors to make the "effective distance" longer
            # effectively routing around floods AND traffic jams.
            flood_w = max(0.1, base_len * flood_factor * traffic_factor) # Ensure positive weight
            self.G[u][v][k]['flood_weight'] = flood_w   # ← write back so Dijkstra uses it
            

    def _compute_matrices(self):
        """
        For each shelter, run a single-source Dijkstra to all nodes using
        flood_weight. This gives O(S × E log V) precomputation — fast because
        we only do it once before the GA starts.
        """
        for j, shelter in enumerate(self.safe_shelters):
            s_node = shelter.get('node_id')

            if s_node is None or not self.G.has_node(s_node):
                # Fallback: Euclidean in degrees → approximate metres
                for i, node in enumerate(self.at_risk_nodes):
                    d = math.sqrt(
                        (node['lat'] - shelter['lat']) ** 2 +
                        (node['lon'] - shelter['lon']) ** 2
                    ) * 111_000
                    self.dist_matrix[i, j] = d
                    self.time_matrix[i, j] = d / self.WALKING_SPEED_MS
                continue

            try:
                # flood-weighted cost (for fitness)
                flood_lengths = nx.single_source_dijkstra_path_length(
                    self.G, s_node, weight='flood_weight'
                )
                # raw length (for time estimate — we don't slow evacuees by depth,
                # we just make flooded paths more costly to choose)
                raw_lengths = nx.single_source_dijkstra_path_length(
                    self.G, s_node, weight='length'
                )
            except Exception:
                continue

            for i, node in enumerate(self.at_risk_nodes):
                r_node = node['id']
                if r_node in flood_lengths:
                    self.dist_matrix[i, j] = flood_lengths[r_node]
                if r_node in raw_lengths:
                    self.time_matrix[i, j] = raw_lengths[r_node] / self.WALKING_SPEED_MS

    def _compute_greedy_chromosome(self):
        """
        Greedy assignment: each at-risk node gets the nearest reachable shelter
        (by flood-weighted distance). Respects capacity — once a shelter is full,
        the next-nearest is tried or overflow distributed to lowest fill ratio.
        """
        n_shelters = len(self.safe_shelters)
        capacities = [s['capacity'] for s in self.safe_shelters]
        assigned_counts = [0] * n_shelters
        chromosome = []

        for i in range(len(self.at_risk_nodes)):
            pop = self.at_risk_nodes[i]['pop']
            # Sort shelters by flood-weighted distance
            order = np.argsort(self.dist_matrix[i])
            
            chosen = int(order[0])
            best_overflow_j = chosen
            min_ratio = float('inf')

            for j in order:
                j = int(j)
                ratio = (assigned_counts[j] + pop) / max(1.0, capacities[j])
                
                # If there's physical space, take it immediately
                if ratio <= 1.0:
                    chosen = j
                    break
                
                # Otherwise, track the shelter with the least proportional overflow
                if ratio < min_ratio:
                    min_ratio = ratio
                    best_overflow_j = j
            else:
                # Loop exhausted: all shelters are over capacity. 
                # Pick the one with the smallest overflow ratio instead of the absolute nearest.
                chosen = best_overflow_j

            assigned_counts[chosen] += pop
            chromosome.append(chosen)

        return chromosome
