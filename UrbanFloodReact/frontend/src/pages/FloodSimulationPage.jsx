import React, { useState, useEffect, useRef, useCallback } from 'react';
import Map, { Source, Layer, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import api from '../api';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import {
  CloudRain, Loader, Users, Gauge, Play, Pause, RotateCcw,
  Zap, AlertTriangle, CheckCircle2, XCircle, Activity
} from 'lucide-react';

/* ---- Map layer styles ---- */
const floodLayerStyle = {
  id: 'sim-flood-layer', type: 'fill',
  paint: {
    'fill-color': ['interpolate', ['linear'], ['get', 'intensity'],
      0, 'rgba(0, 140, 255, 0.4)',    // Bright Blue (Start)
      0.3, 'rgba(0, 100, 230, 0.6)',  // Mid Blue
      0.6, 'rgba(0, 60, 200, 0.75)',  // Deep Blue
      1, 'rgba(0, 20, 160, 0.9)'],    // Darkest Blue
    'fill-opacity': 0.85,
  },
};
const roadRiskStyle = {
  id: 'sim-road-risk', type: 'line',
  paint: {
    'line-color': ['match', ['get', 'risk'],
      'high', '#ef4444', 'medium', '#f59e0b', 'low', '#22c55e', '#999'],
    'line-width': ['match', ['get', 'risk'],
      'high', 3.5, 'medium', 2.5, 'low', 1.5, 1],
    'line-opacity': 0.85,
  },
};
const peopleLayerStyle = {
  id: 'sim-people', type: 'circle',
  paint: {
    'circle-radius': 5,
    'circle-color': ['match', ['get', 'status'], 'danger', '#ef4444', '#22c55e'],
    'circle-stroke-width': 1.5, 'circle-stroke-color': '#fff',
  },
};
const roadBgStyle = {
  id: 'sim-road-bg', type: 'line',
  paint: { 'line-color': '#94a3b8', 'line-width': 1.5, 'line-opacity': 0.5 },
};

/* ---- Constants ---- */
const TOTAL_STEPS = 20;
// Steps are for animation smoothness, not magnitude definition


export default function FloodSimulationPage({ appState, updateState }) {
  /* State */
  const [numPeople, setNumPeople] = useState(50);
  const [loading, setLoading] = useState('');
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1200);       // ms between steps
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);       // [{step, level, atrisk, safe}]
  const [targetFloodPercent, setTargetFloodPercent] = useState(100); // User defined max flood
  const intervalRef = useRef(null);

  const [viewState, setViewState] = useState({
    longitude: appState.center?.lon || 77.6101,
    latitude: appState.center?.lat || 12.9166,
    zoom: 14,
  });

  /* Sync center when network changes */
  useEffect(() => {
    if (appState.center) {
      setViewState(v => ({ ...v, longitude: appState.center.lon, latitude: appState.center.lat }));
    }
  }, [appState.center]);

  /* ---- Init Simulator ---- */
  const initSimulator = async () => {
    setLoading('init');
    try {
      await api.post('/simulation/init', { initial_people: numPeople }, { timeout: 30000 });
      updateState({ simulatorInitialized: true });
      setCurrentStep(0);
      setStats(null);
      setHistory([]);
      // Clear map layers
      updateState({ floodGeojson: null, blockedRoadsGeojson: null, peopleGeojson: null });
    } catch (e) {
      alert(e.response?.data?.detail || 'Init failed');
    } finally {
      setLoading('');
    }
  };

  /* ---- Single step ---- */
  const fetchStep = useCallback(async (step, overrideLevel = null) => {
    // If overrideLevel is provided (manual drag), use it.
    // Otherwise, calculate based on step progress towards target.
    // flood_level sent to backend is 0.0 - 1.0 (fraction of Peak)
    let floodPct;
    
    if (overrideLevel !== null) {
      floodPct = overrideLevel;
    } else {
      // Linear interpolation: Step 0 = 0%, Step 20 = targetFloodPercent%
      floodPct = (step / TOTAL_STEPS) * targetFloodPercent;
    }

    // Ensure within bounds 0-100
    floodPct = Math.min(Math.max(floodPct, 0), 100);
    
    try {
      const r = await api.post('/simulation/update', {
        flood_level: floodPct / 100, // Send fraction 0.0 - 1.0
        num_people: numPeople,
      }, { timeout: 15000 });

      setStats(r.data.stats);
      updateState({
        floodGeojson: r.data.flood_geojson,
        blockedRoadsGeojson: r.data.blocked_roads_geojson,
        peopleGeojson: r.data.people_geojson,
        simulationRun: true, // Unlock Evacuation Page
      });

      const newRecord = {
        step,
        level: Math.round(floodPct),
        atrisk: r.data.stats.flooded_people,
        safe: r.data.stats.safe_people
      };
      setHistory(prev => {
        // Avoid duplicates
        const filtered = prev.filter(p => p.step !== step);
        return [...filtered, newRecord].sort((a, b) => a.step - b.step);
      });

    } catch (e) {
      console.error(e);
      if (step === 0 && !appState.simulatorInitialized) {
         // suppress error if just resetting
      } else {
         // alert('Simulation step failed');
      }
    }
  }, [numPeople, updateState, appState.simulatorInitialized, targetFloodPercent]);

  /* ---- Auto-play loop ---- */
  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= TOTAL_STEPS) {
            setIsPlaying(false);
            return prev;
          }
          const next = prev + 1;
          fetchStep(next); // No override, use step logic
          return next;
        });
      }, speed);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [isPlaying, speed, fetchStep]);

  /* ---- Handlers ---- */
  const handlePlay = () => {
    if (currentStep >= TOTAL_STEPS) {
      setCurrentStep(0);
      updateState({ floodGeojson: null });
      fetchStep(0);
    }
    setIsPlaying(true);
  };
  const handlePause = () => setIsPlaying(false);
  const handleReset = () => {
    setIsPlaying(false);
    setCurrentStep(0);
    setStats(null);
    setHistory([]);
    updateState({ floodGeojson: null, blockedRoadsGeojson: null, peopleGeojson: null });
  };

  const handleManualFloodChange = (val) => {
    const pct = Number(val);
    setTargetFloodPercent(pct);
    // Preview immediately without changing "step" (or maybe set step to max to show completion?)
    // Let's just update the visual state directly
    fetchStep(currentStep, pct); 
  };

  // Calculate current display percentage for labels
  const currentFloodDisplay = isPlaying 
    ? Math.round((currentStep / TOTAL_STEPS) * targetFloodPercent) 
    : targetFloodPercent;
  const speedLabel = speed < 1000 ? 'Fast' : speed > 2000 ? 'Slow' : 'Normal';

  const riskColor = (level) => {
    if (level === 'CRITICAL') return 'bg-red-100 text-red-700 border-red-200';
    if (level === 'HIGH') return 'bg-orange-100 text-orange-700 border-orange-200';
    if (level === 'MEDIUM') return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    return 'bg-green-100 text-green-700 border-green-200';
  }

  return (
    <div className="flex h-full">
      {/* Sidebar Controls */}
      <div className="w-80 bg-white p-5 overflow-y-auto border-r border-gray-200 space-y-6 flex flex-col">
        {/* Header */}
        <div>
          <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <CloudRain size={24} className="text-blue-500" /> Flood Simulation
          </h2>
          <p className="text-xs text-gray-500 mt-1">Simulate water rise & evacuation</p>
        </div>

        {appState.networkLoaded && (
          <>
            {/* Population slider */}
            <div>
              <label className="flex justify-between text-sm font-medium text-gray-600">
                <span className="flex items-center gap-1"><Users size={14} /> Population</span>
                <span className="text-blue-600 font-bold">{numPeople}</span>
              </label>
              <input type="range" min="10" max="200" step="10" value={numPeople}
                onChange={e => setNumPeople(Number(e.target.value))}
                disabled={isPlaying}
                className="w-full h-2 bg-gray-200 rounded-lg accent-blue-600 mt-1" />
            </div>

            {/* Init button */}
            <button onClick={initSimulator} disabled={loading === 'init' || isPlaying}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg flex items-center justify-center gap-2 disabled:opacity-50 transition-colors">
              {loading === 'init' ? <Loader className="animate-spin" size={16} /> : <Zap size={16} />}
              {loading === 'init' ? 'Initializing...' : appState.simulatorInitialized ? 'Re-Initialize' : 'Initialize Simulator'}
            </button>

            {appState.simulatorInitialized && (
              <>
                {/* ---- Playback Controls ---- */}
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-4 rounded-xl border border-blue-200 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-blue-800 flex items-center gap-1">
                      <Activity size={14} /> Simulation Controls
                    </span>
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                      {speedLabel}
                    </span>
                  </div>

                  {/* Play / Pause / Reset */}
                  <div className="flex gap-2">
                    {!isPlaying ? (
                      <button onClick={handlePlay}
                        className="flex-1 py-2.5 bg-green-500 hover:bg-green-600 text-white font-bold rounded-lg flex items-center justify-center gap-2 transition-colors shadow-sm">
                        <Play size={16} fill="white" /> {currentStep >= TOTAL_STEPS ? 'Replay' : 'Play'}
                      </button>
                    ) : (
                      <button onClick={handlePause}
                        className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 text-white font-bold rounded-lg flex items-center justify-center gap-2 transition-colors shadow-sm">
                        <Pause size={16} /> Pause
                      </button>
                    )}
                    <button onClick={handleReset}
                      className="px-4 py-2.5 bg-gray-200 hover:bg-gray-300 text-gray-700 font-bold rounded-lg flex items-center justify-center gap-1 transition-colors">
                      <RotateCcw size={14} /> Reset
                    </button>
                  </div>

                  {/* Speed slider */}
                  <div>
                    <label className="flex justify-between text-xs font-medium text-blue-700">
                      <span>Speed</span>
                      <span>{(speed / 1000).toFixed(1)}s/step</span>
                    </label>
                    <input type="range" min="400" max="3000" step="200" value={speed}
                      onChange={e => setSpeed(Number(e.target.value))}
                      className="w-full h-1.5 bg-blue-200 rounded-lg accent-blue-600 mt-1"
                      style={{ direction: 'rtl' }} />
                    <div className="flex justify-between text-[10px] text-blue-400 mt-0.5">
                      <span>Fast</span><span>Slow</span>
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div>
                    <div className="flex justify-between text-xs font-medium text-blue-800 mb-1">
                      <span>Step {currentStep}/{TOTAL_STEPS}</span>
                      <span className="text-blue-600 font-bold">Flood: {Math.round((currentStep / TOTAL_STEPS) * targetFloodPercent)}%</span>
                    </div>
                    <div className="h-2.5 bg-blue-100 rounded-full overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-blue-400 to-blue-600 rounded-full transition-all duration-500"
                        style={{ width: `${(currentStep / TOTAL_STEPS) * 100}%` }} />
                    </div>
                  </div>

                  {/* Manual Flood Target Slider */}
                  <div>
                    <label className="text-xs font-bold text-blue-800 flex justify-between">
                      Target Flood Level
                      <span className="font-normal text-blue-600">{targetFloodPercent}%</span>
                    </label>
                    <input type="range" min="0" max="100" step="1" value={targetFloodPercent}
                      onChange={e => handleManualFloodChange(e.target.value)}
                      disabled={isPlaying}
                      className="w-full h-1.5 bg-blue-200 rounded-lg accent-blue-600 mt-1 cursor-pointer" />
                    <p className="text-[10px] text-gray-500 mt-1">
                      Set max flood spread. Drag to preview, Play to simulate rise.
                    </p>
                  </div>
                </div>

                {/* ---- Live Stats ---- */}
                {stats && (
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 gap-2">
                      <div className="bg-gray-50 p-2 rounded-lg text-center border border-gray-100">
                        <p className="text-lg font-bold text-gray-800">{stats.total_people}</p>
                        <p className="text-[10px] text-gray-500 uppercase">Total</p>
                      </div>
                      <div className="bg-red-50 p-2 rounded-lg text-center border border-red-100">
                        <p className="text-lg font-bold text-red-600">{stats.flooded_people}</p>
                        <p className="text-[10px] text-red-500 uppercase">At Risk</p>
                      </div>
                      <div className="bg-green-50 p-2 rounded-lg text-center border border-green-100">
                        <p className="text-lg font-bold text-green-600">{stats.safe_people}</p>
                        <p className="text-[10px] text-green-500 uppercase">Safe</p>
                      </div>
                    </div>
                    <div className={`p-3 rounded-lg border text-sm font-bold text-center ${riskColor(stats.risk_level)}`}>
                      {stats.risk_level} — {stats.risk_pct}% at risk
                    </div>
                  </div>
                )}

                {/* ---- Timeline Chart ---- */}
                {history.length > 1 && (
                  <div className="bg-gray-50 p-3 rounded-xl border border-gray-200">
                    <p className="text-xs font-bold text-gray-600 mb-2">Flood Impact Over Time</p>
                    <ResponsiveContainer width="100%" height={100}>
                      <AreaChart data={history}>
                        <defs>
                          <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.6} />
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
                          </linearGradient>
                          <linearGradient id="safeGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.6} />
                            <stop offset="95%" stopColor="#22c55e" stopOpacity={0.05} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="level" tick={{ fontSize: 9 }} tickFormatter={v => `${v}%`} />
                        <YAxis tick={{ fontSize: 9 }} width={25} />
                        <Tooltip contentStyle={{ fontSize: 11 }}
                          formatter={(v, name) => [v, name === 'atrisk' ? 'At Risk' : 'Safe']}
                          labelFormatter={l => `Flood: ${l}%`} />
                        <Area type="monotone" dataKey="atrisk" stroke="#ef4444" fill="url(#riskGrad)" strokeWidth={2} />
                        <Area type="monotone" dataKey="safe" stroke="#22c55e" fill="url(#safeGrad)" strokeWidth={2} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      {/* ---- Map ---- */}
      <div className="flex-1 relative">
        <Map {...viewState} onMove={e => setViewState(e.viewState)}
          mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json" attributionControl={false}>
          <NavigationControl position="top-right" />

          {appState.edgesGeojson && (
            <Source id="sim-road-bg" type="geojson" data={appState.edgesGeojson}>
              <Layer {...roadBgStyle} />
            </Source>
          )}
          {appState.floodGeojson && (
            <Source id="sim-flood" type="geojson" data={appState.floodGeojson}>
              <Layer {...floodLayerStyle} />
            </Source>
          )}
          {appState.blockedRoadsGeojson && (
            <Source id="sim-blocked" type="geojson" data={appState.blockedRoadsGeojson}>
              <Layer {...roadRiskStyle} />
            </Source>
          )}
          {appState.peopleGeojson && (
            <Source id="sim-people" type="geojson" data={appState.peopleGeojson}>
              <Layer {...peopleLayerStyle} />
            </Source>
          )}
        </Map>

        {/* Flood level HUD */}
        {(currentStep > 0 || !isPlaying) && appState.floodGeojson && (
          <div className="absolute top-4 left-4 bg-white/95 backdrop-blur-md px-4 py-2 rounded-xl text-gray-800 flex items-center gap-3 shadow-lg border border-gray-200">
            <CloudRain size={18} className="text-blue-500" />
            <div>
              <p className="text-sm font-bold">Flood Level: {currentFloodDisplay}%</p>
              <p className="text-[10px] text-gray-500">Step {currentStep} of {TOTAL_STEPS}</p>
            </div>
            {isPlaying && <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />}
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white/95 backdrop-blur-md p-4 rounded-xl text-xs text-gray-700 shadow-lg min-w-[150px] border border-gray-200">
          <p className="font-bold mb-2 text-gray-900">Legend</p>
          <div className="flex items-center gap-2 mb-1"><div className="w-3 h-3 rounded-full bg-green-500" /> Safe Person</div>
          <div className="flex items-center gap-2 mb-1"><div className="w-3 h-3 rounded-full bg-red-500" /> At-Risk Person</div>
          <div className="flex items-center gap-2 mb-1"><div className="w-6 h-2 rounded bg-blue-500/80" /> Flood Water</div>
          <div className="flex items-center gap-2 mb-1"><div className="w-6 h-1 bg-red-500 rounded" /> High Risk Road</div>
          <div className="flex items-center gap-2 mb-1"><div className="w-6 h-1 bg-amber-500 rounded" /> Medium Risk Road</div>
          <div className="flex items-center gap-2"><div className="w-6 h-1 bg-green-500 rounded" /> Low Risk Road</div>
        </div>

        {/* Empty state */}
        {!appState.simulatorInitialized && appState.networkLoaded && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="bg-white/90 backdrop-blur p-6 rounded-xl shadow-lg text-center border border-gray-100">
              <CloudRain size={32} className="mx-auto text-blue-400 mb-2" />
              <p className="text-gray-600 font-medium">Initialize the simulator to start</p>
              <p className="text-gray-400 text-sm">Then use controls to simulate flood</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
