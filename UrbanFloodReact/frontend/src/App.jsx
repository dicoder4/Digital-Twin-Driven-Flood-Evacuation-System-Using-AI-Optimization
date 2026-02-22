import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import Map, { Source, Layer, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import axios from 'axios';
import {
  Play, Pause, RefreshCw, Droplets, Clock, Activity, Loader,
  MapPin, ChevronDown, Calendar, BarChart2, AlertTriangle,
  CheckCircle, CloudRain
} from 'lucide-react';

const API_URL = 'http://localhost:8000';

// ── Flood risk badge helper ───────────────────────────────────────────────────
function RiskBadge({ depPct }) {
  if (depPct === null || depPct === undefined) return null;
  const val = Number(depPct);
  if (val > 100) return <span className="badge badge-extreme">⚠ Extreme Excess (+{val.toFixed(0)}%)</span>;
  if (val > 0) return <span className="badge badge-high">↑ Above Normal (+{val.toFixed(0)}%)</span>;
  if (val > -30) return <span className="badge badge-normal">✓ Near Normal ({val.toFixed(0)}%)</span>;
  return <span className="badge badge-low">↓ Deficit ({val.toFixed(0)}%)</span>;
}

export default function App() {
  // ── Map viewport ─────────────────────────────────────────────────────────
  const [viewState, setViewState] = useState({
    longitude: 77.5946,
    latitude: 12.9716,
    zoom: 10,
  });
  const mapRef = useRef(null);

  // ── Region selection ──────────────────────────────────────────────────────
  const [regionsTree, setRegionsTree] = useState({});          // district → taluk → [hobli]
  const [selDistrict, setSelDistrict] = useState('');
  const [selTaluk, setSelTaluk] = useState('');
  const [selHobli, setSelHobli] = useState('');
  const [regionLoading, setRegionLoading] = useState(false);
  const [regionLoaded, setRegionLoaded] = useState(false);  // graph is ready on backend
  const [loadedHobli, setLoadedHobli] = useState('');    // the currently loaded hobli name

  // ── Rainfall data ─────────────────────────────────────────────────────────
  const [rainfallHistory, setRainfallHistory] = useState([]);   // [{date, actual_mm, ...}]
  const [rainfallMode, setRainfallMode] = useState('manual'); // 'historical' | 'manual'
  const [selDate, setSelDate] = useState('');
  const [selRecord, setSelRecord] = useState(null);

  // ── Simulation params ─────────────────────────────────────────────────────
  const [rainfallMm, setRainfallMm] = useState(150);
  const [steps, setSteps] = useState(20);
  const [decayFactor, setDecayFactor] = useState(0.5);

  // ── Simulation state ──────────────────────────────────────────────────────
  const [isRunning, setIsRunning] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [totalSteps, setTotalSteps] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [statusMsg, setStatusMsg] = useState('Select a region to begin');

  // ── Map data ──────────────────────────────────────────────────────────────
  const [roadsData, setRoadsData] = useState(null);
  const [floodData, setFloodData] = useState(null);
  const [simulationDone, setSimulationDone] = useState(false);

  const eventSourceRef = useRef(null);
  const pauseRef = useRef(false);
  const timerRef = useRef(null);

  // ══════════════════════════════════════
  // 1. Load regions tree on mount
  // ══════════════════════════════════════
  useEffect(() => {
    axios.get(`${API_URL}/regions`)
      .then(res => setRegionsTree(res.data))
      .catch(() => setStatusMsg('Could not reach backend. Is the server running?'));
  }, []);

  // Cascading dropdowns
  const districts = Object.keys(regionsTree).sort();
  const taluks = selDistrict ? Object.keys(regionsTree[selDistrict] || {}).sort() : [];
  const hoblis = selDistrict && selTaluk
    ? (regionsTree[selDistrict]?.[selTaluk] || [])
    : [];

  const handleDistrictChange = (d) => {
    setSelDistrict(d); setSelTaluk(''); setSelHobli('');
    setRegionLoaded(false); resetSimulation();
  };
  const handleTalukChange = (t) => {
    setSelTaluk(t); setSelHobli('');
    setRegionLoaded(false); resetSimulation();
  };
  const handleHobliChange = (h) => {
    setSelHobli(h);
    setRegionLoaded(false); resetSimulation();
  };

  // ══════════════════════════════════════
  // 2. Load Region
  // ══════════════════════════════════════
  const handleLoadRegion = async () => {
    if (!selHobli) return;
    setRegionLoading(true);
    setStatusMsg(`Loading road network for ${selHobli} …`);
    setFloodData(null);

    try {
      // Load graph on backend
      const res = await axios.post(`${API_URL}/load-region`, { hobli: selHobli });
      const { lat, lon } = res.data;

      // Fly map to hobli centre
      setViewState(v => ({ ...v, longitude: lon, latitude: lat, zoom: 14 }));

      // Fetch road network for display
      const mapRes = await axios.get(`${API_URL}/map-data`, { params: { hobli: selHobli } });
      setRoadsData(mapRes.data);

      // Fetch rainfall history
      try {
        const rfRes = await axios.get(`${API_URL}/rainfall-data/${encodeURIComponent(selHobli)}`);
        setRainfallHistory(rfRes.data.records || []);
        setSelDate(''); setSelRecord(null);
      } catch {
        setRainfallHistory([]);
      }

      setLoadedHobli(selHobli);
      setRegionLoaded(true);
      setStatusMsg(`Region ready: ${selHobli}. Configure and run simulation.`);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setStatusMsg(`Error: ${detail}`);
    } finally {
      setRegionLoading(false);
    }
  };

  // ══════════════════════════════════════
  // 3. Historical date selection
  // ══════════════════════════════════════
  const handleDateSelect = (date) => {
    setSelDate(date);
    const rec = rainfallHistory.find(r => r.date === date);
    setSelRecord(rec || null);
    if (rec) {
      setRainfallMm(Math.max(1, rec.actual_mm));
      setStatusMsg(`Loaded ${date}: ${rec.actual_mm} mm actual rainfall`);
    }
  };

  // ══════════════════════════════════════
  // 4. Simulation controls
  // ══════════════════════════════════════
  const resetSimulation = () => {
    if (eventSourceRef.current) { eventSourceRef.current.close(); eventSourceRef.current = null; }
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    setIsRunning(false); setIsPaused(false);
    setCurrentStep(0); setTotalSteps(0); setElapsedTime(0);
    setFloodData(null); setSimulationDone(false);
    pauseRef.current = false;
  };

  const startSimulation = useCallback(() => {
    if (!regionLoaded || !loadedHobli) return;
    resetSimulation();
    setIsRunning(true);
    setSimulationDone(false);
    setStatusMsg('Simulation running …');

    const startT = Date.now();
    timerRef.current = setInterval(() => setElapsedTime(Math.round((Date.now() - startT) / 1000)), 1000);

    const params = new URLSearchParams({
      hobli: loadedHobli,
      rainfall_mm: rainfallMm,
      steps: steps,
      decay_factor: decayFactor,
    });
    const url = `${API_URL}/simulate-stream?${params}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = async (evt) => {
      while (pauseRef.current) await new Promise(r => setTimeout(r, 200));
      const data = JSON.parse(evt.data);

      if (data.done) {
        es.close(); eventSourceRef.current = null;
        clearInterval(timerRef.current); timerRef.current = null;
        setIsRunning(false); setSimulationDone(true);
        setStatusMsg(`Simulation complete — ${data.total} steps`);
        return;
      }
      setCurrentStep(data.step);
      setTotalSteps(data.total);
      if (data.flood_geojson?.features?.length > 0) setFloodData(data.flood_geojson);
    };

    es.onerror = () => {
      es.close(); eventSourceRef.current = null;
      clearInterval(timerRef.current); timerRef.current = null;
      setIsRunning(false);
      setStatusMsg('Stream error. Check backend.');
    };
  }, [regionLoaded, loadedHobli, rainfallMm, steps, decayFactor]);

  const togglePause = () => {
    pauseRef.current = !pauseRef.current;
    setIsPaused(pauseRef.current);
    setStatusMsg(pauseRef.current ? 'Paused' : 'Simulation running …');
  };

  // ══════════════════════════════════════
  // Map layer paint styles
  // ══════════════════════════════════════
  const roadPaint = { 'line-color': '#6b7280', 'line-width': 1.5, 'line-opacity': 0.7 };
  const floodFillPaint = {
    'fill-color': ['coalesce', ['get', 'color'], '#3b82f6'],
    'fill-opacity': 0.6,
  };
  const floodLinePaint = {
    'line-color': ['coalesce', ['get', 'color'], '#1d4ed8'],
    'line-width': 1.5, 'line-opacity': 0.8,
  };

  const progressPct = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;

  // ══════════════════════════════════════
  // Render
  // ══════════════════════════════════════
  return (
    <div className="app-container">
      {/* ─── Sidebar ─── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <Droplets size={22} className="icon-blue" />
          <span>Flood Digital Twin</span>
        </div>

        {/* ── Region Selector ─────────────────────────── */}
        <section className="panel">
          <h3 className="panel-title"><MapPin size={14} /> Select Region</h3>

          <label className="field-label">District</label>
          <div className="select-wrap">
            <select
              value={selDistrict}
              onChange={e => handleDistrictChange(e.target.value)}
              className="styled-select"
            >
              <option value="">— Select District —</option>
              {districts.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <ChevronDown size={14} className="select-arrow" />
          </div>

          <label className="field-label">Taluk</label>
          <div className="select-wrap">
            <select
              value={selTaluk}
              onChange={e => handleTalukChange(e.target.value)}
              disabled={!selDistrict}
              className="styled-select"
            >
              <option value="">— Select Taluk —</option>
              {taluks.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <ChevronDown size={14} className="select-arrow" />
          </div>

          <label className="field-label">Hobli</label>
          <div className="select-wrap">
            <select
              value={selHobli}
              onChange={e => handleHobliChange(e.target.value)}
              disabled={!selTaluk}
              className="styled-select"
            >
              <option value="">— Select Hobli —</option>
              {hoblis.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
            <ChevronDown size={14} className="select-arrow" />
          </div>

          <button
            className={`btn-primary ${(!selHobli || regionLoading) ? 'btn-disabled' : ''}`}
            onClick={handleLoadRegion}
            disabled={!selHobli || regionLoading}
          >
            {regionLoading
              ? <><Loader size={14} className="spin" /> Loading…</>
              : regionLoaded && loadedHobli === selHobli
                ? <><CheckCircle size={14} /> Reload Region</>
                : <><MapPin size={14} /> Load Region</>}
          </button>

          {regionLoaded && (
            <p className="loaded-badge">
              <CheckCircle size={12} /> {loadedHobli}
            </p>
          )}
        </section>

        {/* ── Rainfall Mode ───────────────────────────── */}
        {regionLoaded && (
          <section className="panel">
            <h3 className="panel-title"><CloudRain size={14} /> Rainfall Input</h3>

            <div className="mode-toggle">
              <button
                className={`toggle-btn ${rainfallMode === 'historical' ? 'active' : ''}`}
                onClick={() => setRainfallMode('historical')}
              >Historical</button>
              <button
                className={`toggle-btn ${rainfallMode === 'manual' ? 'active' : ''}`}
                onClick={() => setRainfallMode('manual')}
              >Manual</button>
            </div>

            {rainfallMode === 'historical' ? (
              rainfallHistory.length > 0 ? (
                <>
                  <label className="field-label"><Calendar size={12} /> Select Date</label>
                  <div className="select-wrap">
                    <select
                      value={selDate}
                      onChange={e => handleDateSelect(e.target.value)}
                      className="styled-select"
                    >
                      <option value="">— Pick a date —</option>
                      {rainfallHistory.map(r => (
                        <option key={r.date} value={r.date}>
                          {r.date} — {r.actual_mm} mm
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={14} className="select-arrow" />
                  </div>

                  {selRecord && (
                    <div className="rainfall-card">
                      <div className="rf-row">
                        <span>Actual</span>
                        <strong>{selRecord.actual_mm} mm</strong>
                      </div>
                      {selRecord.normal_mm != null && (
                        <div className="rf-row">
                          <span>Normal</span>
                          <strong>{selRecord.normal_mm} mm</strong>
                        </div>
                      )}
                      {selRecord.dep_pct != null && (
                        <div className="rf-row">
                          <span>Departure</span>
                          <RiskBadge depPct={selRecord.dep_pct} />
                        </div>
                      )}
                      <div className="rf-row">
                        <span>→ Simulation uses</span>
                        <strong>{rainfallMm} mm</strong>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="hint-text">No historical data for this hobli.</p>
              )
            ) : (
              <>
                <label className="field-label">
                  Rainfall (mm) — {rainfallMm}
                </label>
                <input
                  type="range" min={5} max={500} step={5}
                  value={rainfallMm}
                  onChange={e => setRainfallMm(Number(e.target.value))}
                  className="slider"
                />
              </>
            )}
          </section>
        )}

        {/* ── Simulation Controls ──────────────────────── */}
        {regionLoaded && (
          <section className="panel">
            <h3 className="panel-title"><Activity size={14} /> Simulation</h3>

            <label className="field-label">Steps — {steps}</label>
            <input
              type="range" min={5} max={50} step={1}
              value={steps}
              onChange={e => setSteps(Number(e.target.value))}
              className="slider"
            />

            <label className="field-label">Decay Factor — {decayFactor.toFixed(2)}</label>
            <input
              type="range" min={0.1} max={0.9} step={0.05}
              value={decayFactor}
              onChange={e => setDecayFactor(Number(e.target.value))}
              className="slider"
            />

            <div className="btn-row">
              {!isRunning ? (
                <button
                  className={`btn-primary ${!regionLoaded ? 'btn-disabled' : ''}`}
                  onClick={startSimulation}
                  disabled={!regionLoaded}
                >
                  <Play size={14} /> Run
                </button>
              ) : (
                <button className="btn-secondary" onClick={togglePause}>
                  {isPaused ? <><Play size={14} /> Resume</> : <><Pause size={14} /> Pause</>}
                </button>
              )}
              <button className="btn-ghost" onClick={resetSimulation} disabled={!isRunning && !simulationDone}>
                <RefreshCw size={14} /> Reset
              </button>
            </div>

            {/* Progress */}
            {(isRunning || simulationDone) && (
              <div className="progress-section">
                <div className="progress-bar-bg">
                  <div className="progress-bar-fill" style={{ width: `${progressPct}%` }} />
                </div>
                <div className="progress-stats">
                  <span><Clock size={11} /> {elapsedTime}s</span>
                  <span>{currentStep}/{totalSteps} steps ({progressPct}%)</span>
                </div>
              </div>
            )}
          </section>
        )}

        {/* ── Status Bar ──────────────────────────────── */}
        <div className="status-bar">
          <Activity size={12} />
          <span>{statusMsg}</span>
        </div>
      </aside>

      {/* ─── Map ─── */}
      <main className="map-container">
        <Map
          ref={mapRef}
          {...viewState}
          onMove={e => setViewState(e.viewState)}
          style={{ width: '100%', height: '100%' }}
          mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        >
          <NavigationControl position="top-right" />

          {/* Road network */}
          {roadsData && (
            <Source id="roads" type="geojson" data={roadsData}>
              <Layer id="roads-layer" type="line" paint={roadPaint} />
            </Source>
          )}

          {/* Flood extent */}
          {floodData && (
            <Source id="flood" type="geojson" data={floodData}>
              <Layer id="flood-fill" type="fill" paint={floodFillPaint} />
              <Layer id="flood-border" type="line" paint={floodLinePaint} />
            </Source>
          )}
        </Map>

        {/* Floating info chip */}
        {loadedHobli && (
          <div className="map-chip">
            <MapPin size={12} /> {loadedHobli}
            {selRecord && <> · <BarChart2 size={12} /> {selRecord.actual_mm} mm</>}
          </div>
        )}
      </main>
    </div>
  );
}
