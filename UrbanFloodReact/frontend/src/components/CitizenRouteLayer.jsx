import { Source, Layer } from 'react-map-gl/maplibre';

export default function CitizenRouteLayer({ routeData }) {
  if (!routeData?.route_geojson) return null;

  const geojson = routeData.route_geojson;

  return (
    <Source id="citizen-route" type="geojson" data={geojson}>
      <Layer
        id="citizen-route-glow"
        type="line"
        paint={{
          'line-color': '#3b82f6',
          'line-width': 8,
          'line-opacity': 0.2,
          'line-blur': 4,
        }}
      />
      <Layer
        id="citizen-route-line"
        type="line"
        paint={{
          'line-color': [
            'match',
            ['get', 'flood_risk'],
            'high', '#ef4444',
            'medium', '#f59e0b',
            'low', '#22c55e',
            '#6366f1'
          ],
          'line-width': 4,
          'line-opacity': 0.9,
          'line-dasharray': [
            'case',
            ['==', ['get', 'flood_risk'], 'high'],
            ['literal', [3, 2]],
            ['literal', [1, 0]]
          ],
        }}
      />
    </Source>
  );
}
