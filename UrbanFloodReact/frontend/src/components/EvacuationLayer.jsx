/**
 * EvacuationLayer.jsx
 * ───────────────────
 * Renders evacuation paths + source citizen pins for a selected shelter.
 *   - Purple route lines: road-following paths (flood-aware shortest path)
 *   - Dashed orange lines: fallback straight-line routes (node unreachable on graph)
 *   - Person 🧍 pin at each source node
 */
import { useMemo } from 'react';
import { Source, Layer, Marker } from 'react-map-gl/maplibre';

export function EvacuationLayer({ evacuationPlan, selectedShelterId }) {
    const filtered = useMemo(() => {
        if (!evacuationPlan || evacuationPlan.length === 0 || !selectedShelterId) return [];
        return evacuationPlan.filter(move => move.to_shelter === selectedShelterId);
    }, [evacuationPlan, selectedShelterId]);

    // Split into road-following (normal) and straight-line (fallback) routes
    const realRoutes = useMemo(() =>
        filtered.filter(m => !m.fallback), [filtered]);
    const fallbackRoutes = useMemo(() =>
        filtered.filter(m => m.fallback), [filtered]);

    const toGeojson = (routes) => ({
        type: 'FeatureCollection',
        features: routes.map((move, idx) => ({
            type: 'Feature',
            geometry: { type: 'LineString', coordinates: move.path },
            properties: { id: idx, pop: move.pop },
        })),
    });

    const realGeojson = useMemo(() => toGeojson(realRoutes), [realRoutes]);
    const fallbackGeojson = useMemo(() => toGeojson(fallbackRoutes), [fallbackRoutes]);

    if (!selectedShelterId || filtered.length === 0) return null;

    // ── Paint styles ────────────────────────────────────────────────────────
    const linePaint = {
        'line-color': '#a855f7',
        'line-width': ['interpolate', ['linear'], ['get', 'pop'], 1, 2.5, 50, 5, 200, 8],
        'line-opacity': 0.9,
    };
    const glowPaint = {
        'line-color': '#c084fc',
        'line-width': ['interpolate', ['linear'], ['get', 'pop'], 1, 6, 50, 12, 200, 18],
        'line-opacity': 0.2,
        'line-blur': 4,
    };
    // Fallback: thin dashed orange — visually distinct, clearly a straight line
    const fallbackPaint = {
        'line-color': '#f97316',
        'line-width': 1.5,
        'line-opacity': 0.7,
        'line-dasharray': [4, 3],
    };

    return (
        <>
            {/* Normal road-following routes (purple) */}
            {realRoutes.length > 0 && (
                <Source id="evacuation-source" type="geojson" data={realGeojson}>
                    <Layer id="evacuation-glow" type="line" paint={glowPaint}
                        layout={{ 'line-cap': 'round', 'line-join': 'round' }} />
                    <Layer id="evacuation-lines" type="line" paint={linePaint}
                        layout={{ 'line-cap': 'round', 'line-join': 'round' }} />
                </Source>
            )}

            {/* Fallback straight-line routes (dashed orange) */}
            {fallbackRoutes.length > 0 && (
                <Source id="evacuation-fallback-source" type="geojson" data={fallbackGeojson}>
                    <Layer id="evacuation-fallback" type="line" paint={fallbackPaint}
                        layout={{ 'line-cap': 'butt', 'line-join': 'miter' }} />
                </Source>
            )}

            {/* Citizen source pins — one per route group */}
            {filtered.map((move, idx) => {
                const [lon, lat] = move.path[0];
                return (
                    <Marker key={`citizen-${idx}`} longitude={lon} latitude={lat} anchor="bottom">
                        <div className="evac-citizen-pin">
                            <div className="evac-citizen-icon">🧍</div>
                            <div className="evac-citizen-label">
                                Citizen {idx + 1}
                                <span className="evac-citizen-pop">({move.pop}p)</span>
                                {move.fallback && (
                                    <span className="evac-citizen-fallback" title="No road path found">⚠️</span>
                                )}
                            </div>
                        </div>
                    </Marker>
                );
            })}
        </>
    );
}
