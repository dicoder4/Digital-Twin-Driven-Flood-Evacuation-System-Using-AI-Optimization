/**
 * App.jsx — Orchestrator
 * Composes hooks and components. Owns top-level state only.
 */
import { useState, useCallback } from 'react';
import { Droplets, Activity } from 'lucide-react';
import axios from 'axios';

import { useRegions } from './hooks/useRegions';
import { useSimulation } from './hooks/useSimulation';
import { RegionSelector } from './components/RegionSelector';
import { RainfallPanel } from './components/RainfallPanel';
import { SimulationControls } from './components/SimulationControls';
import { FloodMap } from './components/FloodMap';
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
  const [selRec, setSelRec] = useState(null);  // current historical record

  // Sim params
  const [rainfallMm, setRainfallMm] = useState(150);
  const [steps, setSteps] = useState(20);
  const [decayFactor, setDecayFactor] = useState(0.5);

  // Hooks
  const regions = useRegions();
  const sim = useSimulation();

  // ── Load Region ───────────────────────────────────────────────────────────
  const handleLoadRegion = useCallback(async () => {
    if (!regions.selHobli) return;
    setRegionLoading(true);
    sim.setStatusMsg(`Loading ${regions.selHobli} …`);
    sim.clearMap();

    try {
      const res = await axios.post(`${API_URL}/load-region`, { hobli: regions.selHobli });
      const { lat, lon } = res.data;
      setViewState(v => ({ ...v, longitude: lon, latitude: lat, zoom: 14 }));

      const mapRes = await axios.get(`${API_URL}/map-data`, { params: { hobli: regions.selHobli } });
      setBaseRoadsData(mapRes.data);

      setLoadedHobli(regions.selHobli);
      setRegionLoaded(true);
      setSelRec(null);
      sim.setStatusMsg(`${regions.selHobli} ready. Configure and run.`);
    } catch (err) {
      sim.setStatusMsg(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setRegionLoading(false);
    }
  }, [regions.selHobli, sim]);

  // When district/taluk/hobli changes, unload region
  const handleDistrict = (d) => { regions.setDistrict(d); setRegionLoaded(false); sim.reset(); };
  const handleTaluk = (t) => { regions.setTaluk(t); setRegionLoaded(false); sim.reset(); };
  const handleHobli = (h) => { regions.setHobli(h); setRegionLoaded(false); sim.reset(); };

  // ── Start simulation ───────────────────────────────────────────────────────
  const handleStart = () => {
    if (!regionLoaded) return;
    sim.start(loadedHobli, rainfallMm, steps, decayFactor);
  };

  return (
    <div className="app-container">
      {/* ─── Sidebar ─────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <Droplets size={20} className="icon-blue" />
          <div>
            <div className="sidebar-title">Urban Flood Model</div>
            <div className="sidebar-sub">Drain-based Simulation</div>
          </div>
        </div>

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
            <RainfallPanel
              loadedHobli={loadedHobli}
              rainfallMm={rainfallMm}
              onRainfallChange={setRainfallMm}
            />
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
          </>
        )}

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
      />
    </div>
  );
}
