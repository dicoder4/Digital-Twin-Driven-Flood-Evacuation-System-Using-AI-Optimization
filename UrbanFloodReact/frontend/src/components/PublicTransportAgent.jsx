import { useState } from 'react';
import { Bus, Users, MapPin, Loader, FileText, ChevronRight } from 'lucide-react';
import { API_URL } from '../config';
import './PublicTransportAgent.css';

export function PublicTransportAgent({ evacuationPlan, onManifestGenerated, shelters = [], selectedBusId, onSelectBus }) {
    const [manifest, setManifest] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const handleGenerateManifest = async () => {
        if (!evacuationPlan || evacuationPlan.length === 0) {
            setError("No evacuation routes available. Please run a simulation first.");
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const res = await fetch(`${API_URL}/public-transport-plan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ evacuation_plan: evacuationPlan }),
            });

            if (!res.ok) {
                throw new Error("Failed to generate public transport plan from server");
            }

            const data = await res.json();

            // Map shelter IDs to readable names if possible
            if (data.manifest && shelters.length > 0) {
                data.manifest = data.manifest.map(bus => {
                    const matched = shelters.find(s => String(s.id) === String(bus.to_shelter));
                    return { ...bus, to_shelter: matched ? matched.name : bus.to_shelter };
                });
            }

            setManifest(data);

            // Push the generated bus manifest back up to App.jsx -> FloodMap.jsx
            if (onManifestGenerated && data.manifest) {
                onManifestGenerated(data.manifest);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section className="panel pta-section" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div className="pta-header" style={{ marginBottom: '1rem' }}>
                <h3 className="panel-title" style={{ color: '#059669', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
                    <Bus size={18} /> Public Transport Agent
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.25rem' }}>
                    Generate a detailed fleet deployment manifest mapping evacuation routes to active BMTC bus networks.
                </p>
            </div>

            <div style={{ marginBottom: '1rem' }}>
                <button
                    className="pta-generate-btn"
                    onClick={handleGenerateManifest}
                    disabled={loading || !evacuationPlan.length}
                    title={!evacuationPlan.length ? "Run an Evacuation Simulation first" : "Query GTFS MCP Server for Bus deployment"}
                >
                    {loading ? <Loader size={16} className="spin" /> : <FileText size={16} />}
                    Generate Fleet Manifest
                </button>
            </div>

            {error && <div className="pta-error">{error}</div>}

            {manifest && (
                <div className="pta-manifest-container custom-scrollbar">
                    <div className="pta-summary">
                        <div className="pta-stat-box">
                            <span className="pta-stat-val">{manifest.total_buses}</span>
                            <span className="pta-stat-label">Buses Deployed</span>
                        </div>
                        <div className="pta-stat-box">
                            <span className="pta-stat-val">
                                {manifest.manifest.reduce((sum, bus) => sum + bus.evacuees, 0)}
                            </span>
                            <span className="pta-stat-label">Total Pax Routed</span>
                        </div>
                    </div>

                    <div className="pta-table-wrapper">
                        <table className="pta-table">
                            <thead>
                                <tr>
                                    <th>FLEET ID / ROUTE</th>
                                    <th>ORIGIN STOP</th>
                                    <th>DESTINATION (SHELTER)</th>
                                    <th style={{ textAlign: 'right' }}>PAX</th>
                                </tr>
                            </thead>
                            <tbody>
                                {manifest.manifest.map((bus, idx) => (
                                    <tr
                                        key={idx}
                                        onClick={() => onSelectBus && onSelectBus(bus.bus_id === selectedBusId ? null : bus.bus_id)}
                                        className={bus.bus_id === selectedBusId ? 'pta-row-selected' : ''}
                                        style={{ cursor: 'pointer', ... (bus.bus_id === selectedBusId ? { backgroundColor: '#f0fdf4', borderLeft: '3px solid #16a34a' } : {}) }}
                                        title="Click to view route on map"
                                    >
                                        <td>
                                            <div style={{ fontWeight: 600, color: '#111827' }}>{bus.bus_id}</div>
                                            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Route: {bus.route_name}</div>
                                        </td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.8rem' }}>
                                                <MapPin size={12} color="#dc2626" /> {bus.origin_stop_name}
                                            </div>
                                        </td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.8rem' }}>
                                                <ChevronRight size={12} color="#16a34a" /> {bus.to_shelter}
                                            </div>
                                        </td>
                                        <td style={{ textAlign: 'right', fontWeight: 600 }}>
                                            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', backgroundColor: '#ecfdf5', padding: '2px 6px', borderRadius: '4px', color: '#059669' }}>
                                                <Users size={12} /> {bus.evacuees}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </section>
    );
}
