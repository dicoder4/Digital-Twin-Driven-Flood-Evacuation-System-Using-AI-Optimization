/**
 * EvacuationLayer.jsx
 * ───────────────────
 * Renders evacuation paths + source citizen pins for a selected shelter.
 * When selectedShelterId is set:
 *   - Purple route lines from source → shelter (flood-aware path)
 *   - Person 🧍 pin at each source node labeled "Citizen N (X people)"
 * When null, renders nothing (routes revealed on sidebar click).
 */
import { useMemo } from 'react';
import { Source, Layer, Marker } from 'react-map-gl/maplibre';

export function EvacuationLayer({ evacuationPlan, selectedShelterId }) {
    const filtered = useMemo(() => {
        if (!evacuationPlan || evacuationPlan.length === 0 || !selectedShelterId) return [];
        return evacuationPlan.filter(move => move.to_shelter === selectedShelterId);
    }, [evacuationPlan, selectedShelterId]);

    const geojson = useMemo(() => {
        const features = filtered.map((move, idx) => ({
            type: 'Feature',
            geometry: {
                type: 'LineString',
                coordinates: move.path,
            },
            properties: { id: idx, pop: move.pop },
        }));
        return { type: 'FeatureCollection', features };
    }, [filtered]);

    if (!selectedShelterId || filtered.length === 0) return null;

    const linePaint = {
        'line-color': '#a855f7',
        'line-width': [
            'interpolate', ['linear'], ['get', 'pop'],
            1, 2.5, 50, 5, 200, 8,
        ],
        'line-opacity': 0.9,
    };

    const glowPaint = {
        'line-color': '#c084fc',
        'line-width': ['interpolate', ['linear'], ['get', 'pop'], 1, 6, 50, 12, 200, 18],
        'line-opacity': 0.2,
        'line-blur': 4,
    };

    return (
        <>
            {/* Route lines */}
            <Source id="evacuation-source" type="geojson" data={geojson}>
                <Layer id="evacuation-glow" type="line" paint={glowPaint}
                    layout={{ 'line-cap': 'round', 'line-join': 'round' }} />
                <Layer id="evacuation-lines" type="line" paint={linePaint}
                    layout={{ 'line-cap': 'round', 'line-join': 'round' }} />
            </Source>

            {/* Citizen source pins — one per route group */}
            {filtered.map((move, idx) => {
                const [lon, lat] = move.path[0];  // first coord = origin node
                return (
                    <Marker key={`citizen-${idx}`} longitude={lon} latitude={lat} anchor="bottom">
                        <div className="evac-citizen-pin">
                            <div className="evac-citizen-icon">🧍</div>
                            <div className="evac-citizen-label">
                                Citizen {idx + 1}
                                <span className="evac-citizen-pop">({move.pop}p)</span>
                            </div>
                        </div>
                    </Marker>
                );
            })}
        </>
    );
}
