/**
 * App.jsx — Orchestrator
 * Composes hooks and components. Owns top-level state only.
 *
 * Flow: District → Taluk → Hobli → Load Region
 *       → Population panel (people first)
 *       → Rainfall panel   (configure rainfall)
 *       → Simulation Controls → Run flood sim
 *       → Evacuation tab: GA analysis shown after simulation completes
 */
import { useState, useCallback, useMemo, useEffect } from 'react';
import { Droplets, Activity, Route } from 'lucide-react';
import axios from 'axios';

import { useRegions } from './hooks/useRegions';
import { useSimulation } from './hooks/useSimulation';
import { RegionSelector } from './components/RegionSelector';
import { PopulationPanel } from './components/PopulationPanel';
import { RainfallPanel } from './components/RainfallPanel';
import { SimulationControls } from './components/SimulationControls';
import { SheltersPanel } from './components/SheltersPanel';
import { EvacuationPanel } from './components/EvacuationPanel';
import { FloodMap } from './components/FloodMap';
import { computeShelterSafety } from './utils/geoUtils';
import { API_URL } from './config';
import './App.css';

export default function App() {
  // Map viewport
  const [viewState, setViewState] = useState({
    longitude: 77.5946, latitude: 12.9716, zoom: 10,
  });

  // Region loading state
  const [regionLoading, setRegionLoading] = useState(false);
  const [regionLoaded, setRegionLoaded] = useState(false);
  const [loadedHobli, setLoadedHobli] = useState('');
  const [baseRoadsData, setBaseRoadsData] = useState(null);
  const [selRec, setSelRec] = useState(null);

  // Population state
  const [populationCount, setPopulationCount] = useState(0);
  const [unsafePeopleCount, setUnsafePeopleCount] = useState(0);
  // Shelter state — raw candidates from backend; safety computed live
  const [shelterCandidates, setShelterCandidates] = useState([]);

  // Sim params
  const [rainfallMm, setRainfallMm] = useState(150);
  const [steps, setSteps] = useState(20);
  const [decayFactor, setDecayFactor] = useState(0.5);
  const [evacuationMode, setEvacuationMode] = useState(false);
  const [activeTab, setActiveTab] = useState('setup');

  // Selected shelter for interactive route display
  const [selectedShelterId, setSelectedShelterId] = useState(null);

  // Hooks
  const regions = useRegions();
  const sim = useSimulation();

  // Recompute shelter safety on every flood update so map updates live
  const sheltersWithSafety = useMemo(
    () => computeShelterSafety(shelterCandidates, sim.floodData),
    [shelterCandidates, sim.floodData],
  );

  // Effective display population: 1% when evac mode on (immediate visual feedback)
  const displayPopulation = evacuationMode
    ? Math.max(1, Math.floor(populationCount / 100))
    : populationCount;

  // Full shelter object for the selected shelter (has lat/lon for map pin)
  const selectedShelter = useMemo(
    () => selectedShelterId
      ? sheltersWithSafety.find(s => s.id === selectedShelterId) || null
      : null,
    [selectedShelterId, sheltersWithSafety],
  );

  // ── Load Region ───────────────────────────────────────────────────────────
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
      const res = await axios.post(`${API_URL}/load-region`, { hobli: regions.selHobli });
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
  const handleTaluk = (t) => { regions.setTaluk(t); setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };
  const handleHobli = (h) => { regions.setHobli(h); setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };

  // ── Start simulation ───────────────────────────────────────────────────────
  const handleStart = () => {
    if (!regionLoaded) return;
    setActiveTab('setup');
    sim.start(loadedHobli, rainfallMm, steps, decayFactor, evacuationMode);
  };

  // Switch to Evacuation tab automatically when simulation completes
  useEffect(() => {
    if (sim.simulationDone) {
      setActiveTab('evacuation');
      setSelectedShelterId(null); // reset selection on new sim
    }
  }, [sim.simulationDone]);

  return (
    <div className="app-container">
      {/* ─── Sidebar ─────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <Droplets size={20} className="icon-blue" />
          <div>
            <div className="sidebar-title">Urban Flood Model</div>
            <div className="sidebar-sub">Digital Twin · Flood Simulation · Evacuation</div>
          </div>
        </div>

        {/* Sidebar Tabs */}
        <div className="sidebar-tabs">
          <button
            className={`sidebar-tab ${activeTab === 'setup' ? 'active' : ''}`}
            onClick={() => setActiveTab('setup')}
          >
            Setup
          </button>

          <button
            className={`sidebar-tab evac-tab ${activeTab === 'evacuation' ? 'active' : ''}`}
            onClick={() => setActiveTab('evacuation')}
            disabled={!sim.simulationDone}
            title={!sim.simulationDone ? 'Run simulation first' : ''}
          >
            <Route size={11} /> Evacuation
          </button>
        </div>

        <div className="sidebar-content custom-scrollbar">
          {/* ── Setup Tab ────────────────────── */}
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

                  {/* Evacuation mode toggle — lives here, not in SimulationControls */}
                  <div className="evac-mode-toggle panel">
                    <div className="evac-toggle-row">
                      <div>
                        <div className="evac-toggle-label">Evacuation Mode</div>
                        <div className="evac-toggle-sub">Scales population to 1% for faster GA testing</div>
                      </div>
                      <button
                        className={`evac-toggle-btn ${evacuationMode ? 'evac-toggle-on' : ''}`}
                        onClick={() => setEvacuationMode(v => !v)}
                      >
                        <span className="evac-toggle-thumb" />
                      </button>
                    </div>
                    {evacuationMode && (
                      <div className="evac-toggle-hint">
                        🚨 GA will run after simulation — routes appear when streaming ends
                      </div>
                    )}
                  </div>

                  <SimulationControls
                    steps={steps} decayFactor={decayFactor}
                    onSteps={setSteps} onDecay={setDecayFactor}
                    isRunning={sim.isRunning} isPaused={sim.isPaused}
                    simulationDone={sim.simulationDone}
                    currentStep={sim.currentStep} totalSteps={sim.totalSteps}
                    elapsedTime={sim.elapsedTime} progressPct={sim.progressPct}
                    onStart={handleStart}
                    onTogglePause={sim.togglePause}
                    onReset={sim.reset}
                  />

                  {/* Flood Impact inline summary */}
                  {sim.simulationDone && populationCount > 0 && (
                    <section className="panel">
                      <h3 className="panel-title" style={{ color: '#dc2626' }}>⚠ Flood Impact</h3>
                      <div className="pop-count-row">
                        <span className="pop-count" style={{ color: '#dc2626' }}>
                          {unsafePeopleCount.toLocaleString()}
                        </span>
                        <span className="pop-count-label">people at risk</span>
                      </div>
                      <div className="pop-split">
                        <span style={{ color: '#16a34a' }}>✓ Safe: {(populationCount - unsafePeopleCount).toLocaleString()}</span>
                        <span style={{ color: '#dc2626' }}>✗ Unsafe: {unsafePeopleCount.toLocaleString()}</span>
                      </div>
                      {evacuationMode && sim.simulationDone && (
                        <button
                          className="btn-evac-goto"
                          onClick={() => setActiveTab('evacuation')}
                        >
                          <Route size={12} /> View Evacuation Analysis →
                        </button>
                      )}
                    </section>
                  )}
                </>
              )}
            </>
          )}



          {/* ── Evacuation Tab ───────────────── */}
          {activeTab === 'evacuation' && (
            <EvacuationPanel
              summary={sim.finalReport?.summary}
              evacuationMode={evacuationMode}
              selectedShelterId={selectedShelterId}
              onSelectShelter={setSelectedShelterId}
            />
          )}
        </div>

        <div className="status-bar">
          <Activity size={11} />
          <span>{sim.statusMsg}</span>
        </div>
      </aside>

      {/* ─── Map ─────────────────────────────────────── */}
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
        evacuationPlan={sim.evacuationPlan}
        simulationDone={sim.simulationDone}
        selectedShelter={selectedShelter}
      />
    </div>
  );
}
