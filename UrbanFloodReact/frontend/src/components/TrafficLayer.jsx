/**
 * TrafficLayer.jsx
 * ─────────────────
 * Places 🚦 traffic signal markers at the midpoint of road segments
 * that received real-time congestion data from Google.
 *
 * Only shows congested roads (congestion_factor >= 1.2).
 * Labels: Heavy (>2×) | Moderate (1.2–2×)
 * Free-flow roads are intentionally hidden — no clutter for normal traffic.
 */
import { useMemo } from 'react';
import { Marker } from 'react-map-gl/maplibre';

function congestionLabel(factor) {
    if (factor >= 2.0) return { label: 'Heavy', cls: 'traffic-pin-heavy' };
    if (factor >= 1.2) return { label: 'Moderate', cls: 'traffic-pin-moderate' };
    return null; // free flow — skip
}

export function TrafficLayer({ trafficRoadsData }) {
    const markers = useMemo(() => {
        if (!trafficRoadsData?.features?.length) return [];

        return trafficRoadsData.features
            .map((f, idx) => {
                const factor = f.properties?.congestion_factor ?? 1.0;
                const info = congestionLabel(factor);
                if (!info) return null;

                // Use midpoint of the edge [lon, lat]
                const coords = f.geometry?.coordinates;
                if (!coords || coords.length < 2) return null;
                const mid = Math.floor(coords.length / 2);
                const [lon, lat] = coords[mid];

                return { idx, lon, lat, ...info };
            })
            .filter(Boolean);
    }, [trafficRoadsData]);

    if (!markers.length) return null;

    return markers.map(({ idx, lon, lat, label, cls }) => (
        <Marker key={`traffic-${idx}`} longitude={lon} latitude={lat} anchor="center">
            <div className={`traffic-pin ${cls}`}>
                <span className="traffic-pin-icon">🚦</span>
                <span className="traffic-pin-label">{label}</span>
            </div>
        </Marker>
    ));
}
