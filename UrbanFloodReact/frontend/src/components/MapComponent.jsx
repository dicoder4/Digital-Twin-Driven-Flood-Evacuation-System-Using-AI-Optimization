import React from 'react';
import Map, { Source, Layer, NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

export default function MapComponent({
  viewState, onMove, onMapClick, mapRef, routeData, routeHistory,
  heatmap, personPos, speedMode, children
}) {
  return (
    <Map
      {...viewState}
      onMove={e => onMove(e.viewState)}
      onClick={e => onMapClick && onMapClick({ lat: e.lngLat.lat, lon: e.lngLat.lng })}
      style={{ width: '100%', height: '100%' }}
      mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
      ref={mapRef}
    >
      <NavigationControl position="top-right" />

      {/* Route history — faded grey lines */}
      {routeHistory && routeHistory.map((r, i) => (
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
      {routeData != null && routeData.route_geojson != null && (
        <Source id="citizen-route" type="geojson" data={routeData.route_geojson}>
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
      )}

      {/* Rainfall heatmap */}
      {heatmap != null && heatmap.length > 0 && (
        <Source id="rainfall-heatmap" type="geojson" data={{ type: 'FeatureCollection', features: heatmap }}>
          <Layer
            id="rainfall-heatmap-layer"
            type="heatmap"
            paint={{
              'heatmap-weight': ['interpolate', ['linear'], ['get', 'intensity'], 0, 0, 1, 1],
              'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 9, 3],
              'heatmap-color': [
                'interpolate',
                ['linear'],
                ['heatmap-density'],
                0, 'rgba(0, 0, 255, 0)',
                0.2, '#87ceeb',
                0.4, '#4169e1',
                0.6, '#1e90ff',
                0.8, '#0000cd',
                1, '#00008b'
              ],
              'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 2, 9, 20],
              'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 7, 1, 9, 0.8]
            }}
          />
        </Source>
      )}

      {/* Person position marker */}
      {personPos != null && (
        <Marker longitude={personPos.lon} latitude={personPos.lat} anchor="bottom">
          <div style={{
            width: '32px',
            height: '32px',
            background: '#3b82f6',
            borderRadius: '50%',
            border: '3px solid white',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '18px'
          }}>
            👤
          </div>
        </Marker>
      )}

      {children}
    </Map>
  );
}
