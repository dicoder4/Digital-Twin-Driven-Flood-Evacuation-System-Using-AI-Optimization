/**
 * FloodMap.jsx
 * MapLibre map with:
 *   - Light CartoDB Positron basemap (GMaps-like)
 *   - Base road network layer (thin gray)
 *   - People dots on roads (green → red when flooded)
 *   - Flood area polygons (dark blue, intensity-mapped opacity)
 *   - Flood risk road overlay (colored by 'risk' field: low/medium/high)
 *   - Legend (bottom-right)
 *   - Hobli info chip (top-left)
 */
import Map, { Source, Layer, NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapPin, BarChart2 } from 'lucide-react';
import { Legend } from './Legend';
import { PeopleLayer } from './PeopleLayer';
import { ShelterLayer } from './ShelterLayer';
import { EvacuationLayer } from './EvacuationLayer';

// Road risk → colour
const RISK_COLOUR = {
    low: '#b3e168ff',
    medium: '#f59e0b',
    high: '#ef4444',
};

// Base road network (before simulation)
const BASE_ROAD_PAINT = {
    'line-color': '#94a3b8',
    'line-width': 1.2,
    'line-opacity': 0.65,
};

// Flood area fill — dark blue (distinct from green people dots)
const FLOOD_FILL_PAINT = {
    'fill-color': [
        'interpolate', ['linear'], ['coalesce', ['get', 'intensity'], 0.2],
        0.2, 'rgba(29,78,216,0.35)',
        0.6, 'rgba(30,58,138,0.58)',
        1.0, 'rgba(15,23,79,0.80)',
    ],
    'fill-outline-color': 'rgba(30,58,138,0.6)',
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

export function FloodMap({ viewState, onMove, baseRoadsData, floodData, riskRoadsData, loadedHobli, selRec, populationCount, onUnsafeCount, shelters, evacuationPlan, simulationDone, selectedShelter }) {
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

                {/* 2. People dots on roads (above roads, below flood) */}
                <PeopleLayer
                    baseRoadsData={baseRoadsData}
                    populationCount={populationCount}
                    riskRoadsData={riskRoadsData}
                    hobliName={loadedHobli}
                    onUnsafeCount={onUnsafeCount}
                />

                {/* 3. Flood extent polygons */}
                {hasFlood && (
                    <Source id="flood" type="geojson" data={floodData}>
                        <Layer id="flood-fill" type="fill" paint={FLOOD_FILL_PAINT} />
                    </Source>
                )}

                {/* 4. Risk-coloured roads overlay */}
                {hasRisk && (
                    <Source id="risk-roads" type="geojson" data={riskRoadsData}>
                        <Layer id="risk-roads-layer" type="line" paint={RISK_ROAD_PAINT} />
                    </Source>
                )}

                {/* 5. Shelter markers with built-in hover tooltip */}
                <ShelterLayer shelters={shelters} />

                {/* 6. Evacuation paths — only for selected shelter, shown when simulation done */}
                {simulationDone && (
                    <EvacuationLayer
                        evacuationPlan={evacuationPlan}
                        selectedShelterId={selectedShelter?.id || null}
                    />
                )}

                {/* 7. Destination pin for selected shelter */}
                {simulationDone && selectedShelter && (
                    <Marker
                        longitude={selectedShelter.lon}
                        latitude={selectedShelter.lat}
                        anchor="bottom"
                    >
                        <div className="evac-dest-pin">
                            <MapPin size={22} fill="#a855f7" color="white" strokeWidth={1.5} />
                            <div className="evac-dest-label">{selectedShelter.name}</div>
                        </div>
                    </Marker>
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
