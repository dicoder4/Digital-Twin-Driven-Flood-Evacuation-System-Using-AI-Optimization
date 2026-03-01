/**
 * EvacuationPanel.jsx
 * ───────────────────
 * Post-simulation analysis tab. Shows:
 *  - Overview stats (evacuated, success rate, GA time)
 *  - Clickable shelter rows → reveals routes on map for that shelter
 *  - Unreachable population alert
 */
import { useMemo } from 'react';
import { ShieldCheck, AlertTriangle, Clock, Users, Building2, MapPin, ChevronRight } from 'lucide-react';

const SHELTER_EMOJI = {
    school: '🏫',
    hospital: '🏥',
    community_centre: '🏛️',
    police: '🚓',
    fire_station: '🚒',
    public: '🏢',
    synthetic: '📍',
};

function shelterIcon(type = '') {
    return SHELTER_EMOJI[type] || '🏠';
}

function FillBar({ pct }) {
    const cls =
        pct >= 90 ? 'danger'
            : pct >= 60 ? 'warn'
                : 'safe';
    return (
        <div className="fill-bar-bg">
            <div className={`fill-bar-fill fill-${cls}`} style={{ width: `${pct}%` }} />
        </div>
    );
}

export function EvacuationPanel({ summary, evacuationMode, selectedShelterId, onSelectShelter, trafficSegmentCount = 0, showTraffic = false }) {
    if (!summary) {
        return (
            <div className="evac-empty">
                <ShieldCheck size={32} className="evac-empty-icon" />
                <p>Run a simulation to see evacuation analysis.<br />
                    Enable <strong>Evacuation Mode</strong> to scale population to 1% for faster testing.</p>
            </div>
        );
    }

    const {
        total_evacuated = 0,
        total_at_risk_remaining = 0,
        total_at_risk_initial = 0,
        simulation_population = 0,
        success_rate_pct = 0,
        ga_execution_time = 0,
        shelter_reports = [],
    } = summary;

    const totalConsidered = total_at_risk_initial || (total_evacuated + total_at_risk_remaining);

    // Sort shelters by occupancy_pct descending (most filled first), then filter to those with occupancy > 0 first
    const sortedShelters = useMemo(() =>
        [...shelter_reports].sort((a, b) => b.occupancy_pct - a.occupancy_pct),
        [shelter_reports]
    );

    return (
        <div className="evac-panel">

            {/* ── Overview ─────────────────────────────── */}
            <section className="panel evac-section">
                <h3 className="panel-title"><ShieldCheck size={13} /> Evacuation Overview</h3>

                <div className="evac-stat-grid">
                    <div className="evac-stat-card evac-stat-green">
                        <Users size={16} />
                        <div className="evac-stat-val">{total_evacuated.toLocaleString()}</div>
                        <div className="evac-stat-lbl">Evacuated</div>
                    </div>
                    <div className={`evac-stat-card ${total_at_risk_remaining > 0 ? 'evac-stat-red' : 'evac-stat-green'}`}>
                        <AlertTriangle size={16} />
                        <div className="evac-stat-val">{total_at_risk_remaining.toLocaleString()}</div>
                        <div className="evac-stat-lbl">Unreachable</div>
                    </div>
                    <div className="evac-stat-card evac-stat-blue">
                        <ShieldCheck size={16} />
                        <div className="evac-stat-val">{success_rate_pct}%</div>
                        <div className="evac-stat-lbl">Success Rate</div>
                    </div>
                    <div className="evac-stat-card evac-stat-muted">
                        <Clock size={16} />
                        <div className="evac-stat-val">{ga_execution_time}s</div>
                        <div className="evac-stat-lbl">GA Time</div>
                    </div>
                    {showTraffic && (
                        <div className="evac-stat-card" style={{ background: '#ecfeff', border: '1px solid #22d3ee' }}>
                            <span style={{ fontSize: 16 }}>🚦</span>
                            <div className="evac-stat-val" style={{ color: '#0891b2' }}>{trafficSegmentCount}</div>
                            <div className="evac-stat-lbl">Traffic Roads</div>
                        </div>
                    )}
                </div>

                {simulation_population > 0 && (
                    <div className="evac-sim-pop-note">
                        <Users size={11} />
                        <span>Simulation used <strong>{simulation_population.toLocaleString()}</strong> people
                            {simulation_population < 10000 ? ' (1% test mode)' : ''}
                        </span>
                    </div>
                )}

                {totalConsidered > 0 && (
                    <div className="evac-overall-bar-wrap">
                        <div className="evac-overall-bar-bg">
                            <div
                                className="evac-overall-bar-fill"
                                style={{ width: `${success_rate_pct}%` }}
                            />
                        </div>
                        <div className="evac-overall-bar-labels">
                            <span className="evac-lbl-safe">✓ {success_rate_pct}% evacuated</span>
                            <span className="evac-lbl-risk">✗ {(100 - success_rate_pct).toFixed(1)}% at risk</span>
                        </div>
                    </div>
                )}
            </section>

            {/* ── Unreachable Alert ─────────────────────── */}
            {total_at_risk_remaining > 0 && (
                <div className="evac-alert">
                    <AlertTriangle size={14} />
                    <span>
                        <strong>{total_at_risk_remaining.toLocaleString()}</strong> people could not be
                        assigned to a safe shelter. Manual rescue required.
                    </span>
                </div>
            )}

            {/* ── Shelter Fill Report (clickable) ───────── */}
            {sortedShelters.length > 0 && (
                <section className="panel evac-section">
                    <h3 className="panel-title"><Building2 size={13} /> Shelter Capacity
                        <span className="panel-title-hint">— click to view routes</span>
                    </h3>
                    <div className="shelter-fill-list">
                        {sortedShelters.map((s) => {
                            const isSelected = selectedShelterId === s.id;
                            const hasOccupancy = s.occupancy > 0;
                            return (
                                <div
                                    key={s.id}
                                    className={`shelter-fill-row shelter-fill-row--clickable ${isSelected ? 'shelter-fill-row--selected' : ''} ${!hasOccupancy ? 'shelter-fill-row--empty' : ''}`}
                                    onClick={() => hasOccupancy && onSelectShelter(isSelected ? null : s.id)}
                                    title={hasOccupancy
                                        ? (isSelected ? 'Click to hide routes' : `Show ${s.occupancy} evacuation routes to this shelter`)
                                        : 'No evacuees assigned to this shelter'}
                                >
                                    <div className="shelter-fill-header">
                                        <span className="shelter-fill-name">
                                            {shelterIcon(s.type)} {s.name || s.id}
                                        </span>
                                        <div className="shelter-fill-right">
                                            <span className={`shelter-fill-pct ${s.occupancy_pct >= 90 ? 'pct-danger' : s.occupancy_pct >= 60 ? 'pct-warn' : 'pct-safe'}`}>
                                                {s.occupancy_pct}%
                                            </span>
                                            {hasOccupancy && (
                                                <span className={`shelter-route-btn ${isSelected ? 'shelter-route-btn--active' : ''}`}>
                                                    <MapPin size={10} />
                                                    {isSelected ? 'Viewing' : 'Routes'}
                                                    <ChevronRight size={10} />
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <FillBar pct={s.occupancy_pct} />
                                    <div className="shelter-fill-meta">
                                        {s.occupancy.toLocaleString()} / {s.capacity.toLocaleString()} people
                                        {hasOccupancy && <span className="shelter-fill-meta-routes"> · {s.occupancy} routed here</span>}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </section>
            )}
        </div>
    );
}
