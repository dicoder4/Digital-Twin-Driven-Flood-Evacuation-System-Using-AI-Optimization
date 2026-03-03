/**
 * App.jsx — Orchestrator
 * Composes hooks and components. Owns top-level state only.
 *
 * Flow: District → Taluk → Hobli → Load Region
 *       → Population panel (people first)
 *       → Rainfall panel   (configure rainfall)
 *       → Optimisation Settings (algorithm + traffic — always visible)
 *       → Evacuation Mode toggle (1% pop scaling — independent)
 *       → Simulation Controls → Run flood sim
 *       → Evacuation tab: analysis shown after simulation completes
 */
import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { Droplets, Activity, Route, GitCompare, Zap, Radio, Info } from 'lucide-react';
import axios from 'axios';

import { useRegions }      from './hooks/useRegions';
import { useSimulation }   from './hooks/useSimulation';
import { RegionSelector }  from './components/RegionSelector';
import { PopulationPanel } from './components/PopulationPanel';
import { RainfallPanel }   from './components/RainfallPanel';
import { SimulationControls } from './components/SimulationControls';
import { SheltersPanel }   from './components/SheltersPanel';
import { EvacuationPanel } from './components/EvacuationPanel';
import { FloodMap }        from './components/FloodMap';
import { computeShelterSafety } from './utils/geoUtils';
import { API_URL } from './config';   // ← ESM import (no require() anywhere)
import './App.css';

