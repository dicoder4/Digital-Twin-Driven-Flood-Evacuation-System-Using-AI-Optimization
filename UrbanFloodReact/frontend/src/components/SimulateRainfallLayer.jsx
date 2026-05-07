import { Source, Layer } from 'react-map-gl/maplibre';

export default function SimulateRainfallLayer({ heatmap }) {
  if (!heatmap || heatmap.length === 0) return null;

  const geojson = {
    type: 'FeatureCollection',
    features: heatmap.map(h => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
      properties: { intensity: h.intensity, hobli: h.hobli }
    }))
  };

  return (
    <Source id="rainfall-heat" type="geojson" data={geojson}>
      <Layer
        id="rainfall-heatmap"
        type="heatmap"
        paint={{
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'intensity'], 0, 0, 1, 1],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 10, 1, 15, 3],
          'heatmap-color': [
            'interpolate',
            ['linear'],
            ['heatmap-density'],
            0, 'rgba(0,0,255,0)',
            0.2, 'rgba(100,150,255,0.3)',
            0.5, 'rgba(255,165,0,0.5)',
            0.8, 'rgba(255,50,0,0.7)',
            1.0, 'rgba(139,0,0,0.9)'
          ],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 10, 30, 15, 80],
          'heatmap-opacity': 0.6
        }}
      />
    </Source>
  );
}
