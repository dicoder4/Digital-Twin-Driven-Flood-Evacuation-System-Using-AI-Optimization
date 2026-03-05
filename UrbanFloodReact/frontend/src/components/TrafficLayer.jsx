/**
 * TrafficLayer.jsx
 * ─────────────────
 * Places 🚦 traffic signal markers at the midpoint of road segments
 * that received real-time congestion data from TomTom.
 *
 * Smart display logic:
 *   - If ANY heavy or moderate roads exist → show only those (suppress clear)
 *   - If ALL roads are clear → show clear pins so user knows data arrived
 */
import { useMemo } from 'react';
import { Marker } from 'react-map-gl/maplibre';

function congestionLabel(factor) {
    if (factor >= 2.0) return { label: 'Heavy',    cls: 'traffic-pin-heavy',    priority: 2 };
    if (factor >= 1.05) return { label: 'Moderate', cls: 'traffic-pin-moderate', priority: 1 };
    return                      { label: 'Clear',   cls: 'traffic-pin-clear',    priority: 0 };
}

export function TrafficLayer({ trafficRoadsData }) {
    const markers = useMemo(() => {
        if (!trafficRoadsData?.features?.length) return [];

        // Build all markers first
        const all = trafficRoadsData.features
            .map((f, idx) => {
                const factor = f.properties?.congestion_factor ?? 1.0;
                const info = congestionLabel(factor);

                const coords = f.geometry?.coordinates;
                if (!coords || coords.length < 2) return null;
                const mid = Math.floor(coords.length / 2);
                const [lon, lat] = coords[mid];

                return { idx, lon, lat, ...info };
            })
            .filter(Boolean);

        // If any heavy or moderate roads exist, suppress clear pins
        const hasCongestion = all.some(m => m.priority > 0);
        return hasCongestion ? all.filter(m => m.priority > 0) : all;

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
