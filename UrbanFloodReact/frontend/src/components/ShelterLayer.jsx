/**
 * ShelterLayer.jsx
 * ─────────────────
 * Renders shelter markers using react-map-gl Marker + SVG house icons.
 * Hover tooltip is handled via React events (no MapLibre layer events needed).
 *
 *   Green  — safe shelter
 *   Red    — flooded / unsafe
 *   Amber  — synthetic / approximate location
 */
import { useState } from 'react';
import { Marker, Popup } from 'react-map-gl/maplibre';

const TYPE_LABEL = {
    school:           'School',
    hospital:         'Hospital',
    community_centre: 'Community Centre',
    townhall:         'Town Hall',
    police:           'Police Station',
    fire_station:     'Fire Station',
    public:           'Public Building',
};

/** Inline SVG house / building icon — always renders, no font dependency */
function HouseIcon({ color }) {
    return (
        <svg width="30" height="34" viewBox="0 0 30 34" fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ display: 'block', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.3))' }}>
            {/* Soft ground shadow */}
            <ellipse cx="15" cy="32" rx="7" ry="2" fill="rgba(0,0,0,0.18)" />
            {/* Building body */}
            <rect x="5" y="17" width="20" height="13" rx="1.5" fill={color} />
            {/* Roof */}
            <polygon points="15,3 1,18 29,18" fill={color}
                stroke="white" strokeWidth="1.8" strokeLinejoin="round" />
            {/* White border on body */}
            <rect x="5" y="17" width="20" height="13" rx="1.5"
                stroke="white" strokeWidth="1.8" fill="none" />
            {/* Door */}
            <rect x="12" y="22" width="6" height="8" rx="1" fill="white" fillOpacity="0.85" />
            {/* Left window */}
            <rect x="7"  y="19" width="4" height="3" rx="0.6" fill="white" fillOpacity="0.7" />
            {/* Right window */}
            <rect x="19" y="19" width="4" height="3" rx="0.6" fill="white" fillOpacity="0.7" />
        </svg>
    );
}

export function ShelterLayer({ shelters }) {
    const [hovered, setHovered] = useState(null);

    if (!shelters?.length) return null;

    return (
        <>
            {shelters.map(s => {
                const color = s.synthetic ? '#d97706'
                            : s.safe      ? '#16a34a'
                            :               '#dc2626';
                return (
                    <Marker key={s.id} longitude={s.lon} latitude={s.lat} anchor="bottom">
                        <div
                            onMouseEnter={() => setHovered(s)}
                            onMouseLeave={() => setHovered(null)}
                            style={{ cursor: 'pointer' }}
                        >
                            <HouseIcon color={color} />
                        </div>
                    </Marker>
                );
            })}

            {/* Hover tooltip Popup */}
            {hovered && (
                <Popup
                    longitude={hovered.lon}
                    latitude={hovered.lat}
                    closeButton={false}
                    anchor="bottom"
                    offset={36}
                >
                    <div className="shelter-popup">
                        <strong>{hovered.name}</strong>
                        <span>{TYPE_LABEL[hovered.type] ?? hovered.type} · {hovered.capacity.toLocaleString()} cap</span>
                        <span style={{ color: hovered.safe ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
                            {hovered.synthetic ? '📍 Approx. location' : hovered.safe ? '✓ Safe' : '✗ Flooded'}
                        </span>
                    </div>
                </Popup>
            )}
        </>
    );
}
