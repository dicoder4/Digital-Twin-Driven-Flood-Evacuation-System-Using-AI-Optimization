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
import { Droplets, Activity, Route, GitCompare, Zap, Radio, Info, Cpu, CloudRain, GraduationCap } from 'lucide-react';
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
import { DraSidebar } from './components/DraSidebar';
import { PanelOfExperts } from './components/PanelOfExperts';
import { EvacuationChat } from './components/EvacuationChat';
import { computeShelterSafety } from './utils/geoUtils';
import { API_URL } from './config';
import { AppCopilot } from './components/AppCopilot';
import { AutomationPanel } from './components/AutomationPanel';
import { PublicTransportAgent } from './components/PublicTransportAgent';
import { useAuth } from './context/AuthContext';
import { useLanguage } from './context/LanguageContext';
import { useTutorial } from './context/TutorialContext';
import TutorialOverlay from './components/TutorialOverlay';
import { t } from './translations';
import CitizenView from './components/CitizenView';
import SimulateCitizenView from './components/SimulateCitizenView';
import './App.css';

export default function App() {
  const { user, logout, isSimulate, isCitizen } = useAuth();
  const { lang, toggle: toggleLang } = useLanguage();
  const { startTutorial, registerTabSwitch } = useTutorial();

  // ── Map viewport ─────────────────────────────────────────────
  const [viewState, setViewState] = useState({
    longitude: 77.5946, latitude: 12.9716, zoom: 10,
  });

  // ── Region state ─────────────────────────────────────────────
  const [regionLoading, setRegionLoading] = useState(false);
  const [regionLoaded, setRegionLoaded] = useState(false);
  const [loadedHobli, setLoadedHobli] = useState('');
  const [baseRoadsData, setBaseRoadsData] = useState(null);
  const [selRec, setSelRec] = useState(null);
  const [busManifest, setBusManifest] = useState(null);

  // ── Population / shelter state ────────────────────────────────
  const [populationCount, setPopulationCount] = useState(0);
  const [unsafePeopleCount, setUnsafePeopleCount] = useState(0);
  const [shelterCandidates, setShelterCandidates] = useState([]);

  // ── Simulation params ─────────────────────────────────────────
  const [rainfallMm, setRainfallMm] = useState(150);
  const [steps, setSteps] = useState(5);
  const [decayFactor, setDecayFactor] = useState(0.5);
  const [algoInfoOpen, setAlgoInfoOpen] = useState(false);

  // ── Three independent toggles / selectors ────────────────────
  // 1. Evacuation Mode — ONLY controls 1% population scaling
  const [evacuationMode, setEvacuationMode] = useState(false);
  // 2. Live Traffic — whether TomTom data modifies the road graph
  const [useTraffic, setUseTraffic] = useState(false);
  // 3. Algorithm — which optimiser runs (always runs, not gated by evac mode)
  const [algorithm, setAlgorithm] = useState('ga');

  // ── Compare mode ──────────────────────────────────────────────
  const [compareMode, setCompareMode] = useState(false);
  const [compareResults, setCompareResults] = useState(null);  // {ga, aco, pso}
  const [compareRunning, setCompareRunning] = useState(false);
  const [compareProgress, setCompareProgress] = useState('');
  const [compareActiveAlgo, setCompareActiveAlgo] = useState(null);  // which algo's routes to show
  // Abort ref — allows cancelling compare mid-run
  const compareAbortRef = useRef(false);

  // ── UI state ──────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState('setup');
  const [selectedShelterId, setSelectedShelterId] = useState(null);
  const [selectedBusId, setSelectedBusId] = useState(null);
  const [showTrafficPins, setShowTrafficPins] = useState(false);
  const isDraMode = user?.role === 'authority'; // DRA mode toggle enforced by user role
  const [mapPinBox, setMapPinBox] = useState(null);
  const [selectedMetro, setSelectedMetro] = useState(null);
  const [metroStations, setMetroStations] = useState([]);
  const [metroLines, setMetroLines] = useState([]);

  // ── DRA Pin-Drop ─────────────────────────────────────────────
  const [pinDropMode, setPinDropMode] = useState(false);
  const [pinResolvedHobli, setPinResolvedHobli] = useState(null);
  const pinAbortRef = useRef(null);

  // ── Sidebar resize ────────────────────────────────────────────
  const [sidebarWidth, setSidebarWidth] = useState(320);
  const sidebarRef = useRef(null);
  const isResizingRef = useRef(false);

  const handleResizeMouseDown = useCallback((e) => {
    e.preventDefault();
    isResizingRef.current = true;
    const handle = e.currentTarget;
    handle.classList.add('dragging');
    const startX = e.clientX;
    const startW = sidebarRef.current?.offsetWidth ?? sidebarWidth;

    const onMouseMove = (mv) => {
      if (!isResizingRef.current) return;
      const newW = Math.min(1000, Math.max(260, startW + (mv.clientX - startX)));
      setSidebarWidth(newW);
    };
    const onMouseUp = () => {
      isResizingRef.current = false;
      handle.classList.remove('dragging');
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [sidebarWidth]);

  // ── Hooks ─────────────────────────────────────────────────────
  const regions = useRegions();
  const sim = useSimulation();

  if (isSimulate) {
    return <SimulateCitizenView user={user} onLogout={logout} lang={lang} onToggleLang={toggleLang} />;
  }

  if (isCitizen) {
    return <CitizenView user={user} onLogout={logout} lang={lang} onToggleLang={toggleLang} />;
  }

  // Recompute shelter safety on every flood update, then override with backend source of truth
  const sheltersWithSafety = useMemo(() => {
    let computed = computeShelterSafety(shelterCandidates, sim.floodData);

    // Once simulation is done or we have a compare report, override with backend's definitive accurate safety
    // Backend also considers high-risk access roads, which frontend doesn't.
    let reports = null;
    if (compareResults && compareActiveAlgo) {
      reports = compareResults[compareActiveAlgo]?.shelter_reports;
    } else if (sim.finalReport?.summary?.shelter_reports) {
      reports = sim.finalReport.summary.shelter_reports;
    }

    if (reports?.length > 0) {
      computed = computed.map(c => {
        const report = reports.find(r => String(r.id) === String(c.id));
        if (report) {
          return { ...c, safe: report.safe };
        }
        return c;
      });
    }

    return computed;
  }, [shelterCandidates, sim.floodData, compareResults, compareActiveAlgo, sim.finalReport]);

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
  const handleLoadRegion = useCallback(async (hobliOverride) => {
    const targetHobli = typeof hobliOverride === 'string' ? hobliOverride : regions.selHobli;
    if (!targetHobli) return;
    setRegionLoading(true);
    sim.setStatusMsg(`Loading ${targetHobli} …`);
    sim.clearMap();
    setPopulationCount(0);
    setUnsafePeopleCount(0);
    setShelterCandidates([]);
    setBusManifest(null);
    setSelectedBusId(null);
    setMetroLines([]);
    setMetroStations([]);
    setSelectedMetro(null);
    setActiveTab('setup');
    try {
      const res = await axios.post(`${API_URL}/load-region`, { hobli: targetHobli });
      const { lat, lon } = res.data;
      setViewState(v => ({ ...v, longitude: lon, latitude: lat, zoom: 14 }));
      
      const stations = res.data.metro_stations || [];
      const lines = res.data.metro_lines || { type: 'FeatureCollection', features: [] };
      
      setMetroStations(stations);
      setMetroLines(lines);
      
      const mapRes = await axios.get(`${API_URL}/map-data`, { params: { hobli: targetHobli } });
      setBaseRoadsData(mapRes.data);
      setLoadedHobli(targetHobli);
      setRegionLoaded(true);
      setSelRec(null);
      sim.setStatusMsg(`${targetHobli} ready. Configure simulation and run.`);
    } catch (err) {
      sim.setStatusMsg(`Error: ${err.response?.data?.detail || err.message}`);
    } finally {
      setRegionLoading(false);
    }
  }, [regions.selHobli, sim]);

  const handleDistrict = (d) => { regions.setDistrict(d); setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };
  const handleTaluk = (t) => { regions.setTaluk(t); setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };
  const handleHobli = (h) => { regions.setHobli(h); setRegionLoaded(false); sim.reset(); setPopulationCount(0); setUnsafePeopleCount(0); setShelterCandidates([]); };

  // ── Copilot: select region (finds district+taluk from tree) ───
  const handleSelectRegion = useCallback((hobli) => {
    const tree = regions.regionsTree || {};
    let foundDistrict = null, foundTaluk = null;
    for (const [dist, taluks] of Object.entries(tree)) {
      for (const [taluk, hoblis] of Object.entries(taluks)) {
        if (hoblis.includes(hobli)) { foundDistrict = dist; foundTaluk = taluk; break; }
      }
      if (foundDistrict) break;
    }
    // Set all three atomically to avoid cascade wiping
    if (foundDistrict && foundTaluk) {
      regions.setAll(foundDistrict, foundTaluk, hobli);
    }
    setRegionLoaded(false);
    sim.reset();
    setPopulationCount(0);
    setUnsafePeopleCount(0);
    setShelterCandidates([]);
    // Load the region into backend memory, auto-fetch population, then navigate to config
    handleLoadRegion(hobli).then(() => {
      setActiveTab('config');
      // Auto-fetch population so it is ready before the Copilot fires run_simulation
      axios.get(`${API_URL}/population/${encodeURIComponent(hobli)}`)
        .then(res => { if (res.data.total_population > 0) setPopulationCount(res.data.total_population); })
        .catch(() => { }); // silent — user can still set it manually
    });
  }, [regions, handleLoadRegion, sim]);

  // ── Start single simulation ───────────────────────────────────
  const handleStart = (extraShelters = null) => {
    if (!regionLoaded) return;
    setCompareResults(null);
    setBusManifest(null);
    setSelectedBusId(null);
    setActiveTab('setup');
    sim.start(loadedHobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic, algorithm, populationCount, extraShelters);
  };

  // ── Re-run with suggested new shelters injected ───────────────
  const handleRerunWithSuggestions = useCallback((suggestions) => {
    if (!regionLoaded || !suggestions?.length) return;
    setCompareResults(null);
    setBusManifest(null);
    setSelectedBusId(null);
    setActiveTab('setup');
    sim.setStatusMsg(`Re-running with ${suggestions.length} suggested shelter(s)…`);
    // Minimal payload to avoid URL length limits with many suggestions
    const stripped = suggestions.map(s => ({
      lat: s.lat,
      lon: s.lon,
      suggested_capacity: s.suggested_capacity,
      area_name: s.area_name
    }));
    sim.start(loadedHobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic, algorithm, populationCount, stripped);
  }, [regionLoaded, loadedHobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic, algorithm, populationCount, sim]);


  // ── DRA Mode: Automatic ACO + Traffic run ────────────────────
  const handleDraRunEvacuation = () => {
    if (!regionLoaded) return;
    setCompareResults(null);

    // In DRA mode, force these settings regardless of what's in React state
    // But we still update React state so the UI reflects what's running
    setAlgorithm('aco');
    setUseTraffic(true);
    setEvacuationMode(false);
    setBusManifest(null);
    setSelectedBusId(null);
    setActiveTab('setup');

    sim.start(loadedHobli, rainfallMm, steps, decayFactor, false, true, 'aco', populationCount);
  };

  // ── Reset everything ──────────────────────────────────────────
  const handleReset = () => {
    compareAbortRef.current = true;   // signal any running compare to stop
    sim.reset();
    setCompareResults(null);
    setBusManifest(null);
    setCompareRunning(false);
    setCompareProgress('');
    setCompareActiveAlgo(null);
  };

  // ── Compare Mode: single /simulate-compare SSE stream ────────
  // Flood simulation runs ONCE on the backend; GA + ACO + PSO then
  // run in parallel threads. The frontend receives the same flood-step
  // frames it uses for map animation, then one 'compare_done' frame
  // containing all three results simultaneously.
  // This reduces compare time from ~3× to ~1× a single run.
  const handleCompare = useCallback((overrideHobli, overrideRainfall, overrideEvac, overrideTraffic) => {
    if (!regionLoaded || compareRunning) return;
    compareAbortRef.current = false;
    setCompareResults(null);
    setBusManifest(null);
    setSelectedBusId(null);
    setCompareRunning(true);
    setCompareProgress('Flood simulation running…');
    sim.reset();
    sim.setStatusMsg('Compare: flood simulation in progress…');

    const runHobli = (typeof overrideHobli === 'string' ? overrideHobli : null) || loadedHobli;
    if (!runHobli) return;

    const params = new URLSearchParams({
      hobli: runHobli,
      rainfall_mm: overrideRainfall !== undefined ? overrideRainfall : rainfallMm,
      steps,
      decay_factor: decayFactor,
      evacuation_mode: overrideEvac !== undefined ? overrideEvac : evacuationMode,
      use_traffic: overrideTraffic !== undefined ? overrideTraffic : useTraffic,
    });
    if (populationCount !== null && populationCount !== undefined && populationCount > 0) {
      params.append('population', populationCount);
    }

    const es = new EventSource(`${API_URL}/simulate-compare?${params}`);

    // Safety timeout — 10 min for the whole compare run
    const timeout = setTimeout(() => {
      es.close();
      setCompareRunning(false);
      setCompareProgress('');
      sim.setStatusMsg('Compare timed out — check backend.');
    }, 10 * 60 * 1000);

    es.onmessage = (evt) => {
      if (compareAbortRef.current) {
        clearTimeout(timeout);
        es.close();
        setCompareRunning(false);
        setCompareProgress('');
        sim.setStatusMsg('Compare cancelled.');
        return;
      }

      try {
        const data = JSON.parse(evt.data);

        // ── Flood step frame — animate the map as normal ────────────────
        if (!data.compare_done) {
          setCompareProgress(`Flood: step ${data.step} / ${data.total}`);
          sim.setStatusMsg(`Compare: flood step ${data.step} of ${data.total}…`);
          // Pipe flood / roads data into the shared sim hook for map rendering
          if (data.flood_geojson?.features?.length > 0) sim.setFloodData(data.flood_geojson);
          if (data.roads_geojson?.features?.length > 0) sim.setRoadsData(data.roads_geojson);
          
          return;
        }

        // ── compare_done frame — all three results arrive at once ────────
        clearTimeout(timeout);
        es.close();

        if (data.error) {
          setCompareResults(null);
          setCompareRunning(false);
          setCompareProgress('');
          sim.setStatusMsg(`Compare failed: ${data.error}`);
          return;
        }

        const rawResults = data.results || {};

        // Reshape: { ga: { summary, evacuation_plan, ... }, aco: ..., pso: ... }
        // → flat shape that EvacuationPanel already expects
        const finalResults = {};
        for (const [algo, payload] of Object.entries(rawResults)) {
          finalResults[algo] = {
            ...(payload.summary || {}),
            evacuation_plan: payload.evacuation_plan || [],
            traffic_segment_count: payload.traffic_segment_count || 0,
            traffic_geojson: payload.traffic_geojson || null,
          };
        }

        setCompareResults(Object.keys(finalResults).length > 0 ? finalResults : null);
        setCompareRunning(false);
        setCompareProgress('');

        if (Object.keys(finalResults).length > 0) {
          // Auto-select the best algo (lowest fitness = best routes)
          let bestAlgo = null, bestFit = Infinity;
          for (const [algo, res] of Object.entries(finalResults)) {
            const f = res.best_fitness ?? Infinity;
            if (!res.error && f < bestFit) { bestFit = f; bestAlgo = algo; }
          }
          setCompareActiveAlgo(bestAlgo);
          setActiveTab('evacuation');
          sim.setStatusMsg(
            `Compare complete — showing ${bestAlgo?.toUpperCase() ?? ''} routes (best fitness)`
          );

          // Sync the "winner" result to MCP server
          if (bestAlgo) {
            const winner = finalResults[bestAlgo];
            fetch(`${API_URL}/mcp-update-state`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                summary_data: winner,
                evacuation_plan: winner.evacuation_plan || [],
                hobli: runHobli,
              }),
            }).catch(() => { });
          }
        } else {
          sim.setStatusMsg('Compare finished — no results returned.');
        }

      } catch {
        // ignore malformed SSE frames
      }
    };

    es.onerror = () => {
      clearTimeout(timeout);
      es.close();
      setCompareRunning(false);
      setCompareProgress('');
      sim.setStatusMsg('Compare stream error — check backend.');
    };
  }, [regionLoaded, compareRunning, loadedHobli, rainfallMm, steps, decayFactor, evacuationMode, useTraffic, sim]);

  useEffect(() => {
    if (sim.simulationDone && !compareRunning) {
      setActiveTab('evacuation');
      setSelectedShelterId(null);
      setSelectedBusId(null);
      setShowTrafficPins(false);
    }
  }, [sim.simulationDone, compareRunning]);

  // Handle DRA mode auto-fetch of population & shelters
  useEffect(() => {
    if (isDraMode && regionLoaded && loadedHobli) {
      if (populationCount === 0) {
        axios.get(`${API_URL}/population/${encodeURIComponent(loadedHobli)}`)
          .then(res => setPopulationCount(res.data.total_population || 0))
          .catch(console.error);
      }
      if (shelterCandidates.length === 0) {
        axios.get(`${API_URL}/shelters/${encodeURIComponent(loadedHobli)}`)
          .then(res => setShelterCandidates(res.data.shelters || []))
          .catch(console.error);
      }
    }
  }, [isDraMode, regionLoaded, loadedHobli, populationCount, shelterCandidates.length]);

  // ── Render ────────────────────────────────────────────────────
  const isCitizenMode = user?.role === 'citizen';
  if (isCitizenMode) {
    return <CitizenView user={user} onLogout={logout} lang={lang} onToggleLang={toggleLang} />;
  }

  const isSimulateMode = user?.role === 'simulate';
  if (isSimulateMode) {
    return <SimulateCitizenView user={user} onLogout={logout} lang={lang} onToggleLang={toggleLang} />;
  }

  return (
    <div className="app-container" style={{ '--sidebar-w': `${sidebarWidth}px` }}>
      {/* ─── Sidebar ───────────────────────────────────────── */}
      <aside className="sidebar" ref={sidebarRef} style={{ width: sidebarWidth }}>
        <div className="sidebar-header" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', alignItems: 'stretch' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <Droplets size={20} className="icon-blue" />
              <div>
                <div className="sidebar-title">{t('app_title', lang)}</div>
                <div className="sidebar-sub">{t('app_subtitle', lang)}</div>
              </div>
            </div>
            <button
              onClick={toggleLang}
              id="tutorial-lang-toggle"
              style={{ fontSize: '11px', fontWeight: 700, padding: '3px 8px', borderRadius: '4px', border: '1px solid #cbd5e1', background: '#f8fafc', color: '#334155', cursor: 'pointer', whiteSpace: 'nowrap' }}
              title={lang === 'en' ? 'Switch to Kannada' : 'Switch to English'}
            >
              {t('lang_toggle', lang)}
            </button>
          </div>
            {/* User Profile & Logout */}
            <div className="flex items-center justify-between bg-slate-50 p-2.5 rounded-lg border border-slate-200 backdrop-blur-sm">
              <div className="flex flex-col text-left">
                <span className="text-slate-800 text-sm font-bold">{user?.username || 'Guest'}</span>
                <span className="text-slate-500 font-medium text-xs capitalize tracking-wide">{user?.role || 'Viewer'}</span>
              </div>
              <button
                onClick={logout}
                className="bg-red-50 border border-red-200 hover:bg-red-100 hover:border-red-300 text-red-600 hover:text-red-700 px-3 py-1.5 rounded transition-all duration-200 text-xs font-bold"
              >
                {t('logout', lang)}
              </button>
              <button
                className="tutorial-trigger-btn"
                onClick={() => startTutorial(isDraMode ? 'authority' : 'researcher')}
                title="Take a guided tutorial"
              >
                <GraduationCap size={13} />
                Tutorial
              </button>
            </div>
        </div>

        {/* ── Drag-resize handle ─────────────────────────────── */}
        <div
          className="sidebar-resize-handle"
          onMouseDown={handleResizeMouseDown}
          title="Drag to resize"
        />

        {/* Tabs */}
        <div className="sidebar-tabs">
          <button
            className={`sidebar-tab ${activeTab === 'setup' ? 'active' : ''}`}
            onClick={() => setActiveTab('setup')}
          >{t('tab_setup', lang)}</button>
          <button
            className={`sidebar-tab evac-tab ${activeTab === 'evacuation' ? 'active' : ''}`}
            onClick={() => setActiveTab('evacuation')}
            disabled={!sim.simulationDone && !compareResults}
            title={!sim.simulationDone && !compareResults ? t('tab_run_sim_first', lang) : ''}
          ><Route size={11} /> {t('tab_evacuation', lang)}</button>
          <button
            className={`sidebar-tab ${activeTab === 'ai-agent' ? 'active' : ''}`}
            onClick={() => setActiveTab('ai-agent')}
            disabled={!sim.simulationDone && !compareResults}
            title={!sim.simulationDone && !compareResults ? t('tab_run_sim_first', lang) : ''}
          ><Cpu size={11} /> {t('tab_resources', lang)}</button>
          <button
            className={`sidebar-tab ${activeTab === 'automation' ? 'active' : ''}`}
            onClick={() => setActiveTab('automation')}
          ><CloudRain size={11} /> {t('tab_sentinel', lang)}</button>
        </div>

        <div className="sidebar-content custom-scrollbar">

          {/* ── SETUP TAB ────────────────────────────────── */}
          <div style={{ display: activeTab === 'setup' ? 'block' : 'none' }}>
            {isDraMode ? (
                <DraSidebar
                  allHoblis={regions.allHoblis}
                  selHobli={regions.selHobli}
                  onHobli={handleHobli}
                  onLoad={handleLoadRegion}
                  loading={regionLoading}
                  loaded={regionLoaded}
                  loadedHobli={loadedHobli}
                  rainfallMm={rainfallMm}
                  onRainfallChange={setRainfallMm}
                  onRunEvacuation={handleDraRunEvacuation}
                  simulationRunning={sim.isRunning}
                  pinDropMode={pinDropMode}
                  onTogglePinDrop={() => {
                    setPinDropMode(v => !v);
                    if (pinDropMode) {
                      setMapPinBox(null);
                      setPinResolvedHobli(null);
                    }
                  }}
                  pinResolvedHobli={pinResolvedHobli}
                  onRunPinSimulation={async () => {
                    if (!pinResolvedHobli?.hobli_name) return;
                    // Switch region to the resolved hobli, then run
                    await handleLoadRegion(pinResolvedHobli.hobli_name);
                    sim.start(pinResolvedHobli.hobli_name, rainfallMm, steps, decayFactor, false, true, 'ga', 0);
                    setActiveTab('evacuation');
                    setPinDropMode(false);
                    setMapPinBox(null);
                  }}
                />
            ) : (
              <>
                <RegionSelector
                  id="tutorial-region-selector"
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
                    <div id="tutorial-population-panel">
                    <PopulationPanel
                      loadedHobli={loadedHobli}
                      onPopulationSet={setPopulationCount}
                    />
                    </div>

                    <div id="tutorial-shelters-panel">
                    <SheltersPanel
                      loadedHobli={loadedHobli}
                      shelters={sheltersWithSafety.length ? sheltersWithSafety : null}
                      onCandidates={setShelterCandidates}
                    />
                    </div>

                    <div id="tutorial-rainfall-panel">
                    <RainfallPanel
                      loadedHobli={loadedHobli}
                      rainfallMm={rainfallMm}
                      onRainfallChange={setRainfallMm}
                    />
                    </div>

                    {/* ── Panel 1: Evacuation Mode (standalone) ───── */}
                    <div className="evac-mode-toggle panel">
                      <div className="evac-toggle-row">
                        <div>
                          <div className="evac-toggle-label">{t('evac_mode', lang)}</div>
                          <div className="evac-toggle-sub">{t('evac_mode_hint', lang)}</div>
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
                      <h3 className="panel-title"><Zap size={13} /> {t('opt_settings', lang)}</h3>

                      {/* Algorithm selector */}
                      <div className="optim-row">
                        <div className="optim-row-label">
                          <div className="evac-toggle-label">{t('algorithm', lang)}</div>
                          <div className="evac-toggle-sub">{t('algo_hint', lang)}</div>
                        </div>
                        <div className="algo-pill-group">
                          {['ga', 'aco', 'pso'].map(a => (
                            <button
                              key={a}
                              className={`algo-pill ${algorithm === a && !compareMode ? 'algo-pill--active' : ''}`}
                              onClick={() => { setAlgorithm(a); setCompareMode(false); }}
                              disabled={compareRunning}
                              title={{ ga: t('ga_label', lang), aco: t('aco_label', lang), pso: t('pso_label', lang) }[a]}
                            >{a.toUpperCase()}</button>
                          ))}
                          <button
                            className={`algo-pill algo-pill--compare ${compareMode ? 'algo-pill--active-compare' : ''}`}
                            onClick={() => setCompareMode(v => !v)}
                            title={t('compare_desc', lang)}
                            disabled={compareRunning}
                          ><GitCompare size={9} /> {t('tab_setup', lang) === 'Setup' ? 'All' : 'ಎಲ್ಲ'}</button>
                        </div>
                      </div>

                      {/* ⓘ info toggle + expandable descriptions */}
                      <button
                        className={`algo-info-btn ${algoInfoOpen ? 'algo-info-btn--open' : ''}`}
                        onClick={() => setAlgoInfoOpen(v => !v)}
                        title={t('what_are_these', lang)}
                      >
                        <Info size={11} /> {algoInfoOpen ? t('hide_info', lang) : t('what_are_these', lang)}
                      </button>

                      {algoInfoOpen && (
                        <div className="algo-info-panel">
                          <div className="algo-info-item" style={{ borderLeft: '3px solid #93c5fd' }}>
                            <strong style={{ color: '#1d4ed8' }}>GA</strong> — {t('ga_label', lang)}
                            <div className="algo-info-desc">{t('ga_desc', lang)}</div>
                          </div>
                          <div className="algo-info-item" style={{ borderLeft: '3px solid #86efac' }}>
                            <strong style={{ color: '#15803d' }}>ACO</strong> — {t('aco_label', lang)}
                            <div className="algo-info-desc">{t('aco_desc', lang)}</div>
                          </div>
                          <div className="algo-info-item" style={{ borderLeft: '3px solid #d8b4fe' }}>
                            <strong style={{ color: '#7e22ce' }}>PSO</strong> — {t('pso_label', lang)}
                            <div className="algo-info-desc">{t('pso_desc', lang)}</div>
                          </div>
                          <div className="algo-info-item" style={{ borderLeft: '3px solid #c084fc' }}>
                            <strong style={{ color: '#7c3aed' }}>⇄ {lang === 'en' ? 'All' : 'ಎಲ್ಲ'}</strong> — {lang === 'en' ? 'Compare Mode' : 'ಹೋಲಿಕೆ ಮೋಡ್'}
                            <div className="algo-info-desc">{t('compare_desc', lang)}</div>
                          </div>
                        </div>
                      )}

                      {/* Live Traffic toggle */}
                      <div className="optim-row" style={{ marginTop: '0.5rem' }}>
                        <div className="optim-row-label">
                          <div className="evac-toggle-label"><Radio size={11} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }} />{t('live_traffic', lang)}</div>
                          <div className="evac-toggle-sub">{t('traffic_hint', lang)}</div>
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
                          ? t('compare_hint', lang)
                          : `🚨 ${algorithm.toUpperCase()} ${lang === 'en' ? 'will optimise evacuation routes after the flood simulation' : 'ಪ್ರವಾಹ ಸಿಮ್ಯುಲೇಶನ್ ನಂತರ ಸ್ಥಳಾಂತರ ಮಾರ್ಗಗಳನ್ನು ಆಪ್ಟಿಮೈಸ್ ಮಾಡುತ್ತದೆ'}`
                        }
                      </div>
                    </div>

                    {/* ── Simulation Controls ─────────────────────── */}
                    <div id="tutorial-sim-controls">
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
                      onStop={sim.stop}
                      onRestart={sim.restart}
                      compareMode={compareMode}
                      compareProgress={compareProgress}
                    />
                    </div>

                    {/* Flood Impact summary */}
                    {sim.simulationDone && populationCount > 0 && (
                      <section className="panel">
                        <h3 className="panel-title" style={{ color: '#dc2626' }}>⚠ {t('flood_impact', lang)}</h3>
                        <div className="pop-count-row">
                          <span className="pop-count" style={{ color: '#dc2626' }}>
                            {(sim.finalReport?.summary?.total_at_risk_initial ?? unsafePeopleCount).toLocaleString()}
                          </span>
                          <span className="pop-count-label">{t('people_at_risk', lang)}</span>
                        </div>
                        <div className="pop-split">
                          <span style={{ color: '#16a34a' }}>✓ {t('safe', lang)}: {((sim.finalReport?.summary?.simulation_population ?? displayPopulation) - (sim.finalReport?.summary?.total_at_risk_initial ?? unsafePeopleCount)).toLocaleString()}</span>
                          <span style={{ color: '#dc2626' }}>✗ {t('unsafe', lang)}: {(sim.finalReport?.summary?.total_at_risk_initial ?? unsafePeopleCount).toLocaleString()}</span>
                        </div>
                        <button className="btn-evac-goto" onClick={() => setActiveTab('evacuation')}>
                          <Route size={12} /> {t('view_evac_analysis', lang)}
                        </button>
                      </section>
                    )}
                  </>
                )}
              </>
            )}
          </div>

          <div style={{ display: activeTab === 'evacuation' ? 'block' : 'none', height: '100%' }}>
            <EvacuationPanel
              locationName={loadedHobli}
              summary={sim.finalReport?.summary}
              evacuationMode={evacuationMode}
              selectedShelterId={selectedShelterId}
              onSelectShelter={setSelectedShelterId}
              trafficSegmentCount={sim.trafficSegmentCount}
              showTraffic={useTraffic}
              compareResults={compareResults}
              compareActiveAlgo={compareActiveAlgo}
              onSetCompareAlgo={setCompareActiveAlgo}
              isDraMode={isDraMode}
              user={user}
              evacuationPlan={sim.evacuationPlan || []}
              onRerunWithSuggestions={handleRerunWithSuggestions}
              simulationParams={{ rainfall_mm: rainfallMm, steps, decay_factor: decayFactor, population: populationCount }}
              floodData={sim.floodData}
              roadsData={sim.roadsData}
              trafficRoadsData={sim.trafficRoadsData}
              metroLines={metroLines}
              metroStations={metroStations}
              busManifest={busManifest}
            />

          </div>

          <div className="evac-panel" style={{ display: activeTab === 'ai-agent' ? 'flex' : 'none', height: "100%", paddingBottom: "2rem", overflowY: 'auto' }}>
            {sim.simulationDone || compareResults ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <PublicTransportAgent
                  evacuationPlan={compareResults && compareActiveAlgo ? compareResults[compareActiveAlgo]?.evacuation_plan : (sim.evacuationPlan || [])}
                  onManifestGenerated={setBusManifest}
                  shelters={sheltersWithSafety}
                  selectedBusId={selectedBusId}
                  onSelectBus={setSelectedBusId}
                  metroReports={compareResults && compareActiveAlgo ? compareResults[compareActiveAlgo]?.metro_reports : (sim.finalReport?.summary?.metro_reports || [])}
                  metroStations={metroStations}
                  onSelectMetro={setSelectedMetro}
                  selectedMetroId={selectedMetro ? (selectedMetro.id || `${selectedMetro.name}::${selectedMetro.line || ''}`) : null}
                  loadedHobli={loadedHobli}
                />
                {compareResults && compareActiveAlgo ? (
                  <>
                    <PanelOfExperts
                      locationName={loadedHobli}
                      summary={compareResults[compareActiveAlgo]}
                      evacuationPlan={compareResults[compareActiveAlgo]?.evacuation_plan ?? []}
                    />
                  </>
                ) : sim.finalReport?.summary ? (
                  <>
                    <PanelOfExperts locationName={loadedHobli} summary={sim.finalReport?.summary} evacuationPlan={sim.evacuationPlan || []} />
                  </>
                ) : null}
              </div>
            ) : (
              <div className="evac-empty">
                <Cpu size={32} className="evac-empty-icon" style={{ marginBottom: "1rem", color: "#64748b" }} />
                <p style={{ color: "#64748b", textAlign: "center", lineHeight: "1.5" }}>Run a simulation to interact with the AI Evacuation Agent.</p>
              </div>
            )}
          </div>

          <div className="evac-panel" style={{ display: activeTab === 'automation' ? 'flex' : 'none', height: "100%", paddingBottom: "2rem" }}>
            <AutomationPanel onTriggerSimulation={async (autoHobli, thresholdMm) => {
              sim.setStatusMsg("Sentinel Auto-Triggered!");
              await handleLoadRegion(autoHobli);
              sim.start(autoHobli, thresholdMm > 0 ? thresholdMm : 150, 5, 0.5, false, true, 'ga', 0);
              setActiveTab('evacuation');
            }} />
          </div>
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
        trafficRoadsData={
          compareResults && compareActiveAlgo
            ? (compareResults[compareActiveAlgo]?.traffic_geojson ?? null)
            : sim.trafficRoadsData
        }
        showTraffic={useTraffic && (sim.simulationDone || !!compareResults)}
        showTrafficPins={showTrafficPins}
        onToggleTrafficPins={() => setShowTrafficPins(v => !v)}
        busManifest={busManifest}
        selectedBusId={selectedBusId}
        mapPinBox={mapPinBox}
        onMapClick={async (lat, lon) => {
          if (isDraMode && pinDropMode) {
            // Cancel any in-flight resolve-pin request
            if (pinAbortRef.current) pinAbortRef.current.abort();
            pinAbortRef.current = new AbortController();
            setMapPinBox({ lat, lon });
            setPinResolvedHobli({ loading: true });
            try {
              const res = await axios.post(`${API_URL}/resolve-pin`, { lat, lon }, { signal: pinAbortRef.current.signal });
              setPinResolvedHobli(res.data);
            } catch (err) {
              if (axios.isCancel(err) || err.name === 'CanceledError') return;
              console.error("Failed to resolve pin:", err);
              setPinResolvedHobli({ error: "Could not resolve location. Try a different spot." });
            }
            return;
          }
          setMapPinBox(prev => {
            if (!prev) return { lat, lon };
            const dist = Math.abs(prev.lat - lat) + Math.abs(prev.lon - lon);
            if (dist < 0.005) return null; 
            return { lat, lon };
          });
        }}
        selectedMetro={selectedMetro}
        metroLines={metroLines}
      />

      <AppCopilot
        loadedHobli={loadedHobli}
        availableHoblis={regions.allHoblis || []}
        regionsTree={regions.regionsTree || {}}
        populationCount={populationCount}
        mapPin={mapPinBox}
        onNavigate={(tab) => {
          if (tab === 'evacuate' || tab === 'evacuation') {
            setActiveTab('evacuation');
            return;
          }
          if (tab === 'compare') {
            setCompareMode(true);
            setActiveTab('setup');
            return;
          }
          setActiveTab('setup');
        }}
        onSelectRegion={handleSelectRegion}
        onUpdateParams={({ algorithm: algo, rainfall, evacuationMode: evac, useTraffic: traffic }) => {
          if (algo) {
            if (algo === 'all') {
              setCompareMode(true);
            } else {
              setAlgorithm(algo);
              setCompareMode(false);
            }
          }
          if (rainfall) setRainfallMm(rainfall);
          if (evac !== undefined) setEvacuationMode(evac);
          if (traffic !== undefined) setUseTraffic(traffic);
        }}
        onRunSimulation={(newHobli, newRainfall, algo, evac, traffic) => {
          const runHobli = newHobli || loadedHobli;
          // Sync sidebar state so UI reflects what's actually running
          if (algo && algo !== 'all') setAlgorithm(algo);
          if (newRainfall) setRainfallMm(newRainfall);
          if (evac !== undefined) setEvacuationMode(evac);
          if (traffic !== undefined) setUseTraffic(traffic);

          if (runHobli) {
            setActiveTab('setup');
            if (algo === 'all' || (compareMode && !algo)) {
              setCompareMode(true);
              // Wait for React state to settle slightly since compare reads 'steps' and 'decayFactor'
              // but we pass our immediate overrides for the rest.
              setTimeout(() => {
                handleCompare(runHobli, newRainfall, evac, traffic);
              }, 0);
            } else {
              setCompareMode(false);
              sim.start(
                runHobli,
                newRainfall || 150,
                steps,    // use current state
                decayFactor,
                evac !== undefined ? evac : evacuationMode,
                traffic !== undefined ? traffic : useTraffic,
                algo || algorithm || 'aco',
                populationCount // pass population count to simulation
              );
            }
          }
        }}
      />

      <TutorialOverlay />
    </div>
  );
}
