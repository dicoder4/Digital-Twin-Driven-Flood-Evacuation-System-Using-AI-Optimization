/**
 * EvacuationPanel.jsx
 * ───────────────────
 * Post-simulation analysis tab. Shows:
 *  - Overview stats (evacuated, success rate, GA time)
 *  - Clickable shelter rows → reveals routes on map for that shelter
 *  - Unreachable population alert
 */
import { useMemo } from 'react';
import { ShieldCheck, AlertTriangle, Clock, Users, Building2, MapPin, ChevronRight, Trophy, Zap } from 'lucide-react';

const ALGO_COLORS = {
    ga:  { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', label: 'Genetic Algorithm' },
    aco: { bg: '#f0fdf4', border: '#86efac', text: '#15803d', label: 'Ant Colony Opt.' },
    pso: { bg: '#fdf4ff', border: '#d8b4fe', text: '#7e22ce', label: 'Particle Swarm' },
};

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

export function EvacuationPanel({ summary, evacuationMode, selectedShelterId, onSelectShelter, trafficSegmentCount = 0, showTraffic = false, compareResults = null, compareActiveAlgo = null, onSetCompareAlgo = null }) {

    // ── Compare table must be checked FIRST — summary is null after compare ──
    // (compare runs its own EventSources and never sets sim.finalReport)
    const bestAlgo = useMemo(() => {
        if (!compareResults) return null;
        let best = null, bestFitness = Infinity;
        for (const [algo, res] of Object.entries(compareResults)) {
            const f = res.best_fitness ?? Infinity;
            if (!res.error && f < bestFitness) {
                bestFitness = f;
                best = algo;
            }
        }
        return best;
    }, [compareResults]);

    if (compareResults) {
        const rows = ['ga', 'aco', 'pso'].map(algo => ({
            algo,
            ...compareResults[algo],
        }));

        // Active algo detail — extract summary fields from the selected algo's results
        const activeData = compareActiveAlgo ? compareResults[compareActiveAlgo] : null;
        const ad = activeData ? {
            total_evacuated:        activeData.total_evacuated ?? 0,
            total_at_risk_remaining: activeData.total_at_risk_remaining ?? 0,
            total_at_risk_initial:  activeData.total_at_risk_initial ?? 0,
            simulation_population:  activeData.simulation_population ?? 0,
            success_rate_pct:       activeData.success_rate_pct ?? 0,
            ga_execution_time:      activeData.ga_execution_time ?? 0,
            shelter_reports:        activeData.shelter_reports ?? [],
            traffic_segment_count:  activeData.traffic_segment_count ?? 0,
        } : null;
        const adTotalConsidered = ad ? (ad.total_at_risk_initial || (ad.total_evacuated + ad.total_at_risk_remaining)) : 0;
        const adSortedShelters  = ad ? [...ad.shelter_reports].sort((a, b) => b.occupancy_pct - a.occupancy_pct) : [];
        const adColor = compareActiveAlgo ? ALGO_COLORS[compareActiveAlgo] : null;

        return (
            <div className="evac-panel">
                <section className="panel evac-section">
                    <h3 className="panel-title"><Trophy size={13} /> Algorithm Comparison</h3>

                    {/* Route selector hint */}
                    <div className="compare-route-hint">
                        <MapPin size={10} /> Click <strong>Show Routes</strong> on any row to view that algorithm's evacuation plan on the map
                    </div>

                    <div className="compare-table">
                        <div className="compare-header">
                            <span>Algorithm</span>
                            <span title="Lower is better — total flood-weighted distance + time cost for all evacuees">Fitness ↓</span>
                            <span>Success %</span>
                            <span>Time</span>
                        </div>
                        {rows.map(({ algo, best_fitness: fit = null, success_rate_pct: rate = 0, ga_execution_time: t = 0, error }) => {
                            const c = ALGO_COLORS[algo];
                            const isWinner = algo === bestAlgo;
                            const isActive = algo === compareActiveAlgo;
                            const fitLabel = fit != null
                                ? (fit >= 1_000_000 ? `${(fit/1_000_000).toFixed(2)}M`
                                 : fit >= 1_000     ? `${(fit/1_000).toFixed(1)}k`
                                 : String(fit))
                                : '—';
                            return (
                                <div key={algo}>
                                    <div
                                        className={`compare-row ${isWinner ? 'compare-row--winner' : ''} ${isActive ? 'compare-row--active' : ''}`}
                                        style={{ borderLeft: `3px solid ${c.border}`, background: isActive ? c.bg : isWinner ? c.bg : undefined }}>
                                        <span className="compare-algo" style={{ color: c.text }}>
                                            {isWinner && <Trophy size={10} style={{ verticalAlign: 'middle', marginRight: 3 }}/>}
                                            {algo.toUpperCase()}
                                            {isWinner && <span className="compare-winner-badge">BEST</span>}
                                        </span>
                                        {error
                                            ? <span className="compare-error" style={{ gridColumn: '2 / -1' }}>Failed</span>
                                            : <>
                                                <span style={{ fontWeight: isWinner ? 700 : 400, color: isWinner ? c.text : undefined }}>{fitLabel}</span>
                                                <span className={rate >= 80 ? 'compare-rate-good' : rate >= 50 ? 'compare-rate-warn' : 'compare-rate-bad'}>
                                                    {rate}%
                                                </span>
                                                <span>{t}s</span>
                                              </>
                                        }
                                    </div>
                                    {/* Route toggle button */}
                                    {!error && onSetCompareAlgo && (
                                        <button
                                            className={`compare-route-btn ${isActive ? 'compare-route-btn--active' : ''}`}
                                            style={isActive ? { background: c.bg, borderColor: c.border, color: c.text } : {}}
                                            onClick={() => onSetCompareAlgo(isActive ? null : algo)}
                                        >
                                            <MapPin size={9} />
                                            {isActive ? `Showing ${algo.toUpperCase()} routes` : `Show ${algo.toUpperCase()} routes`}
                                            {isActive && <span className="compare-route-active-dot" />}
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {bestAlgo && (
                        <div className="compare-verdict">
                            <Zap size={12} style={{ color: ALGO_COLORS[bestAlgo].text }}/>
                            <strong style={{ color: ALGO_COLORS[bestAlgo].text }}>{bestAlgo.toUpperCase()}</strong> found the lowest-cost evacuation plan
                            (fitness&nbsp;=&nbsp;{compareResults[bestAlgo]?.best_fitness?.toLocaleString()})
                        </div>
                    )}
                    <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 4 }}>
                        Fitness = flood-weighted distance + travel time + overflow penalty (lower = better routes)
                    </div>
                </section>

                {/* ── Per-algo detail view (appears when an algo is active) ────── */}
                {ad && adColor && (
                    <>
                        <section className="panel evac-section" style={{ borderTop: `2px solid ${adColor.border}` }}>
                            <h3 className="panel-title" style={{ color: adColor.text }}>
                                <ShieldCheck size={13} /> {compareActiveAlgo.toUpperCase()} — Evacuation Overview
                            </h3>

                            <div className="evac-stat-grid">
                                <div className="evac-stat-card evac-stat-green">
                                    <Users size={16} />
                                    <div className="evac-stat-val">{ad.total_evacuated.toLocaleString()}</div>
                                    <div className="evac-stat-lbl">Evacuated</div>
                                </div>
                                <div className={`evac-stat-card ${ad.total_at_risk_remaining > 0 ? 'evac-stat-red' : 'evac-stat-green'}`}>
                                    <AlertTriangle size={16} />
                                    <div className="evac-stat-val">{ad.total_at_risk_remaining.toLocaleString()}</div>
                                    <div className="evac-stat-lbl">Unreachable</div>
                                </div>
                                <div className="evac-stat-card evac-stat-blue">
                                    <ShieldCheck size={16} />
                                    <div className="evac-stat-val">{ad.success_rate_pct}%</div>
                                    <div className="evac-stat-lbl">Success Rate</div>
                                </div>
                                <div className="evac-stat-card evac-stat-muted">
                                    <Clock size={16} />
                                    <div className="evac-stat-val">{ad.ga_execution_time}s</div>
                                    <div className="evac-stat-lbl">{compareActiveAlgo.toUpperCase()} Time</div>
                                </div>
                                {ad.traffic_segment_count > 0 && (
                                    <div className="evac-stat-card" style={{ background: '#ecfeff', border: '1px solid #22d3ee' }}>
                                        <span style={{ fontSize: 16 }}>🚦</span>
                                        <div className="evac-stat-val" style={{ color: '#0891b2' }}>{ad.traffic_segment_count}</div>
                                        <div className="evac-stat-lbl">Traffic Roads</div>
                                    </div>
                                )}
                            </div>

                            {ad.simulation_population > 0 && (
                                <div className="evac-sim-pop-note">
                                    <Users size={11} />
                                    <span>Simulation used <strong>{ad.simulation_population.toLocaleString()}</strong> people
                                        {ad.simulation_population < 10000 ? ' (1% test mode)' : ''}
                                    </span>
                                </div>
                            )}

                            {adTotalConsidered > 0 && (
                                <div className="evac-overall-bar-wrap">
                                    <div className="evac-overall-bar-bg">
                                        <div className="evac-overall-bar-fill" style={{ width: `${ad.success_rate_pct}%` }} />
                                    </div>
                                    <div className="evac-overall-bar-labels">
                                        <span className="evac-lbl-safe">✓ {ad.success_rate_pct}% evacuated</span>
                                        <span className="evac-lbl-risk">✗ {(100 - ad.success_rate_pct).toFixed(1)}% at risk</span>
                                    </div>
                                </div>
                            )}
                        </section>

                        {ad.total_at_risk_remaining > 0 && (
                            <div className="evac-alert">
                                <AlertTriangle size={14} />
                                <span>
                                    <strong>{ad.total_at_risk_remaining.toLocaleString()}</strong> people could not be
                                    assigned to a safe shelter. Manual rescue required.
                                </span>
                            </div>
                        )}

                        {adSortedShelters.length > 0 && (
                            <section className="panel evac-section">
                                <h3 className="panel-title"><Building2 size={13} /> Shelter Capacity
                                    <span className="panel-title-hint">— {compareActiveAlgo.toUpperCase()} assignment · click to view routes</span>
                                </h3>
                                <div className="shelter-fill-list">
                                    {adSortedShelters.map((s) => {
                                        const isSelected = selectedShelterId === s.id;
                                        const hasOccupancy = s.occupancy > 0;
                                        return (
                                            <div key={s.id}
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
                    </>
                )}
            </div>
        );
    }


    // ── Empty state — no simulation run yet ───────────────────────────────────
    if (!summary) {
        return (
            <div className="evac-empty">
                <ShieldCheck size={32} className="evac-empty-icon" />
                <p>Run a simulation to see evacuation analysis.<br />
                    Enable <strong>Evacuation Mode</strong> to scale population to 1% for faster testing.</p>
            </div>
        );
    }

    // ── Single-run summary (summary is non-null here) ─────────────────────────
    const {
        total_evacuated = 0,
        total_at_risk_remaining = 0,
        total_at_risk_initial = 0,
        simulation_population = 0,
        success_rate_pct = 0,
        ga_execution_time = 0,
        algorithm = 'GA',
        shelter_reports = [],
    } = summary;

    const totalConsidered = total_at_risk_initial || (total_evacuated + total_at_risk_remaining);

    // Sort shelters by occupancy_pct descending
    const sortedShelters = [...shelter_reports].sort((a, b) => b.occupancy_pct - a.occupancy_pct);

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
                        <div className="evac-stat-lbl">{algorithm} Time</div>
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
