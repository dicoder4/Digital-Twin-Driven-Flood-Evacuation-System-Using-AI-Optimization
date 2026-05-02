/**
 * EvacuationPanel.jsx
 * ───────────────────
 * Post-simulation analysis tab. Shows:
 *  - Overview stats (evacuated, success rate, GA time)
 *  - Clickable shelter rows → reveals routes on map for that shelter
 *  - Unreachable population alert
 */
import { useMemo, useState, useEffect } from 'react';
import { ShieldCheck, AlertTriangle, Clock, Users, Building2, MapPin, ChevronRight, ChevronDown, Trophy, Zap, Cpu, PlusCircle, Navigation, RefreshCw, BrainCircuit, Bell, Send } from 'lucide-react';
import { PanelOfExperts } from './PanelOfExperts';
import { EvacuationChat } from './EvacuationChat';
import { AlgoAnalysisPopup } from './AlgoAnalysisPopup';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';
import html2canvas from 'html2canvas';


const ALGO_COLORS = {
    ga: { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', label: 'Genetic Algorithm' },
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

// ── Shelter Gap Analysis ──────────────────────────────────────────────────────
const PRIORITY_STYLE = {
    high: { bg: '#fff1f2', border: '#fda4af', badge: '#be123c', label: '⚠ HIGH' },
    medium: { bg: '#fffbeb', border: '#fcd34d', badge: '#b45309', label: '! MEDIUM' },
    low: { bg: '#f0fdf4', border: '#86efac', badge: '#15803d', label: '✓ LOW' },
};

function ShelterGapAnalysis({ suggestions = [], atRiskRemaining = 0, onRerun }) {
    const { lang } = useLanguage();
    if (!suggestions || suggestions.length === 0) return null;

    const totalSuggestedCap = suggestions.reduce((acc, s) => acc + s.suggested_capacity, 0);
    const coveragePct = atRiskRemaining > 0
        ? Math.min(100, Math.round(totalSuggestedCap / atRiskRemaining * 100))
        : 100;

    return (
        <section className="panel evac-section" style={{ borderTop: '2px solid #fda4af', marginTop: 8 }}>
            <h3 className="panel-title" style={{ color: '#be123c' }}>
                <PlusCircle size={13} /> {t('shelter_gap', lang)}
                <span className="panel-title-hint"> — {atRiskRemaining.toLocaleString()} {t('people_need_shelter', lang)}</span>
            </h3>

            {/* Coverage summary bar */}
            <div style={{
                background: '#fff1f2', border: '1px solid #fda4af', borderRadius: 6,
                padding: '6px 10px', marginBottom: 8, fontSize: 10,
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <span style={{ color: '#7f1d1d', fontWeight: 600 }}>
                        {suggestions.length} shelter{suggestions.length > 1 ? 's' : ''} identified
                    </span>
                    <span style={{ color: coveragePct >= 100 ? '#15803d' : '#b45309', fontWeight: 700 }}>
                        {coveragePct}% {t('deficit_covered', lang)}
                    </span>
                </div>
                <div style={{ background: '#fecdd3', borderRadius: 4, height: 4 }}>
                    <div style={{
                        width: `${coveragePct}%`, height: 4, borderRadius: 4,
                        background: coveragePct >= 100 ? '#16a34a' : '#e11d48',
                        transition: 'width 0.5s',
                    }} />
                </div>
                <div style={{ color: '#64748b', marginTop: 3 }}>
                    {t('total_suggested_cap', lang)} <strong>{totalSuggestedCap.toLocaleString()}</strong> &nbsp;|&nbsp;
                    {t('deficit', lang)} <strong style={{ color: '#be123c' }}>{atRiskRemaining.toLocaleString()}</strong>
                </div>
            </div>

            {/* Scrollable shelter cards */}
            <div style={{
                display: 'flex', flexDirection: 'column', gap: 6,
                maxHeight: 280, overflowY: 'auto',
                paddingRight: 2,
            }}>
                {suggestions.map((s, idx) => {
                    const ps = PRIORITY_STYLE[s.priority] || PRIORITY_STYLE.medium;
                    return (
                        <div key={idx} style={{
                            background: ps.bg,
                            border: `1px solid ${ps.border}`,
                            borderRadius: 7,
                            padding: '7px 9px',
                            flexShrink: 0,
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 3 }}>
                                <span style={{ fontWeight: 700, fontSize: 10.5, color: '#1e293b', lineHeight: 1.3 }}>
                                    <Navigation size={9} style={{ verticalAlign: 'middle', marginRight: 3 }} />
                                    Shelter {idx + 1} — {s.area_name}
                                </span>
                                <span style={{
                                    fontSize: 8.5, fontWeight: 700, color: '#fff', flexShrink: 0,
                                    background: ps.badge, borderRadius: 4,
                                    padding: '1px 5px', letterSpacing: '0.04em', marginLeft: 6,
                                }}>{ps.label}</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 10px', fontSize: 9.5, color: '#475569' }}>
                                <div>
                                    <div style={{ fontSize: 7, fontWeight: 700, color: '#94a3b8', marginBottom: 1 }}>DEFICIT</div>
                                    <span><Users size={8} style={{ verticalAlign: 'middle' }} /> <strong style={{ color: '#be123c' }}>{s.deficit_population.toLocaleString()}</strong></span>
                                </div>
                                <div>
                                    <div style={{ fontSize: 7, fontWeight: 700, color: '#94a3b8', marginBottom: 1 }}>CAPACITY</div>
                                    <span><Building2 size={8} style={{ verticalAlign: 'middle' }} /> <strong>{s.suggested_capacity.toLocaleString()}</strong></span>
                                </div>
                                <div>
                                    <div style={{ fontSize: 7, fontWeight: 700, color: '#94a3b8', marginBottom: 1 }}>COORDS</div>
                                    <span><MapPin size={8} style={{ verticalAlign: 'middle' }} /> {s.lat.toFixed(4)}, {s.lon.toFixed(4)}</span>
                                </div>
                                <div>
                                    <div style={{ fontSize: 7, fontWeight: 700, color: '#94a3b8', marginBottom: 1 }}>PROXIMITY</div>
                                    <span>Nearest: <strong>{s.nearest_shelter_km} km</strong></span>
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Re-run button */}
            {onRerun && (
                <button
                    onClick={() => onRerun(suggestions)}
                    style={{
                        marginTop: 10, width: '100%', display: 'flex', alignItems: 'center',
                        justifyContent: 'center', gap: 6, padding: '8px 12px',
                        background: 'linear-gradient(135deg, #be123c, #e11d48)',
                        color: '#fff', border: 'none', borderRadius: 8,
                        fontSize: 11, fontWeight: 700, cursor: 'pointer',
                        boxShadow: '0 2px 8px rgba(190,18,60,0.3)',
                        transition: 'opacity 0.2s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
                    onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                >
                    <RefreshCw size={12} />
                    Re-run with {suggestions.length} Emergency Shelter{suggestions.length > 1 ? 's' : ''} → Evacuate All
                </button>
            )}
            <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 5 }}>
                💡 Re-run adds all {suggestions.length} shelter{suggestions.length > 1 ? 's' : ''} as emergency sites on dry ground and restarts the algorithm to evacuate remaining {atRiskRemaining.toLocaleString()} people.
            </div>
        </section>
    );
}


export function EvacuationPanel({ locationName, summary, evacuationMode, selectedShelterId, onSelectShelter, trafficSegmentCount = 0, showTraffic = false, compareResults = null, compareActiveAlgo = null, onSetCompareAlgo = null, isDraMode = false, evacuationPlan = [], onRerunWithSuggestions = null, simulationParams = {}, user = null, floodData = null, roadsData = null, trafficRoadsData = null, metroLines = null, metroStations = [], busManifest = null }) {
    const { lang } = useLanguage();
    const [genaiOpen, setGenaiOpen] = useState(false);
    const [notifyLoading, setNotifyLoading] = useState(false);

    const handleNotifyActions = async (targetSummary, targetPlan) => {
        setNotifyLoading(true);
        try {
            // Use existing html2canvas logic if map exists, else null
            let mapBase64 = null;
            const mapEl = document.querySelector('.map-container') || document.querySelector('.maplibregl-map');
            if (mapEl) {
                const canvas = await html2canvas(mapEl, { useCORS: true, backgroundColor: null });
                mapBase64 = canvas.toDataURL('image/jpeg', 0.6).split(',')[1];
            }

            const isAuthority = user?.role === 'authority';
            const endpoint = isAuthority ? '/api/notifications/sos' : '/api/notifications/notify-authorities';
            const url = `http://localhost:8000${endpoint}`;

            const payload = {
                user_data: user || { name: 'Guest', role: 'guest' },
                researcher_data: user || { name: 'Guest', role: 'guest' },
                evacuation_data: { ...targetSummary, algorithm: targetSummary.algorithm || 'AI Computed' },
                location_data: { location_name: locationName, lat: 12.9716, lon: 77.5946 },
                map_image_base64: mapBase64,
                ai_report: isAuthority ? 'Emergency Mass SOS Broadcast Initiated.' : 'Please review evacuation metrics.',
                map_state: {
                    flood_geojson: floodData,
                    roads_geojson: roadsData,
                    traffic_geojson: trafficRoadsData,
                    metro_geojson: metroLines,
                    metro_stations: metroStations,
                    bus_manifest: busManifest,
                    evacuation_plan: targetPlan,
                },
                simulation_params: simulationParams,
                frontend_base_url: window.location.origin
            };

            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) throw new Error('Failed to send notification');
            alert(isAuthority ? 'Mass SOS Broadcasted successfully.' : 'Authorities Notified successfully.');
        } catch (err) {
            console.error('Notification error:', err);
            alert('Failed to send notification: ' + err.message);
        } finally {
            setNotifyLoading(false);
        }
    };

    // ── Analysis Logic ──
    const [analysisOpen, setAnalysisOpen] = useState(false);
    const [analysisMetrics, setAnalysisMetrics] = useState(null);
    const [isAnalysing, setIsAnalysing] = useState(false);
    const [analysisProgress, setAnalysisProgress] = useState('');
    const [deepAnalysis, setDeepAnalysis] = useState(false);
    const [lastAnalysisWasDeep, setLastAnalysisWasDeep] = useState(null);

    // Clear analysis cache if the comparison results change (new simulation)
    useEffect(() => {
        setAnalysisMetrics(null);
        setLastAnalysisWasDeep(null);
    }, [compareResults]);

    const handleRunAnalysis = () => {
        if (isAnalysing) return;

        // Instant return if we already ran it with the exact same deep analysis setting
        if (analysisMetrics && Object.keys(analysisMetrics).length === 3 && deepAnalysis === lastAnalysisWasDeep) {
            setAnalysisOpen(true);
            return;
        }

        setIsAnalysing(true);
        setAnalysisMetrics(null);
        setLastAnalysisWasDeep(deepAnalysis);
        setAnalysisProgress('Preparing flood simulation…');

        const url = new URL('http://localhost:8000/simulate-analysis');
        url.searchParams.append('hobli', locationName);
        url.searchParams.append('use_traffic', showTraffic);
        // Pass simulation params so analysis matches the user's current scenario
        if (simulationParams.rainfall_mm != null) url.searchParams.append('rainfall_mm', simulationParams.rainfall_mm);
        if (simulationParams.steps != null) url.searchParams.append('steps', simulationParams.steps);
        if (simulationParams.decay_factor != null) url.searchParams.append('decay_factor', simulationParams.decay_factor);
        if (simulationParams.population != null && simulationParams.population > 0) url.searchParams.append('population', simulationParams.population);
        if (deepAnalysis) url.searchParams.append('iterations', 100);

        const eventSource = new EventSource(url.href);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.error) {
                console.error("Analysis error:", data.error);
                setIsAnalysing(false);
                setAnalysisProgress('');
                eventSource.close();
                return;
            }

            // ── Progressive: progress message ──
            if (data.analysis_progress) {
                setAnalysisProgress(data.message || `Algorithm ${data.step}/${data.total}…`);
                return;
            }

            // ── Progressive: one algorithm completed ──
            if (data.algo_result && data.metrics) {
                setAnalysisMetrics(prev => ({ ...prev, ...data.metrics }));
                // Open the popup as soon as the first algorithm finishes
                if (!analysisOpen) setAnalysisOpen(true);
                setAnalysisProgress(`${data.algo.toUpperCase()} complete — ${3 - Object.keys(data.metrics).length > 0 ? 'running next…' : 'done'}`);
                return;
            }

            // ── Final: all algorithms done ──
            if (data.analysis_done) {
                setAnalysisMetrics(data.metrics);
                setIsAnalysing(false);
                setAnalysisProgress('');
                setAnalysisOpen(true);
                eventSource.close();
            }
        };

        eventSource.onerror = (err) => {
            console.error("Analysis SSE error:", err);
            setIsAnalysing(false);
            setAnalysisProgress('');
            eventSource.close();
        };
    };

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
            total_evacuated: activeData.total_evacuated ?? 0,
            total_at_risk_remaining: activeData.total_at_risk_remaining ?? 0,
            genuinely_unreachable: activeData.genuinely_unreachable ?? 0,
            total_at_risk_initial: activeData.total_at_risk_initial ?? 0,
            simulation_population: activeData.simulation_population ?? 0,
            success_rate_pct: activeData.success_rate_pct ?? 0,
            ga_execution_time: activeData.ga_execution_time ?? 0,
            shelter_reports: activeData.shelter_reports ?? [],
            traffic_segment_count: activeData.traffic_segment_count ?? 0,
        } : null;
        const adTotalConsidered = ad ? (ad.total_at_risk_initial || (ad.total_evacuated + ad.total_at_risk_remaining)) : 0;
        const adSortedShelters = ad ? [...ad.shelter_reports].sort((a, b) => b.occupancy_pct - a.occupancy_pct) : [];
        const adColor = compareActiveAlgo ? ALGO_COLORS[compareActiveAlgo] : null;

        return (
            <div className="evac-panel">
                <section className="panel evac-section">
                    <h3 className="panel-title"><Trophy size={13} /> {t('algo_comparison', lang)}</h3>

                    {/* Route selector hint */}
                    <div className="compare-route-hint">
                        <MapPin size={10} /> Click <strong>{t('show_routes', lang)}</strong> on any row to view that algorithm's evacuation plan on the map
                    </div>

                    <div className="compare-table">
                        <div className="compare-header">
                            <span>Algorithm</span>
                            <span title="Lower is better — total flood-weighted distance + time cost for all evacuees">{t('fitness_col', lang)}</span>
                            <span>{t('success_pct_col', lang)}</span>
                            <span>{t('time_col', lang)}</span>
                        </div>
                        {rows.map(({ algo, best_fitness: fit = null, success_rate_pct: rate = 0, ga_execution_time: execTime = 0, error }) => {
                            const c = ALGO_COLORS[algo];
                            const isWinner = algo === bestAlgo;
                            const isActive = algo === compareActiveAlgo;
                            const fitLabel = fit != null
                                ? (fit >= 1_000_000 ? `${(fit / 1_000_000).toFixed(2)}M`
                                    : fit >= 1_000 ? `${(fit / 1_000).toFixed(1)}k`
                                        : String(fit))
                                : '—';
                            return (
                                <div key={algo}>
                                    <div
                                        className={`compare-row ${isWinner ? 'compare-row--winner' : ''} ${isActive ? 'compare-row--active' : ''}`}
                                        style={{ borderLeft: `3px solid ${c.border}`, background: isActive ? c.bg : isWinner ? c.bg : undefined }}>
                                        <span className="compare-algo" style={{ color: c.text }}>
                                            {isWinner && <Trophy size={10} style={{ verticalAlign: 'middle', marginRight: 3 }} />}
                                            {algo.toUpperCase()}
                                            {isWinner && <span className="compare-winner-badge">{t('best', lang)}</span>}
                                        </span>
                                        {error
                                            ? <span className="compare-error" style={{ gridColumn: '2 / -1' }}>{t('failed', lang)}</span>
                                            : <>
                                                <span style={{ fontWeight: isWinner ? 700 : 400, color: isWinner ? c.text : undefined }}>{fitLabel}</span>
                                                <span className={rate >= 80 ? 'compare-rate-good' : rate >= 50 ? 'compare-rate-warn' : 'compare-rate-bad'}>
                                                    {rate}%
                                                </span>
                                                <span>{execTime}s</span>
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
                                            {isActive ? `${t('showing_routes', lang)} (${algo.toUpperCase()})` : `${t('show_routes', lang)} (${algo.toUpperCase()})`}
                                            {isActive && <span className="compare-route-active-dot" />}
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {bestAlgo && (
                        <div className="compare-verdict">
                            <Zap size={12} style={{ color: ALGO_COLORS[bestAlgo].text }} />
                            <strong style={{ color: ALGO_COLORS[bestAlgo].text }}>{bestAlgo.toUpperCase()}</strong> found the lowest-cost evacuation plan
                            (fitness&nbsp;=&nbsp;{compareResults[bestAlgo]?.best_fitness?.toLocaleString()})
                        </div>
                    )}
                    <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 4 }}>
                        Fitness = flood-weighted distance + travel time + overflow penalty (lower = better routes)
                    </div>

                    <button
                        className={`analyse-algos-btn ${isAnalysing ? 'analysing' : ''}`}
                        onClick={handleRunAnalysis}
                        disabled={isAnalysing}
                    >
                        {isAnalysing ? (
                            <><RefreshCw size={12} className="spin" /> {analysisProgress || t('calculating_stability', lang)}</>
                        ) : (
                            <><BrainCircuit size={12} /> {t('analyse_algo', lang)}{deepAnalysis ? ' (100 iter)' : ''}</>
                        )}
                        <ChevronRight size={12} />
                    </button>
                    <label
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            fontSize: 9.5, color: '#64748b', marginTop: 5,
                            cursor: isAnalysing ? 'not-allowed' : 'pointer',
                            opacity: isAnalysing ? 0.5 : 1,
                        }}
                    >
                        <input
                            type="checkbox"
                            checked={deepAnalysis}
                            onChange={e => setDeepAnalysis(e.target.checked)}
                            disabled={isAnalysing}
                            style={{ accentColor: '#7c3aed', width: 13, height: 13, cursor: 'inherit' }}
                        />
                        <span>
                            <strong style={{ color: '#7c3aed' }}>{t('deep_analysis', lang)}</strong> — 100 iterations per algorithm
                            <span style={{ color: '#94a3b8' }}> (slower, better for ACO pheromone convergence)</span>
                        </span>
                    </label>
                </section>

                <AlgoAnalysisPopup
                    isOpen={analysisOpen}
                    onClose={() => setAnalysisOpen(false)}
                    metrics={analysisMetrics}
                    locationName={locationName}
                />

                {/* ── Per-algo detail view (appears when an algo is active) ────── */}
                {ad && adColor && (
                    <>
                        <section className="panel evac-section" style={{ borderTop: `2px solid ${adColor.border}` }}>
                            <h3 className="panel-title" style={{ color: adColor.text }}>
                                <ShieldCheck size={13} /> {compareActiveAlgo.toUpperCase()} — {t('evac_overview', lang)}
                            </h3>

                            <div className="evac-stat-grid">
                                <div className="evac-stat-card evac-stat-green">
                                    <Users size={16} />
                                    <div className="evac-stat-val">{ad.total_evacuated.toLocaleString()}</div>
                                    <div className="evac-stat-lbl">{t('evacuated', lang)}</div>
                                </div>
                                {((ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 || ad.genuinely_unreachable === 0) && (
                                    <div className={`evac-stat-card ${(ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 ? 'evac-stat-orange' : 'evac-stat-green'}`} style={(ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 ? { border: '1px solid #fdba74', background: '#fff7ed' } : {}}>
                                        <Users size={16} color={(ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 ? "#f97316" : undefined} />
                                        <div className="evac-stat-val" style={{ color: (ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 ? '#c2410c' : undefined }}>{(ad.total_at_risk_remaining - ad.genuinely_unreachable).toLocaleString()}</div>
                                        <div className="evac-stat-lbl" style={{ color: (ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 ? '#ea580c' : undefined }}>{ad.genuinely_unreachable > 0 ? t('at_risk', lang) + ' (Cap)' : t('at_risk', lang)}</div>
                                    </div>
                                )}
                                {ad.genuinely_unreachable > 0 && (
                                    <div className="evac-stat-card evac-stat-red" style={{ background: '#fef2f2', border: '1px solid #fecaca' }}>
                                        <AlertTriangle size={16} color="#dc2626" />
                                        <div className="evac-stat-val" style={{ color: '#b91c1c' }}>{ad.genuinely_unreachable.toLocaleString()}</div>
                                        <div className="evac-stat-lbl" style={{ color: '#ef4444' }}>{t('needs_rescue', lang)}</div>
                                    </div>
                                )}
                                <div className="evac-stat-card evac-stat-blue">
                                    <ShieldCheck size={16} />
                                    <div className="evac-stat-val">{ad.success_rate_pct}%</div>
                                    <div className="evac-stat-lbl">{t('success_rate', lang)}</div>
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
                                        <div className="evac-stat-lbl">{t('traffic_roads', lang)}</div>
                                    </div>
                                )}
                            </div>

                            {ad.simulation_population > 0 && (
                                <div className="evac-sim-pop-note">
                                    <Users size={11} />
                                    <span>Simulation used <strong>{ad.simulation_population.toLocaleString()}</strong> people
                                        {evacuationMode ? ' (1% test mode)' : ''}
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

                        {/* Shelter gap analysis — only when coverage is incomplete */}
                        {(ad.total_at_risk_remaining - ad.genuinely_unreachable) > 0 && (
                            <ShelterGapAnalysis
                                suggestions={ad.shelter_suggestions || []}
                                atRiskRemaining={ad.total_at_risk_remaining - ad.genuinely_unreachable}
                                onRerun={onRerunWithSuggestions}
                            />
                        )}

                        {/* ── Manual Rescue Alert — added to Compare Mode ───────────────────── */}
                        {ad.genuinely_unreachable > 0 && (
                            <section className="panel evac-section" style={{ borderTop: '2px solid #fecaca', marginTop: 8 }}>
                                <h3 className="panel-title" style={{ color: '#b91c1c' }}>
                                    <AlertTriangle size={13} /> {t('manual_rescue', lang)}
                                    <span className="panel-title-hint"> — {ad.genuinely_unreachable.toLocaleString()} {t('people_stranded', lang)}</span>
                                </h3>
                                <div style={{ fontSize: 10, color: '#7f1d1d', marginBottom: 2, lineHeight: 1.5, background: '#fef2f2', padding: 8, borderRadius: 6, border: '1px solid #fca5a5' }}>
                                    <strong>{t('isolation_detected', lang)}</strong> {ad.genuinely_unreachable.toLocaleString()} people are completely surrounded by floodwater deeper than the 0.15m (6-inch) safe wading limit.
                                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid #fecaca' }}>
                                        {t('dispatch_rescue', lang)}
                                    </div>
                                </div>
                            </section>
                        )}

                        {adSortedShelters.length > 0 && (
                            <section className="panel evac-section">
                                <h3 className="panel-title"><Building2 size={13} /> {t('shelter_capacity', lang)}
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

                {/* ── Emergency Actions (Compare Mode) ────────────────── */}
                {ad && user?.role === 'authority' && (
                    <section className="panel evac-section" style={{ borderTop: '2px solid #fecaca', marginTop: 8, paddingBottom: 12 }}>
                        <h3 className="panel-title" style={{ color: '#b91c1c' }}>
                            <Bell size={13} /> {t('emergency_actions', lang)}
                        </h3>
                        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                            <button
                                onClick={() => handleNotifyActions(ad, compareResults[compareActiveAlgo]?.evacuation_plan ?? [])}
                                disabled={notifyLoading}
                                style={{
                                    flex: 1,
                                    background: user.role === 'authority' ? '#ef4444' : '#f59e0b',
                                    color: '#fff', border: 'none', borderRadius: '6px',
                                    cursor: notifyLoading ? 'not-allowed' : 'pointer',
                                    padding: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    gap: '6px', fontSize: '13px', fontWeight: 600,
                                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                                    opacity: notifyLoading ? 0.7 : 1,
                                    animation: user.role === 'authority' && !notifyLoading ? 'pulse 2s infinite' : 'none'
                                }}>
                                {notifyLoading ? t('processing', lang) : (
                                    <>
                                        <Send size={14} />
                                        {user.role === 'authority' ? t('broadcast_sos', lang) : t('notify_authorities', lang)}
                                    </>
                                )}
                            </button>
                        </div>
                    </section>
                )}

                {/* ── GenAI Agent (compare mode) ─────────────────── */}
                {ad && (
                    <section className="panel evac-section genai-dropdown">
                        <button
                            className="genai-dropdown-toggle"
                            onClick={() => setGenaiOpen(prev => !prev)}
                        >
                            <span className="genai-dropdown-title">
                                <Cpu size={14} />
                                {t('genai_agent', lang)}
                            </span>
                            <ChevronDown
                                size={14}
                                className={`genai-chevron ${genaiOpen ? 'genai-chevron--open' : ''}`}
                            />
                        </button>
                        {genaiOpen && (
                            <div className="genai-dropdown-content">
                                <PanelOfExperts
                                    locationName={locationName}
                                    summary={ad}
                                    evacuationPlan={compareActiveAlgo ? (compareResults[compareActiveAlgo]?.evacuation_plan ?? []) : []}
                                />
                                <EvacuationChat context={{
                                    mode: 'compare',
                                    active_algo: compareActiveAlgo,
                                    // Strip the heavy geojson/plan data so context doesn't explode
                                    summaries: Object.keys(compareResults).reduce((acc, k) => {
                                        const { evacuation_plan, traffic_geojson, ...rest } = compareResults[k];
                                        acc[k] = rest;
                                        return acc;
                                    }, {})
                                }} />
                            </div>
                        )}
                    </section>
                )}
            </div>
        );
    }


    // ── Empty state — no simulation run yet ───────────────────────────────────
    if (!summary) {
        return (
            <div className="evac-empty">
                <ShieldCheck size={32} className="evac-empty-icon" />
                <p>{t('run_sim_to_see', lang)}<br />
                    Enable <strong>{t('evac_mode', lang)}</strong> to scale population to 1% for faster testing.</p>
            </div>
        );
    }

    // ── Single-run summary (summary is non-null here) ─────────────────────────
    const {
        total_evacuated = 0,
        total_at_risk_remaining = 0,
        genuinely_unreachable = 0,
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
                <h3 className="panel-title"><ShieldCheck size={13} /> {t('evac_overview', lang)}</h3>

                <div className="evac-stat-grid">
                    <div className="evac-stat-card evac-stat-green">
                        <Users size={16} />
                        <div className="evac-stat-val">{total_evacuated.toLocaleString()}</div>
                        <div className="evac-stat-lbl">{t('evacuated', lang)}</div>
                    </div>
                    {((total_at_risk_remaining - genuinely_unreachable) > 0 || genuinely_unreachable === 0) && (
                        <div className={`evac-stat-card ${(total_at_risk_remaining - genuinely_unreachable) > 0 ? 'evac-stat-orange' : 'evac-stat-green'}`} style={(total_at_risk_remaining - genuinely_unreachable) > 0 ? { border: '1px solid #fdba74', background: '#fff7ed' } : {}}>
                            <Users size={16} color={(total_at_risk_remaining - genuinely_unreachable) > 0 ? "#f97316" : undefined} />
                            <div className="evac-stat-val" style={{ color: (total_at_risk_remaining - genuinely_unreachable) > 0 ? '#c2410c' : undefined }}>{(total_at_risk_remaining - genuinely_unreachable).toLocaleString()}</div>
                            <div className="evac-stat-lbl" style={{ color: (total_at_risk_remaining - genuinely_unreachable) > 0 ? '#ea580c' : undefined }}>{genuinely_unreachable > 0 ? t('at_risk', lang) + ' (Cap)' : t('at_risk', lang)}</div>
                        </div>
                    )}
                    {genuinely_unreachable > 0 && (
                        <div className="evac-stat-card evac-stat-red" style={{ background: '#fef2f2', border: '1px solid #fecaca' }}>
                            <AlertTriangle size={16} color="#dc2626" />
                            <div className="evac-stat-val" style={{ color: '#b91c1c' }}>{genuinely_unreachable.toLocaleString()}</div>
                            <div className="evac-stat-lbl" style={{ color: '#ef4444' }}>{t('needs_rescue', lang)}</div>
                        </div>
                    )}
                    <div className="evac-stat-card evac-stat-blue">
                        <ShieldCheck size={16} />
                        <div className="evac-stat-val">{success_rate_pct}%</div>
                        <div className="evac-stat-lbl">{t('success_rate', lang)}</div>
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
                            <div className="evac-stat-lbl">{t('traffic_roads', lang)}</div>
                        </div>
                    )}
                </div>

                {simulation_population > 0 && (
                    <div className="evac-sim-pop-note">
                        <Users size={11} />
                        <span>Simulation used <strong>{simulation_population.toLocaleString()}</strong> people
                            {evacuationMode ? ' (1% test mode)' : ''}
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

            {/* ── Emergency Actions (Single Mode) ──────────────────── */}
            {summary && user?.role === 'authority' && (
                <section className="panel evac-section" style={{ borderTop: '2px solid #fecaca', marginTop: 8, paddingBottom: 12 }}>
                    <h3 className="panel-title" style={{ color: '#b91c1c' }}>
                        <Bell size={13} /> {t('emergency_actions', lang)}
                    </h3>
                    <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                        <button
                            onClick={() => handleNotifyActions(summary, evacuationPlan)}
                            disabled={notifyLoading}
                            style={{
                                flex: 1,
                                background: user.role === 'authority' ? '#ef4444' : '#f59e0b',
                                color: '#fff', border: 'none', borderRadius: '6px',
                                cursor: notifyLoading ? 'not-allowed' : 'pointer',
                                padding: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                gap: '6px', fontSize: '13px', fontWeight: 600,
                                boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                                opacity: notifyLoading ? 0.7 : 1,
                                animation: user.role === 'authority' && !notifyLoading ? 'pulse 2s infinite' : 'none'
                            }}>
                            {notifyLoading ? t('processing', lang) : (
                                <>
                                    <Send size={14} />
                                    {user.role === 'authority' ? t('broadcast_sos', lang) : t('notify_authorities', lang)}
                                </>
                            )}
                        </button>
                    </div>
                </section>
            )}

            {/* ── GenAI Agent ────────────────────────────────── */}
            {summary && (
                <section className="panel evac-section genai-dropdown">
                    <button
                        className="genai-dropdown-toggle"
                        onClick={() => setGenaiOpen(prev => !prev)}
                    >
                        <span className="genai-dropdown-title">
                            <Cpu size={14} />
                            {t('genai_agent', lang)}
                        </span>
                        <ChevronDown
                            size={14}
                            className={`genai-chevron ${genaiOpen ? 'genai-chevron--open' : ''}`}
                        />
                    </button>
                    {genaiOpen && (
                        <div className="genai-dropdown-content">
                            <PanelOfExperts
                                locationName={locationName}
                                summary={summary}
                                evacuationPlan={evacuationPlan}
                            />
                            <EvacuationChat context={summary} evacuationPlan={evacuationPlan} />
                        </div>
                    )}
                </section>
            )}

            {/* ── Shelter Gap Analysis ──────────────────── */}
            <ShelterGapAnalysis
                suggestions={summary.shelter_suggestions || []}
                atRiskRemaining={total_at_risk_remaining - genuinely_unreachable}
                onRerun={onRerunWithSuggestions}
            />

            {/* ── Manual Rescue Alert ───────────────────── */}
            {genuinely_unreachable > 0 && (
                <section className="panel evac-section" style={{ borderTop: '2px solid #fecaca', marginTop: 8 }}>
                    <h3 className="panel-title" style={{ color: '#b91c1c' }}>
                        <AlertTriangle size={13} /> {t('manual_rescue', lang)}
                        <span className="panel-title-hint"> — {genuinely_unreachable.toLocaleString()} {t('people_stranded', lang)}</span>
                    </h3>
                    <div style={{ fontSize: 10, color: '#7f1d1d', marginBottom: 2, lineHeight: 1.5, background: '#fef2f2', padding: 8, borderRadius: 6, border: '1px solid #fca5a5' }}>
                        <strong>{t('isolation_detected', lang)}</strong> {genuinely_unreachable.toLocaleString()} people are completely surrounded by floodwater deeper than the 0.15m (6-inch) safe wading limit.
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid #fecaca' }}>
                            {t('dispatch_rescue', lang)}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Shelter Fill Report (clickable) ───────── */}
            {sortedShelters.length > 0 && (
                <section className="panel evac-section">
                    <h3 className="panel-title"><Building2 size={13} /> {t('shelter_capacity', lang)}
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
