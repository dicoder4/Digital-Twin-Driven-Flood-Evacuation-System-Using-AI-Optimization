import { useMemo, useCallback } from 'react';
import Map, { Source, Layer, NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapPin, BarChart2, Train, Activity } from 'lucide-react';
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
        0.2, 'rgba(175, 202, 249, 0.75)', // Shallow Blue
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

export function FloodMap({
    viewState, onMove, baseRoadsData, floodData, riskRoadsData,
    loadedHobli, selRec, populationCount, onUnsafeCount,
    shelters, evacuationPlan, simulationDone, selectedShelter,
    trafficRoadsData, showTraffic, showTrafficPins, onToggleTrafficPins,
    busManifest, selectedBusId, mapPinBox, onMapClick,
    selectedMetro, metroLines
}) {
    const hasFlood = !!(floodData?.features?.length);
    const hasRisk = !!(riskRoadsData?.features?.length);
    const hasTrafficData = showTraffic && !!(trafficRoadsData?.features?.length);

    const handleClick = useCallback((event) => {
        if (onMapClick) {
            onMapClick(event.lngLat.lat, event.lngLat.lng);
        }
    }, [onMapClick]);

    const busGeoJSON = useMemo(() => {
        const manifestArr = Array.isArray(busManifest) ? busManifest : busManifest?.manifest;
        if (!manifestArr || manifestArr.length === 0) return null;

        return {
            type: 'FeatureCollection',
            features: manifestArr
                .filter(bus => bus.path_points && bus.path_points.length >= 2)
                .map(bus => ({
                    type: 'Feature',
                    geometry: {
                        type: 'LineString',
                        coordinates: bus.path_points
                    },
                    properties: {
                        bus_id: bus.bus_id,
                        route_name: bus.route_name,
                        selected: bus.bus_id === selectedBusId,
                        fade: selectedBusId && bus.bus_id !== selectedBusId
                    }
                }))
        };
    }, [busManifest, selectedBusId]);

    const metroGeoJSON = useMemo(() => {
        if (!metroLines) return null;
        // Backend now sends FeatureCollection directly
        if (metroLines.type === 'FeatureCollection') {
            const hasFeatures = metroLines.features && metroLines.features.length > 0;
            return hasFeatures ? metroLines : null;
        }
        // Fallback for old array format
        if (Array.isArray(metroLines) && metroLines.length > 0) {
            return {
                type: 'FeatureCollection',
                features: metroLines
            };
        }
        return null;
    }, [metroLines]);

    const selectedBus = useMemo(() => {
        const manifestArr = Array.isArray(busManifest) ? busManifest : busManifest?.manifest;
        return selectedBusId && manifestArr ? manifestArr.find(b => b.bus_id === selectedBusId) : null;
    }, [selectedBusId, busManifest]);

    const selectedMetroStatus = selectedMetro?.status
        || (selectedMetro?.flooded === true ? 'unsafe' : selectedMetro?.flooded === false ? 'safe' : 'unknown');
    const selectedMetroLineNorm = (selectedMetro?.line || '').toString().trim().toLowerCase();
    const selectedMetroNameNorm = (selectedMetro?.name || '').toString().trim().toLowerCase();

    const selectedMetroStatusIcon = selectedMetroStatus === 'unsafe'
        ? '🔴'
        : selectedMetroStatus === 'caution'
            ? '🟡'
            : selectedMetroStatus === 'safe'
                ? '🟢'
                : '⏳';

    return (
        <main className="map-container">
            <Map
                {...viewState}
                onMove={e => onMove(e.viewState)}
                onClick={handleClick}
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
                                'line-color': [
                                    'case',
                                    ['get', 'fade'], '#fcd34d',
                                    ['get', 'selected'], '#d97706',
                                    '#f59e0b'
                                ],
                                'line-width': [
                                    'case',
                                    ['get', 'fade'], 2,
                                    ['get', 'selected'], 6,
                                    4.5
                                ],
                                'line-opacity': [
                                    'case',
                                    ['get', 'fade'], 0.3,
                                    ['get', 'selected'], 1,
                                    0.9
                                ],
                                'line-dasharray': [2, 1]
                            }}
                        />
                    </Source>
                )}
                {/* 6.6 Metro Network */}
                {metroGeoJSON && (
                    <Source id="metro-network" type="geojson" data={metroGeoJSON}>
                        <Layer
                            id="railway-network-layer"
                            type="line"
                            filter={['==', ['coalesce', ['get', 'transport_type'], 'metro'], 'railway']}
                            paint={{
                                'line-color': '#475569',
                                'line-width': 2,
                                'line-opacity': 0,
                                'line-dasharray': [1.5, 1.2]
                            }}
                            layout={{
                                'line-cap': 'round',
                                'line-join': 'round'
                            }}
                        />

                        <Layer
                            id="metro-network-layer"
                            type="line"
                            filter={['==', ['coalesce', ['get', 'transport_type'], 'metro'], 'metro']}
                            paint={{
                                'line-color': [
                                    'match', ['coalesce', ['get', 'colour'], 'none'],
                                    'purple', '#7c3aed',
                                    'green', '#059669',
                                    'yellow', '#eab308',
                                    'blue', '#2563eb',
                                    'pink', '#db2777',
                                    'red', '#dc2626',
                                    'railway', '#64748b',
                                    '#94a3b8' // neutral fallback (slate-400)
                                ],
                                'line-width': 2.2,
                                'line-opacity': 0,
                                'line-blur': 0.2
                            }}
                            layout={{
                                'line-cap': 'round',
                                'line-join': 'round'
                            }}
                        />

                        <Layer
                            id="metro-network-selected-layer"
                            type="line"
                            filter={selectedMetro
                                ? ['all',
                                    ['!=', ['coalesce', ['get', 'transport_type'], 'metro'], 'railway'],
                                    ['any',
                                        // Exact match by normalised line name (e.g. "green line" == "green line")
                                        ['==', ['downcase', ['coalesce', ['get', 'line'], '']], selectedMetroLineNorm],
                                        // Exact match by colour token (e.g. feature.colour="green" vs "green line" stripped)
                                        ['==', ['downcase', ['coalesce', ['get', 'colour'], '']], selectedMetroLineNorm.replace(' line', '').trim()],
                                    ]
                                ]
                                : ['==', ['get', 'id'], 'none']}
                            paint={{
                                'line-color': [
                                    'match', ['coalesce', ['get', 'colour'], 'none'],
                                    'purple', '#7c3aed',
                                    'green', '#059669',
                                    'yellow', '#eab308',
                                    'blue', '#2563eb',
                                    'pink', '#db2777',
                                    'red', '#dc2626',
                                    '#94a3b8'
                                ],
                                'line-width': 5.5,
                                'line-opacity': 0.95,
                                'line-blur': 0.1
                            }}
                            layout={{
                                'line-cap': 'butt',
                                'line-join': 'miter'
                            }}
                        />

                        <Layer
                            id="railway-network-selected-layer"
                            type="line"
                            filter={selectedMetro
                                ? ['all',
                                    ['==', ['get', 'transport_type'], 'railway'],
                                    ['==', ['downcase', ['coalesce', ['get', 'line'], '']], selectedMetroLineNorm],
                                ]
                                : ['==', ['get', 'id'], 'none']}
                            paint={{
                                'line-color': 'rgba(78, 77, 77, 0.8)',
                                'line-width': 6,
                                'line-opacity': 0.9,
                                'line-dasharray': [2, 2]
                            }}
                            layout={{
                                'line-cap': 'butt',
                                'line-join': 'miter'
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

                {/* 8. Selected Bus Endpoints */}
                {selectedBus && selectedBus.path_points && selectedBus.path_points.length >= 2 && (
                    <>
                        <Marker
                            longitude={selectedBus.path_points[0][0]}
                            latitude={selectedBus.path_points[0][1]}
                            anchor="bottom"
                        >
                            <div className="evac-dest-pin" style={{ filter: 'drop-shadow(0 2px 6px rgba(217, 119, 6, 0.4))' }}>
                                <MapPin size={22} fill="#d97706" color="white" strokeWidth={1.5} />
                                <div className="evac-dest-label" style={{ background: '#fef3c7', color: '#d97706', border: '1px solid #d97706' }}>Pickup: {selectedBus.origin_stop_name}</div>
                            </div>
                        </Marker>

                        <Marker
                            longitude={selectedBus.path_points[selectedBus.path_points.length - 1][0]}
                            latitude={selectedBus.path_points[selectedBus.path_points.length - 1][1]}
                            anchor="bottom"
                        >
                            <div className="evac-dest-pin" style={{ filter: 'drop-shadow(0 2px 6px rgba(21, 128, 61, 0.4))' }}>
                                <MapPin size={22} fill="#15803d" color="white" strokeWidth={1.5} />
                                <div className="evac-dest-label" style={{ background: '#ecfdf5', color: '#15803d', border: '1px solid #15803d' }}>Dropoff: {selectedBus.to_shelter}</div>
                            </div>
                        </Marker>
                    </>
                )}

                {/* 9. Selected Metro/Railway Station */}
                {selectedMetro && (
                    <Marker longitude={selectedMetro.lon} latitude={selectedMetro.lat} anchor="bottom">
                        <div className="evac-dest-pin" style={{
                            filter: selectedMetro.transport_type === 'railway'
                                ? 'drop-shadow(0 2px 6px rgba(100, 116, 139, 0.4))'
                                : 'drop-shadow(0 2px 6px rgba(124, 58, 237, 0.4))'
                        }}>
                            <div style={{
                                background: selectedMetro.transport_type === 'railway' ? '#64748b' : '#7c3aed',
                                color: 'white',
                                padding: '6px',
                                borderRadius: '50%',
                                border: '2px solid white',
                                boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center'
                            }}>
                                {selectedMetro.transport_type === 'railway' ? <Activity size={16} /> : <Train size={16} />}
                            </div>
                            <div className="evac-dest-label" style={{
                                background: selectedMetro.transport_type === 'railway' ? '#f1f5f9' : '#f5f3ff',
                                color: selectedMetro.transport_type === 'railway' ? '#475569' : '#7c3aed',
                                border: `1px solid ${selectedMetro.transport_type === 'railway' ? '#94a3b8' : '#7c3aed'}`
                            }}>
                                {selectedMetro.transport_type === 'railway' ? '🛤️' : '🚆'} {selectedMetro.name}
                                {selectedMetro.line ? ` · ${selectedMetro.line}` : ''}
                                {' '}
                                {selectedMetroStatusIcon}
                            </div>
                        </div>
                    </Marker>
                )}

                {/* Selected Map Pin box */}
                {mapPinBox && (
                    <Marker latitude={mapPinBox.lat} longitude={mapPinBox.lon} anchor="bottom">
                        <div className="evac-dest-pin" style={{ filter: 'drop-shadow(0 2px 6px rgba(239, 68, 68, 0.4))' }}>
                            <MapPin size={22} fill="#ef4444" color="white" strokeWidth={1.5} />
                            <div className="evac-dest-label" style={{ background: '#fee2e2', color: '#b91c1c', border: '1px solid #b91c1c' }}>PINNED LOCATION</div>
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