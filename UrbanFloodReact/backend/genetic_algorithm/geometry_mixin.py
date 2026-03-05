import networkx as nx

class GeometryMixin:
    def _find_nearest_node_robust(self, lat, lon):
        """
        3-strategy fallback to always resolve a (lat, lon) to a valid graph node.
        Ported from find_nearest_node_robust() in the old evacuation_algorithms.py.

        Strategy 1: ox.distance.nearest_nodes (fast BallTree spatial index)
        Strategy 2: manual Euclidean brute-force over all nodes
        Strategy 3: first node in graph (last resort)
        """
        import osmnx as ox
        try:
            # OSMnx uses (X=lon, Y=lat) ordering
            return ox.distance.nearest_nodes(self.G, lon, lat)
        except Exception:
            pass
        try:
            min_dist = float('inf')
            nearest = None
            for node, data in self.G.nodes(data=True):
                if 'x' in data and 'y' in data:
                    dist = ((lon - data['x']) ** 2 + (lat - data['y']) ** 2) ** 0.5
                    if dist < min_dist:
                        min_dist = dist
                        nearest = node
            if nearest is not None:
                return nearest
        except Exception:
            pass
        # Last resort: return the first node in the graph
        return next(iter(self.G.nodes()))

    def _path_to_coords(self, path_nodes):
        """
        Convert a list of node IDs into [lon, lat] coordinate pairs that follow
        the actual road curvature stored in OSMnx edge geometry attributes.

        OSMnx stores road curves as a Shapely LineString on each edge
        (G[u][v][key]['geometry']).  Using only node coordinates (intersections)
        loses all intermediate waypoints, making curved/diagonal roads appear
        as straight lines on the map.
        """
        coords = []
        for k in range(len(path_nodes) - 1):
            u, v = path_nodes[k], path_nodes[k + 1]

            # OSMnx uses MultiDiGraph: G[u][v] = {0: {edge_data}, 1: ...}
            edge_dict = self.G.get_edge_data(u, v)
            if edge_dict is None:
                # Defensive: no edge found, use straight node-to-node segment
                if k == 0:
                    coords.append([self.G.nodes[u]['x'], self.G.nodes[u]['y']])
                coords.append([self.G.nodes[v]['x'], self.G.nodes[v]['y']])
                continue

            # Pick the parallel edge with the shortest length (matches Dijkstra)
            if isinstance(next(iter(edge_dict.values())), dict):
                best = min(edge_dict.values(),
                           key=lambda d: d.get('length', float('inf')))
            else:
                best = edge_dict

            geom = best.get('geometry')  # Shapely LineString or None
            if geom is not None:
                seg = [[c[0], c[1]] for c in geom.coords]
            else:
                # No geometry stored — straight line between the two nodes
                seg = [
                    [self.G.nodes[u]['x'], self.G.nodes[u]['y']],
                    [self.G.nodes[v]['x'], self.G.nodes[v]['y']],
                ]

            if k == 0:
                coords.extend(seg)          # include the start node
            else:
                coords.extend(seg[1:])      # skip duplicate junction point

        # Edge case: single-node path (origin == destination)
        if not coords and path_nodes:
            n = path_nodes[0]
            coords = [[self.G.nodes[n]['x'], self.G.nodes[n]['y']]]

        return coords

    def _decode(self, chromosome):
        results = []
        for i, j in enumerate(chromosome):
            node_info = self.at_risk_nodes[i]
            shelter   = self.safe_shelters[j]
            pop       = node_info['pop']
            node_id   = node_info['id']

            # Straight-line — only kept if all snapping + pathfinding fails
            path_coords = [
                [node_info['lon'], node_info['lat']],
                [shelter['lon'],   shelter['lat']],
            ]
            fallback = True

            # ── Resolve at-risk node ──────────────────────────────────────────
            # at_risk node_id is already a graph node, but guard against stale copies
            if not self.G.has_node(node_id):
                node_id = self._find_nearest_node_robust(node_info['lat'], node_info['lon'])
                print(f"  [DECODE] at-risk node snapped to {node_id} via nearest-node lookup")

            # ── Resolve shelter node ─────────────────────────────────────────
            # This is the primary cause of straight-line routes: shelter.node_id
            # is None or belongs to a different graph copy.
            shelter_node = shelter.get('node_id')
            if shelter_node is None or not self.G.has_node(shelter_node):
                shelter_node = self._find_nearest_node_robust(shelter['lat'], shelter['lon'])
                print(f"  [DECODE] shelter '{shelter['id']}' snapped to node {shelter_node} via lat/lon")

            # ── Path geometry via flood-aware shortest path ───────────────────
            try:
                path_nodes = nx.shortest_path(
                    self.G, node_id, shelter_node, weight='flood_weight'
                )
                # Extract full road geometry (edge waypoints), not just node coords.
                # This prevents diagonal/curved roads from appearing as straight lines.
                path_coords = self._path_to_coords(path_nodes)
                fallback = False
            except Exception as e:
                # Truly disconnected — keep straight-line and flag it
                print(f"  [DECODE] no road path from {node_id} to {shelter_node}: {e}")

            results.append({
                'from_node':  node_info['id'],
                'to_shelter': shelter['id'],
                'pop':        pop,
                'path':       path_coords,
                'fallback':   fallback,   # True = straight-line (disconnected nodes)
            })
        return results
