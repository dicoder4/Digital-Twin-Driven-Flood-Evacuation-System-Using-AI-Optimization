import { Source, Layer } from 'react-map-gl/maplibre';

export default function SimulateRouteLayer({ routeData, routeHistory }) {
  if (!routeData?.route_geojson) return null;

  return (
    <>
      {/* Route history — faded grey lines */}
      {routeHistory.map((r, i) => (
        <Source key={`history-${i}`} id={`history-${i}`} type="geojson" data={r.geojson}>
          <Layer
            id={`history-line-${i}`}
            type="line"
            paint={{
              'line-color': '#9ca3af',
              'line-width': 2,
              'line-opacity': 0.15 + (i / (routeHistory.length + 1)) * 0.25,
              'line-dasharray': [4, 3],
            }}
          />
        </Source>
      ))}

      {/* Current route — flood-risk colour-coded */}
      <Source id="simulate-route" type="geojson" data={routeData.route_geojson}>
        <Layer
          id="simulate-route-glow"
          type="line"
          paint={{
            'line-color': '#3b82f6',
            'line-width': 8,
            'line-opacity': 0.2,
            'line-blur': 4,
          }}
        />
        <Layer
          id="simulate-route-line"
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
          }}
        />
      </Source>
    </>
  );
}
