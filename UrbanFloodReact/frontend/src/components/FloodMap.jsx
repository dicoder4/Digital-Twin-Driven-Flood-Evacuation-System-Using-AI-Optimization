/**
 * FloodMap.jsx
 * MapLibre map with:
 *   - Light CartoDB Positron basemap (GMaps-like)
 *   - Base road network layer (thin gray)
 *   - Flood area polygons (teal, intensity-mapped opacity)
 *   - Flood risk road overlay (colored by 'risk' field: low/medium/high)
 *   - Legend (bottom-right)
 *   - Hobli info chip (top-left)
 */
import Map, { Source, Layer, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapPin, BarChart2 } from 'lucide-react';
import { Legend } from './Legend';

// Road risk → colour
const RISK_COLOUR = {
    low: '#22c55e',
    medium: '#f59e0b',
    high: '#ef4444',
};

// Base road network (before simulation)
const BASE_ROAD_PAINT = {
    'line-color': '#94a3b8',
    'line-width': 1.2,
    'line-opacity': 0.65,
};

// Flood area fill (uses 'intensity': 0–1 from flood_gdf)
const FLOOD_FILL_PAINT = {
    'fill-color': [
        'interpolate', ['linear'], ['coalesce', ['get', 'intensity'], 0.2],
        0.2, 'rgba(56,189,248,0.35)',
        0.6, 'rgba(14,165,233,0.55)',
        1.0, 'rgba(2,132,199,0.75)',
    ],
    'fill-outline-color': 'rgba(14,165,233,0.5)',
};

// Flooded roads: colour from `risk` field
const RISK_ROAD_PAINT = {
    'line-color': [
        'match', ['get', 'risk'],
        'low', RISK_COLOUR.low,
        'medium', RISK_COLOUR.medium,
        'high', RISK_COLOUR.high,
        '#94a3b8',
    ],
    'line-width': 2.5,
    'line-opacity': 0.9,
};

export function FloodMap({ viewState, onMove, baseRoadsData, floodData, riskRoadsData, loadedHobli, selRec }) {
    const hasFlood = !!(floodData?.features?.length);
    const hasRisk = !!(riskRoadsData?.features?.length);

    return (
        <main className="map-container">
            <Map
                {...viewState}
                onMove={e => onMove(e.viewState)}
                style={{ width: '100%', height: '100%' }}
                mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
            >
                <NavigationControl position="top-right" />

                {/* 1. Base road network */}
                {baseRoadsData && (
                    <Source id="base-roads" type="geojson" data={baseRoadsData}>
                        <Layer id="base-roads-layer" type="line" paint={BASE_ROAD_PAINT} />
                    </Source>
                )}

                {/* 2. Flood extent polygons */}
                {hasFlood && (
                    <Source id="flood" type="geojson" data={floodData}>
                        <Layer id="flood-fill" type="fill" paint={FLOOD_FILL_PAINT} />
                    </Source>
                )}

                {/* 3. Risk-coloured roads overlay */}
                {hasRisk && (
                    <Source id="risk-roads" type="geojson" data={riskRoadsData}>
                        <Layer id="risk-roads-layer" type="line" paint={RISK_ROAD_PAINT} />
                    </Source>
                )}
            </Map>

            {/* Floating hobli chip */}
            {loadedHobli && (
                <div className="map-chip">
                    <MapPin size={12} /> {loadedHobli}
                    {selRec && <> · <BarChart2 size={12} /> {selRec.actual_mm} mm</>}
                </div>
            )}

            {/* Legend */}
            <Legend visible={hasFlood || hasRisk} />
        </main>
    );
}
