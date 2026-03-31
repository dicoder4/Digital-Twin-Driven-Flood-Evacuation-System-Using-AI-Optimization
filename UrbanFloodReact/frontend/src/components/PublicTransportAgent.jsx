import { useState, useEffect } from 'react';
import { Bus, Train, Users, MapPin, Loader, FileText, ChevronRight, ChevronUp, ChevronDown, Activity, Trash2, AlertTriangle } from 'lucide-react';
import { API_URL } from '../config';
import './PublicTransportAgent.css';

export function PublicTransportAgent({ 
    evacuationPlan, 
    onManifestGenerated, 
    shelters = [], 
    selectedBusId, 
    onSelectBus,
    metroReports = [], // Array of { name, lat, lon, flooded } from final simulation report
    metroStations = [],
    onSelectMetro,     // Callback to show metro pin on map
    selectedMetroId,   // ID/Name of metro to highlight
    loadedHobli
}) {
    const [manifest, setManifest] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [stations, setStations] = useState([]); // Initial station list
    
    // UI state for independent dropdowns
    const [busOpen, setBusOpen] = useState(true);
    const [metroOpen, setMetroOpen] = useState(false);

    useEffect(() => {
        setStations(metroStations || []);
    }, [metroStations]);

    // Merge static station list with live physics reports if available
    // Sort: Metro first, then Railway
    const displayMetro = Array.from(
        [...stations.map(s => ({ ...s, flooded: null })), ...metroReports]
            .reduce((acc, item) => {
                const key = `${(item?.name || '').trim().toLowerCase()}`;
                const existing = acc.get(key);
                if (!existing) {
                    acc.set(key, item);
                    return acc;
                }
                acc.set(key, {
                    ...existing,
                    ...item,
                    line: item?.line || existing?.line,
                    colour: item?.colour || existing?.colour,
                    transport_type: item?.transport_type || existing?.transport_type || 'metro',
                });
                return acc;
            }, new Map()).values()
    )
    .filter((item) => {
        const text = `${item?.name || ''} ${item?.line || ''}`.toLowerCase();
        if (!item?.name) return false;
        if (text.includes('bus') || text.includes('police station')) return false;
        const transportType = (item?.transport_type || '').toString().toLowerCase();
        if (transportType === 'metro' || transportType === 'railway') return true;
        return text.includes('line') || text.includes('metro') || text.includes('railway') || text.includes('subway');
    })
    .sort((a, b) => {
        const getVal = (x) => x.transport_type === 'railway' ? 1 : 0;
        return getVal(a) - getVal(b);
    });

    const metroRowKey = (m) => m.id || `${m.name}::${m.line || ''}`;

    const prettyLineName = (lineName) => {
        const line = (lineName || '').toString().trim();
        if (!line) return 'Unknown Line';
        const lower = line.toLowerCase();
        if (lower.includes('railway')) return 'Railway Track';
        if (lower === 'namma metro' || lower === 'namma metro/rail' || lower === 'metro') return 'Unknown Line';
        return line;
    };

    const getMetroStatus = (m) => {
        if (m?.status) return m.status;
        if (m?.flooded === true) return 'unsafe';
        if (m?.flooded === false) return 'safe';
        return 'unknown';
    };

    const renderStatusPill = (m) => {
        const status = getMetroStatus(m);
        if (status === 'unsafe') {
            return (
                <span className="pta-status-pill pta-status-flooded">
                    <AlertTriangle size={10} style={{ marginRight: '3px' }} /> Unsafe
                </span>
            );
        }
        if (status === 'caution') {
            return (
                <span className="pta-status-pill" style={{ background: '#fef3c7', color: '#92400e', border: '1px solid #f59e0b' }}>
                    Caution
                </span>
            );
        }
        if (status === 'safe') {
            return <span className="pta-status-pill pta-status-operational">Safe</span>;
        }
        return (
            <span className="pta-status-pill" style={{ background: '#f1f5f9', color: '#94a3b8' }}>
                Analyzing...
            </span>
        );
    };

    const floodedMetroCount = metroReports.filter((m) => getMetroStatus(m) === 'unsafe').length;

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

            if (!res.ok) throw new Error("Failed to generate public transport plan");

            const data = await res.json();

            if (data.manifest && shelters.length > 0) {
                data.manifest = data.manifest.map(bus => {
                    const matched = shelters.find(s => String(s.id) === String(bus.to_shelter));
                    return { ...bus, to_shelter: matched ? matched.name : bus.to_shelter };
                });
            }

            setManifest(data);
            if (onManifestGenerated && data.manifest) onManifestGenerated(data.manifest);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section className="panel pta-section" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div className="pta-header">
                <h3 className="panel-title" style={{ color: '#059669', display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
                    <Activity size={18} /> Public Transport Agent
                </h3>
                <p style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem', marginBottom: 0 }}>
                    Coordinate multi-modal logistics for {loadedHobli || 'Region'}.
                </p>
            </div>

            <div className="pta-content custom-scrollbar" style={{ marginTop: '1rem', overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
                
                {/* ── BMTC Bus Fleet Accordion ── */}
                <div className="pta-accordion">
                    <div className="pta-accordion-header" onClick={() => setBusOpen(!busOpen)}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: '#334155', fontSize: '0.85rem' }}>
                            <Bus size={16} color="#d97706" /> BMTC Bus Fleet
                        </div>
                        {busOpen ? <ChevronUp size={16} color="#94a3b8" /> : <ChevronDown size={16} color="#94a3b8" />}
                    </div>
                    
                    {busOpen && (
                        <div className="pta-accordion-content">
                            <button
                                className="pta-generate-btn"
                                onClick={handleGenerateManifest}
                                disabled={loading || !evacuationPlan.length}
                            >
                                {loading ? <Loader size={16} className="spin" /> : <FileText size={16} />}
                                Generate Fleet Manifest
                            </button>

                            {error && <div className="pta-error" style={{ color: '#dc2626', fontSize: '0.75rem', marginTop: '0.5rem' }}>{error}</div>}

                            {manifest && (
                                <div className="pta-manifest-container" style={{ marginTop: '1rem' }}>
                                    <div className="pta-summary">
                                        <div className="pta-stat-box">
                                            <span className="pta-stat-val">{manifest.total_buses}</span>
                                            <span className="pta-stat-label">Buses</span>
                                        </div>
                                        <div className="pta-stat-box">
                                            <span className="pta-stat-val">
                                                {manifest.manifest.reduce((sum, bus) => sum + bus.evacuees, 0)}
                                            </span>
                                            <span className="pta-stat-label">Pax Routed</span>
                                        </div>
                                    </div>

                                    <div className="pta-table-wrapper">
                                        <table className="pta-table">
                                            <thead>
                                                <tr>
                                                    <th>FLEET / ROUTE</th>
                                                    <th>DESTINATION</th>
                                                    <th style={{ textAlign: 'right' }}>PAX</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {manifest.manifest.map((bus, idx) => (
                                                    <tr
                                                        key={idx}
                                                        onClick={() => onSelectBus && onSelectBus(bus.bus_id === selectedBusId ? null : bus.bus_id)}
                                                        className={bus.bus_id === selectedBusId ? 'pta-row-selected' : ''}
                                                        style={{ cursor: 'pointer' }}
                                                    >
                                                        <td>
                                                            <div style={{ fontWeight: 600, color: '#1e293b' }}>{bus.bus_id}</div>
                                                            <div style={{ fontSize: '0.7rem', color: '#64748b' }}>{bus.route_name}</div>
                                                        </td>
                                                        <td>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.75rem' }}>
                                                                <ChevronRight size={12} color="#16a34a" /> {bus.to_shelter}
                                                            </div>
                                                        </td>
                                                        <td style={{ textAlign: 'right', fontWeight: 600, color: '#059669' }}>
                                                            {bus.evacuees}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* ── Namma Metro/Rail Network Accordion ── */}
                <div className="pta-accordion">
                    <div className="pta-accordion-header" onClick={() => setMetroOpen(!metroOpen)}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, color: '#334155', fontSize: '0.85rem' }}>
                            <Train size={16} color="#7c3aed" /> Namma Metro/Rail Network
                            {metroReports.length > 0 && (
                                <span style={{ marginLeft: '4px', fontSize: '0.65rem', background: floodedMetroCount > 0 ? '#fee2e2' : '#dcfce7', color: floodedMetroCount > 0 ? '#dc2626' : '#16a34a', padding: '1px 6px', borderRadius: '10px' }}>
                                    {floodedMetroCount} Flooded
                                </span>
                            )}
                        </div>
                        {metroOpen ? <ChevronUp size={16} color="#94a3b8" /> : <ChevronDown size={16} color="#94a3b8" />}
                    </div>

                    {metroOpen && (
                        <div className="pta-accordion-content">
                            <div style={{ background: '#f5f3ff', color: '#6d28d9', border: '1px solid #ddd6fe', borderRadius: '8px', padding: '0.6rem 0.75rem', marginBottom: '1rem', fontSize: '0.75rem' }}>
                                Metro/Rail network is loaded when you click <strong>Load Network</strong> in Setup.
                            </div>

                            {displayMetro.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '1rem', color: '#94a3b8', fontSize: '0.8rem' }}>
                                    <Train size={24} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                                    <p>No metro/rail stations found for this loaded region.</p>
                                </div>
                            ) : (
                                <div className="pta-table-wrapper" style={{ maxHeight: '300px' }}>
                                    <table className="pta-table">
                                        <thead>
                                            <tr>
                                                <th>STATION NAME</th>
                                                    <th>LINE</th>
                                                <th>STATUS / SAFETY</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {displayMetro.map((m, idx) => (
                                                <tr 
                                                    key={idx} 
                                                    onClick={() => {
                                                        const isSelected = metroRowKey(m) === selectedMetroId;
                                                        const newSelection = isSelected ? null : m;
                                                        onSelectMetro && onSelectMetro(newSelection);
                                                    }}
                                                    className={metroRowKey(m) === selectedMetroId ? 'pta-row-selected' : ''}
                                                    style={{ cursor: 'pointer' }}
                                                >
                                                    <td style={{ fontWeight: 500 }}>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                                            {m.transport_type === 'railway' ? <Activity size={12} color="#64748b" /> : <Train size={12} color="#7c3aed" />}
                                                            {m.name}
                                                        </div>
                                                    </td>
                                                    <td>
                                                        <span
                                                            className="pta-status-pill"
                                                            style={{
                                                                background: m.transport_type === 'railway' ? '#f1f5f9' : '#f5f3ff',
                                                                color: m.transport_type === 'railway' ? '#475569' : '#6d28d9',
                                                                border: `1px solid ${m.transport_type === 'railway' ? '#cbd5e1' : '#c4b5fd'}`,
                                                            }}
                                                        >
                                                            {prettyLineName(m.line)}
                                                        </span>
                                                    </td>
                                                    <td>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                                            {renderStatusPill(m)}
                                                            {m.confidence && (
                                                                <span className="pta-status-pill" style={{ background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>
                                                                    {m.confidence}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                            <p style={{ fontSize: '0.65rem', color: '#94a3b8', marginTop: '0.75rem', fontStyle: 'italic' }}>
                                Click a station to highlight the station and show its entire line on the map. Click again to toggle off.
                            </p>
                        </div>
                    )}
                </div>

            </div>
        </section>
    );
}
