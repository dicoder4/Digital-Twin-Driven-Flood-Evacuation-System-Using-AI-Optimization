import { useMemo } from 'react';
import Map, { Source, Layer, NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapPin, BarChart2 } from 'lucide-react';
import { Legend } from './Legend';
import { PeopleLayer } from './PeopleLayer';
import { ShelterLayer } from './ShelterLayer';
import { EvacuationLayer } from './EvacuationLayer';
import { TrafficLayer } from './TrafficLayer';


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

// Flood area fill — Premium high-fidelity palette
const FLOOD_FILL_PAINT = {
    'fill-color': [
        'interpolate', ['linear'], ['coalesce', ['get', 'intensity'], 0.2],
        0.2, 'rgba(59, 130, 246, 0.75)', // Shallow Blue
        0.6, 'rgba(11, 146, 243, 0.45)',  // Moderate Blue
        1.0, 'rgba(2, 45, 125, 0.85)',    // Deep Navy (High Intensity)
    ],
    'fill-outline-color': 'rgba(30, 58, 138, 0.45)',
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

export function FloodMap({ viewState, onMove, baseRoadsData, floodData, riskRoadsData, loadedHobli, selRec, populationCount, onUnsafeCount, shelters, evacuationPlan, simulationDone, selectedShelter, trafficRoadsData, showTraffic, showTrafficPins, onToggleTrafficPins, busManifest }) {
    const hasFlood = !!(floodData?.features?.length);
    const hasRisk = !!(riskRoadsData?.features?.length);
    const hasTrafficData = showTraffic && !!(trafficRoadsData?.features?.length);

    const busGeoJSON = useMemo(() => {
        if (!busManifest?.manifest) return null;
        return {
            type: 'FeatureCollection',
            features: busManifest.manifest.map(bus => ({
                type: 'Feature',
                geometry: {
                    type: 'LineString',
                    coordinates: bus.path_points
                },
                properties: {
                    bus_id: bus.bus_id,
                    route_name: bus.route_name
                }
            }))
        };
    }, [busManifest]);

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

                {/* 2. Traffic signal pins — only when toggled ON */}
                {hasTrafficData && showTrafficPins && <TrafficLayer trafficRoadsData={trafficRoadsData} />}

                {/* 3. People dots on roads (above roads, below flood) */}
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

                {/* 6. Evacuation paths */}
                {simulationDone && (
                    <EvacuationLayer
                        evacuationPlan={evacuationPlan}
                        selectedShelterId={selectedShelter?.id || null}
                    />
                )}

                {/* 6.5 Bus paths */}
                {busGeoJSON && (
                    <Source id="bus-routes" type="geojson" data={busGeoJSON}>
                        <Layer
                            id="bus-routes-layer"
                            type="line"
                            paint={{
                                'line-color': '#f59e0b', /* Amber */
                                'line-width': 4.5,
                                'line-opacity': 0.9,
                                'line-dasharray': [2, 1]
                            }}
                        />
                    </Source>
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

            {/* Live Traffic UI — functions as both status AND control */}
            {hasTrafficData && (
                <button
                    className={`map-traffic-toggle ${showTrafficPins ? 'map-traffic-toggle--on' : ''}`}
                    onClick={onToggleTrafficPins}
                    title={showTrafficPins ? 'Hide traffic signal indicators' : 'Show traffic signal indicators'}
                >
                    🚦 {showTrafficPins ? 'Hide Traffic' : 'Show Traffic'}
                </button>
            )}

            {/* Legend */}
            <Legend visible={hasFlood || hasRisk} showTraffic={showTraffic} />
        </main>
    );
}