export default function App() {
  // ── Map viewport ─────────────────────────────────────────────
  const [viewState, setViewState] = useState({
    longitude: 77.5946, latitude: 12.9716, zoom: 10,
  });

  // ── Region state ─────────────────────────────────────────────
  const [regionLoading, setRegionLoading]   = useState(false);
  const [regionLoaded,  setRegionLoaded]    = useState(false);
  const [loadedHobli,   setLoadedHobli]     = useState('');
  const [baseRoadsData, setBaseRoadsData]   = useState(null);
  const [selRec,        setSelRec]          = useState(null);

  // ── Population / shelter state ────────────────────────────────
  const [populationCount,   setPopulationCount]   = useState(0);
  const [unsafePeopleCount, setUnsafePeopleCount] = useState(0);
  const [shelterCandidates, setShelterCandidates] = useState([]);

  // ── Simulation params ─────────────────────────────────────────
  const [rainfallMm,    setRainfallMm]    = useState(150);
  const [steps,         setSteps]         = useState(20);
  const [decayFactor,   setDecayFactor]   = useState(0.5);
  const [algoInfoOpen,  setAlgoInfoOpen]  = useState(false);

  // ── Three independent toggles / selectors ────────────────────
  // 1. Evacuation Mode — ONLY controls 1% population scaling
  const [evacuationMode, setEvacuationMode] = useState(false);
  // 2. Live Traffic — whether TomTom data modifies the road graph
  const [useTraffic,     setUseTraffic]     = useState(false);
  // 3. Algorithm — which optimiser runs (always runs, not gated by evac mode)
  const [algorithm,      setAlgorithm]      = useState('ga');

  // ── Compare mode ──────────────────────────────────────────────
  const [compareMode,       setCompareMode]       = useState(false);
  const [compareResults,    setCompareResults]    = useState(null);  // {ga, aco, pso}
  const [compareRunning,    setCompareRunning]    = useState(false);
  const [compareProgress,   setCompareProgress]   = useState('');
  const [compareActiveAlgo, setCompareActiveAlgo] = useState(null);  // which algo's routes to show
  // Abort ref — allows cancelling compare mid-run
  const compareAbortRef = useRef(false);

  // ── UI state ──────────────────────────────────────────────────
  const [activeTab,        setActiveTab]        = useState('setup');
  const [selectedShelterId, setSelectedShelterId] = useState(null);
  const [showTrafficPins,   setShowTrafficPins]   = useState(false);

  // ── Hooks ─────────────────────────────────────────────────────
  const regions = useRegions();
  const sim     = useSimulation();

  // Recompute shelter safety on every flood update
  const sheltersWithSafety = useMemo(
    () => computeShelterSafety(shelterCandidates, sim.floodData),
    [shelterCandidates, sim.floodData],
  );

  // 1% display population when evacuation mode is ON
  const displayPopulation = evacuationMode
    ? Math.max(1, Math.floor(populationCount / 100))
    : populationCount;

  const selectedShelter = useMemo(
    () => selectedShelterId
      ? sheltersWithSafety.find(s => s.id === selectedShelterId) || null
      : null,
    [selectedShelterId, sheltersWithSafety],
  );

  // ── Load Region ───────────────────────────────────────────────
  const handleLoadRegion = useCallback(async () => {
    if (!regions.selHobli) return;
    setRegionLoading(true);
    sim.setStatusMsg(`Loading ${regions.selHobli} …`);
    sim.clearMap();
    setPopulationCount(0);
    setUnsafePeopleCount(0);
    setShelterCandidates([]);
    setActiveTab('setup');
    try {
      const res    = await axios.post(`${API_URL}/load-region`, { hobli: regions.selHobli });
      const { lat, lon } = res.data;
      setViewState(v => ({ ...v, longitude: lon, latitude: lat, zoom: 14 }));
      const mapRes = await axios.get(`${API_URL}/map-data`, { params: { hobli: regions.selHobli } });
      setBaseRoadsData(mapRes.data);
      setLoadedHobli(regions.selHobli);
      setRegionLoaded(true);
      setSelRec(null);
      sim.setStatusMsg(`${regions.selHobli} ready. Configure simulation and run.`);
    } catch (err) {
      sim.setStatusMsg(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setRegionLoading(false);
    }
  }, [regions.selHobli, sim]);

  const handleDistrict = (d) => { regions.setDistrict(d); setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };
  const handleTaluk    = (t) => { regions.setTaluk(t);    setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };
  const handleHobli    = (h) => { regions.setHobli(h);    setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };

  // ── Start single simulation ───────────────────────────────────
  const handleStart = () => {
    if (!regionLoaded) return;
    setCompareResults(null);
    setActiveTab('setup');
    sim.start(loadedHobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic, algorithm);
  };

  // ── Reset everything ──────────────────────────────────────────
  const handleReset = () => {
    compareAbortRef.current = true;   // signal any running compare to stop
    sim.reset();
    setCompareResults(null);
    setCompareRunning(false);
    setCompareProgress('');
    setCompareActiveAlgo(null);
  };

  // ── Compare Mode: run GA → ACO → PSO sequentially ─────────────
  // BUG FIX: was using require('./config') which is CommonJS and fails
  // in Vite/ESM → EventSource URL was never built → promise never resolved
  // → page appeared frozen. Now uses the ESM-imported API_URL directly.
  const handleCompare = useCallback(async () => {
    if (!regionLoaded || compareRunning) return;
    compareAbortRef.current = false;
    setCompareResults(null);
    setCompareRunning(true);
    const results = {};
    const algos = ['ga', 'aco', 'pso'];

    for (let i = 0; i < algos.length; i++) {
      const algo = algos[i];

      // Allow cancellation between rounds
      if (compareAbortRef.current) break;

      setCompareProgress(`Running ${algo.toUpperCase()} (${i + 1}/3)…`);
      sim.setStatusMsg(`Compare: running ${algo.toUpperCase()} (${i + 1} of 3)…`);

      await new Promise((resolve) => {
        const params = new URLSearchParams({
          hobli:           loadedHobli,
          rainfall_mm:     rainfallMm,
          steps,
          decay_factor:    decayFactor,
          evacuation_mode: evacuationMode,
          use_traffic:     useTraffic,
          algorithm:       algo,
        });

        // ✅ Use already-imported ESM API_URL — NOT require()
        const es = new EventSource(`${API_URL}/simulate-stream?${params}`);

        // Safety timeout — if backend hangs for >5 min, give up on this algo
        const timeout = setTimeout(() => {
          es.close();
          results[algo] = { error: true, error_msg: 'timeout' };
          resolve();
        }, 5 * 60 * 1000);

        es.onmessage = (evt) => {
          if (compareAbortRef.current) {
            clearTimeout(timeout);
            es.close();
            resolve();
            return;
          }
          try {
            const data = JSON.parse(evt.data);
            if (data.done) {
              clearTimeout(timeout);
              es.close();
              // Store summary + evacuation_plan + traffic_segment_count
              results[algo] = {
                ...(data.summary || {}),
                evacuation_plan: data.evacuation_plan || [],
                traffic_segment_count: data.traffic_segment_count || 0,
              };
              resolve();
            }
          } catch {
            // ignore malformed SSE frames
          }
        };

        es.onerror = () => {
          clearTimeout(timeout);
          es.close();
          results[algo] = { error: true };
          resolve();
        };
      });
    }

    const finalResults = Object.keys(results).length > 0 ? results : null;
    setCompareResults(finalResults);
    setCompareRunning(false);
    setCompareProgress('');

    if (!compareAbortRef.current && finalResults) {
      // Auto-select the best algo's routes on the map (lowest fitness)
      let bestAlgo = null, bestFit = Infinity;
      for (const [algo, res] of Object.entries(finalResults)) {
        const f = res.best_fitness ?? Infinity;
        if (!res.error && f < bestFit) { bestFit = f; bestAlgo = algo; }
      }
      setCompareActiveAlgo(bestAlgo);
      setActiveTab('evacuation');
      sim.setStatusMsg(`Compare complete — showing ${bestAlgo?.toUpperCase() ?? ''} routes (best fitness)`);
    } else {
      sim.setStatusMsg('Compare cancelled.');
    }
  }, [regionLoaded, compareRunning, loadedHobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic, sim]);

  // Auto-switch to Evacuation tab when single-algo sim completes
  useEffect(() => {
    if (sim.simulationDone && !compareRunning) {
      setActiveTab('evacuation');
      setSelectedShelterId(null);
      setShowTrafficPins(false);
    }
  }, [sim.simulationDone, compareRunning]);

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* ─── Sidebar ───────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <Droplets size={20} className="icon-blue" />
          <div>
            <div className="sidebar-title">Urban Flood Model</div>
            <div className="sidebar-sub">Digital Twin · Flood Simulation · Evacuation</div>
          </div>
        </div>

        {/* Tabs */}
        <div className="sidebar-tabs">
          <button
            className={`sidebar-tab ${activeTab === 'setup' ? 'active' : ''}`}
            onClick={() => setActiveTab('setup')}
          >Setup</button>
          <button
            className={`sidebar-tab evac-tab ${activeTab === 'evacuation' ? 'active' : ''}`}
            onClick={() => setActiveTab('evacuation')}
            disabled={!sim.simulationDone && !compareResults}
            title={!sim.simulationDone && !compareResults ? 'Run simulation first' : ''}
          ><Route size={11} /> Evacuation</button>
        </div>

        <div className="sidebar-content custom-scrollbar">

          {/* ── SETUP TAB ────────────────────────────────── */}
          {activeTab === 'setup' && (
            <>
              <RegionSelector
                districts={regions.districts}
                taluks={regions.taluks}
                hoblis={regions.hoblis}
                selDistrict={regions.selDistrict}
                selTaluk={regions.selTaluk}
                selHobli={regions.selHobli}
                onDistrict={handleDistrict}
                onTaluk={handleTaluk}
                onHobli={handleHobli}
                onLoad={handleLoadRegion}
                loading={regionLoading}
                loaded={regionLoaded}
                loadedHobli={loadedHobli}
              />

              {regionLoaded && (
                <>
                  <PopulationPanel
                    loadedHobli={loadedHobli}
                    onPopulationSet={setPopulationCount}
                  />

                  <SheltersPanel
                    loadedHobli={loadedHobli}
                    shelters={sheltersWithSafety.length ? sheltersWithSafety : null}
                    onCandidates={setShelterCandidates}
                  />

                  <RainfallPanel
                    loadedHobli={loadedHobli}
                    rainfallMm={rainfallMm}
                    onRainfallChange={setRainfallMm}
                  />

                  {/* ── Panel 1: Evacuation Mode (standalone) ───── */}
                  <div className="evac-mode-toggle panel">
                    <div className="evac-toggle-row">
                      <div>
                        <div className="evac-toggle-label">Evacuation Mode</div>
                        <div className="evac-toggle-sub">Scales population to 1% for faster testing</div>
                      </div>
                      <button
                        className={`evac-toggle-btn ${evacuationMode ? 'evac-toggle-on' : ''}`}
                        onClick={() => setEvacuationMode(v => !v)}
                      >
                        <span className="evac-toggle-thumb" />
                      </button>
                    </div>
                  </div>

                  {/* ── Panel 2: Optimisation Settings (always visible) ── */}
                  <div className="panel optim-panel">
                    <h3 className="panel-title"><Zap size={13} /> Optimisation Settings</h3>

                    {/* Algorithm selector */}
                    <div className="optim-row">
                      <div className="optim-row-label">
                        <div className="evac-toggle-label">Algorithm</div>
                        <div className="evac-toggle-sub">Runs after flood simulation</div>
                      </div>
                      <div className="algo-pill-group">
                        {['ga', 'aco', 'pso'].map(a => (
                          <button
                            key={a}
                            className={`algo-pill ${algorithm === a && !compareMode ? 'algo-pill--active' : ''}`}
                            onClick={() => { setAlgorithm(a); setCompareMode(false); }}
                            disabled={compareRunning}
                            title={{ ga: 'Genetic Algorithm', aco: 'Ant Colony Optimisation', pso: 'Particle Swarm Optimisation' }[a]}
                          >{a.toUpperCase()}</button>
                        ))}
                        <button
                          className={`algo-pill algo-pill--compare ${compareMode ? 'algo-pill--active-compare' : ''}`}
                          onClick={() => setCompareMode(v => !v)}
                          title="Run all 3 algorithms sequentially and compare results"
                          disabled={compareRunning}
                        ><GitCompare size={9} /> All</button>
                      </div>
                    </div>

                    {/* ⓘ info toggle + expandable descriptions */}
                    <button
                      className={`algo-info-btn ${algoInfoOpen ? 'algo-info-btn--open' : ''}`}
                      onClick={() => setAlgoInfoOpen(v => !v)}
                      title="Learn about each algorithm"
                    >
                      <Info size={11} /> {algoInfoOpen ? 'Hide info' : 'What are these?'}
                    </button>

                    {algoInfoOpen && (
                      <div className="algo-info-panel">
                        <div className="algo-info-item" style={{ borderLeft: '3px solid #93c5fd' }}>
                          <strong style={{ color: '#1d4ed8' }}>GA</strong> — Genetic Algorithm
                          <div className="algo-info-desc">Evolves solutions using crossover &amp; mutation. Good general-purpose optimiser, occasional disruption of good sub-routes.</div>
                        </div>
                        <div className="algo-info-item" style={{ borderLeft: '3px solid #86efac' }}>
                          <strong style={{ color: '#15803d' }}>ACO</strong> — Ant Colony Optimisation
                          <div className="algo-info-desc">Ants build routes using pheromone trails. Directly minimises flood-weighted distance — best solution quality.</div>
                        </div>
                        <div className="algo-info-item" style={{ borderLeft: '3px solid #d8b4fe' }}>
                          <strong style={{ color: '#7e22ce' }}>PSO</strong> — Particle Swarm Optimisation
                          <div className="algo-info-desc">Particles swarm toward best-known solutions. Fastest convergence but can plateau early.</div>
                        </div>
                        <div className="algo-info-item" style={{ borderLeft: '3px solid #c084fc' }}>
                          <strong style={{ color: '#7c3aed' }}>⇄ All</strong> — Compare Mode
                          <div className="algo-info-desc">Runs GA → ACO → PSO sequentially on the same flood scenario. Compares fitness scores head-to-head.</div>
                        </div>
                      </div>
                    )}

                    {/* Live Traffic toggle */}
                    <div className="optim-row" style={{ marginTop: '0.5rem' }}>
                      <div className="optim-row-label">
                        <div className="evac-toggle-label"><Radio size={11} style={{ display:'inline', verticalAlign:'middle', marginRight:3 }}/>Live Traffic</div>
                        <div className="evac-toggle-sub">TomTom congestion on road graph</div>
                      </div>
                      <button
                        className={`evac-toggle-btn ${useTraffic ? 'evac-toggle-on' : ''}`}
                        onClick={() => setUseTraffic(v => !v)}
                        disabled={compareRunning}
                      >
                        <span className="evac-toggle-thumb" />
                      </button>
                    </div>

                    {/* Hint */}
                    <div className="evac-toggle-hint" style={{ marginTop: '0.4rem' }}>
                      {compareMode
                        ? '🤖 GA → ACO → PSO will run sequentially — compare results in Evacuation tab'
                        : `🚨 ${algorithm.toUpperCase()} will optimise evacuation routes after the flood simulation`
                      }
                    </div>
                  </div>

                  {/* ── Simulation Controls ─────────────────────── */}
                  <SimulationControls
                    steps={steps}
                    decayFactor={decayFactor}
                    onSteps={setSteps}
                    onDecay={setDecayFactor}
                    isRunning={sim.isRunning || compareRunning}
                    isPaused={sim.isPaused}
                    simulationDone={sim.simulationDone || !!compareResults}
                    currentStep={sim.currentStep}
                    totalSteps={sim.totalSteps}
                    elapsedTime={sim.elapsedTime}
                    progressPct={sim.progressPct}
                    onStart={compareMode ? handleCompare : handleStart}
                    onTogglePause={sim.togglePause}
                    onReset={handleReset}
                    compareMode={compareMode}
                    compareProgress={compareProgress}
                  />

                  {/* Flood Impact summary */}
                  {sim.simulationDone && populationCount > 0 && (
                    <section className="panel">
                      <h3 className="panel-title" style={{ color: '#dc2626' }}>⚠ Flood Impact</h3>
                      <div className="pop-count-row">
                        <span className="pop-count" style={{ color: '#dc2626' }}>
                          {(sim.finalReport?.summary?.total_at_risk_initial ?? unsafePeopleCount).toLocaleString()}
                        </span>
                        <span className="pop-count-label">people at risk</span>
                      </div>
                      <div className="pop-split">
                        <span style={{ color: '#16a34a' }}>✓ Safe: {((sim.finalReport?.summary?.simulation_population ?? displayPopulation) - (sim.finalReport?.summary?.total_at_risk_initial ?? unsafePeopleCount)).toLocaleString()}</span>
                        <span style={{ color: '#dc2626' }}>✗ Unsafe: {(sim.finalReport?.summary?.total_at_risk_initial ?? unsafePeopleCount).toLocaleString()}</span>
                      </div>
                      <button className="btn-evac-goto" onClick={() => setActiveTab('evacuation')}>
                        <Route size={12} /> View Evacuation Analysis →
                      </button>
                    </section>
                  )}
                </>
              )}
            </>
          )}

          {activeTab === 'evacuation' && (
            <EvacuationPanel
              summary={sim.finalReport?.summary}
              evacuationMode={evacuationMode}
              selectedShelterId={selectedShelterId}
              onSelectShelter={setSelectedShelterId}
              trafficSegmentCount={sim.trafficSegmentCount}
              showTraffic={useTraffic}
              compareResults={compareResults}
              compareActiveAlgo={compareActiveAlgo}
              onSetCompareAlgo={setCompareActiveAlgo}
            />
          )}
        </div>

        <div className="status-bar">
          <Activity size={11} />
          <span>{sim.statusMsg}</span>
        </div>
      </aside>

      {/* ─── Map ─────────────────────────────────────────── */}
      <FloodMap
        viewState={viewState}
        onMove={setViewState}
        baseRoadsData={baseRoadsData}
        floodData={sim.floodData}
        riskRoadsData={sim.roadsData}
        loadedHobli={loadedHobli}
        selRec={selRec}
        populationCount={displayPopulation}
        onUnsafeCount={setUnsafePeopleCount}
        shelters={sheltersWithSafety}
        evacuationPlan={
          compareResults && compareActiveAlgo
            ? (compareResults[compareActiveAlgo]?.evacuation_plan ?? [])
            : sim.evacuationPlan
        }
        simulationDone={sim.simulationDone || !!compareResults}
        selectedShelter={selectedShelter}
        trafficRoadsData={sim.trafficRoadsData}
        showTraffic={useTraffic && sim.simulationDone}
        showTrafficPins={showTrafficPins}
        onToggleTrafficPins={() => setShowTrafficPins(v => !v)}
      />
    </div>
  );
}
