import { Marker } from 'react-map-gl/maplibre';

export default function PersonMarker({ pos, speedMode }) {
  if (!pos) return null;

  const emoji = speedMode === 'walk' ? '🚶' : speedMode === 'emergency' ? '🚨' : '🚗';

  return (
    <Marker longitude={pos.lon} latitude={pos.lat}>
      <div style={{ fontSize: '28px', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))' }}>
        {emoji}
      </div>
    </Marker>
  );
}
