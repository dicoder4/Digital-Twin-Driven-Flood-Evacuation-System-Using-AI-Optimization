import React, { useState } from 'react';
import Map, { Source, Layer, Marker, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import api from '../api';
import { Route, Loader, Shield, Mail, Download, ChevronDown, ChevronUp } from 'lucide-react';

const routeLayerStyle = {
  id: 'evac-routes', type: 'line',
  paint: {
    'line-color': ['get', 'color'],
    'line-width': 3,
    'line-opacity': 0.85,
  },
};

const floodBgStyle = {
  id: 'evac-flood-bg', type: 'fill',
  paint: { 'fill-color': '#93c5fd', 'fill-opacity': 0.25 },
};

const roadBgStyle = {
  id: 'evac-road-bg', type: 'line',
  paint: { 'line-color': '#d1d5db', 'line-width': 1, 'line-opacity': 0.5 },
};

export default function EvacuationPage({ appState, updateState }) {
  const [algorithm, setAlgorithm] = useState('Dijkstra');
  const [walkingSpeed, setWalkingSpeed] = useState(5);
  const [loading, setLoading] = useState('');
  const [result, setResult] = useState(null);
  const [showLog, setShowLog] = useState(false);

  const [viewState, setViewState] = useState({
    longitude: appState.center?.lon || 77.6101,
    latitude: appState.center?.lat || 12.9166,
    zoom: 14,
  });

  const prepareCenters = async () => {
    setLoading('centers');
    try {
      const r = await api.post('/evacuation/safe-centers');
      updateState({ safeCentersPrepared: true, safeCenters: r.data.centers });
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed');
    } finally {
      setLoading('');
    }
  };

  const runEvacuation = async () => {
    setLoading('run');
    try {
      const r = await api.post('/evacuation/run', { algorithm, walking_speed: walkingSpeed });
      setResult(r.data);
      updateState({ evacuationDone: true, evacuationResult: r.data });
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed');
    } finally {
      setLoading('');
    }
  };

  const emailAuthorities = async () => {
    if (!result) return;
    setLoading('email');
    try {
      await api.post('/evacuation/email-authorities', {
        algorithm: result.algorithm,
        avg_time: result.stats.avg_time,
        evacuated_count: result.stats.evacuated,
        total_at_risk: result.stats.total_flooded,
      });
      alert('✅ Evacuation plan sent to all authorities!');
    } catch (e) {
      alert(e.response?.data?.detail || 'Email failed');
    } finally {
      setLoading('');
    }
  };

  const downloadLog = () => {
    if (!result?.detailed_log_text) return;
    const blob = new Blob([result.detailed_log_text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evacuation_log_${algorithm.replace(/ /g, '_')}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const stats = result?.stats;

  return (
    <div className="flex h-full">
      <div className="w-80 bg-white p-6 overflow-y-auto border-r border-gray-200 space-y-5">
        <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
          <Route size={20} className="text-blue-600" /> Evacuation Planning
        </h2>

        {!appState.simulationRun ? (
          <div className="bg-yellow-50 border border-yellow-200 p-3 rounded-lg text-sm text-yellow-700">
            ⚠️ Run flood simulation first
          </div>
        ) : (
          <>
            {/* Algorithm */}
            <div>
              <label className="text-sm font-medium text-gray-600 block mb-1">Algorithm</label>
              <select value={algorithm} onChange={e => setAlgorithm(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                <option>Dijkstra</option>
                <option>A*</option>
                <option>Quanta Adaptive Routing</option>
                <option>Bidirectional</option>
              </select>
            </div>

            <div>
              <label className="flex justify-between text-sm font-medium text-gray-600">
                Walking Speed <span className="text-blue-600 font-bold">{walkingSpeed} km/h</span>
              </label>
              <input type="range" min="3" max="15" value={walkingSpeed}
                onChange={e => setWalkingSpeed(Number(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg accent-blue-600 mt-1" />
            </div>

            <button onClick={prepareCenters} disabled={loading === 'centers'}
              className="w-full py-3 bg-white border-2 border-indigo-600 text-indigo-600 hover:bg-indigo-50 font-bold rounded-lg flex items-center justify-center gap-2 disabled:opacity-50">
              {loading === 'centers' ? <Loader className="animate-spin" size={16} /> : <Shield size={16} />}
              {loading === 'centers' ? 'Finding...' : 'Prepare Safe Centers'}
            </button>

            {appState.safeCenters && (
              <p className="text-sm text-green-600">✅ {appState.safeCenters.length} safe centers found</p>
            )}

            <button onClick={runEvacuation} disabled={!appState.safeCentersPrepared || loading === 'run'}
              className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg flex items-center justify-center gap-2 disabled:opacity-50">
              {loading === 'run' ? <Loader className="animate-spin" size={16} /> : '🚁'}
              {loading === 'run' ? 'Calculating...' : 'Calculate Routes'}
            </button>

            {/* Results */}
            {stats && (
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-gray-700">🚨 Results ({result.algorithm})</h3>

                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-orange-50 p-2 rounded-lg text-center">
                    <p className="text-lg font-bold text-orange-600">{stats.total_flooded}</p>
                    <p className="text-[10px] text-orange-500">In Danger</p>
                  </div>
                  <div className="bg-blue-50 p-2 rounded-lg text-center">
                    <p className="text-lg font-bold text-blue-600">{stats.evacuated}</p>
                    <p className="text-[10px] text-blue-500">Evacuated</p>
                  </div>
                  <div className="bg-red-50 p-2 rounded-lg text-center">
                    <p className="text-lg font-bold text-red-600">{stats.unreachable}</p>
                    <p className="text-[10px] text-red-500">Unreachable</p>
                  </div>
                </div>

                <div className="bg-gray-50 p-3 rounded-lg text-sm space-y-1">
                  <p>✅ Success: <strong>{stats.success_rate}%</strong></p>
                  <p>⏱️ Avg Time: <strong>{stats.avg_time} min</strong></p>
                  <p>⏱️ Max Time: <strong>{stats.max_time} min</strong></p>
                  <p>⚡ Exec: <strong>{stats.execution_time}s</strong></p>
                </div>

                {/* Center Summary */}
                {result.center_summary && Object.keys(result.center_summary).length > 0 && (
                  <div>
                    <p className="text-sm font-bold text-gray-700 mb-1">🏥 Center Assignments</p>
                    {Object.entries(result.center_summary).map(([id, d]) => (
                      d.count > 0 && (
                        <div key={id} className="text-xs text-gray-600 py-1 border-b border-gray-100">
                          <strong>{id}</strong> — {d.count} people, {d.avg_time} min avg
                        </div>
                      )
                    ))}
                  </div>
                )}

                {/* Log */}
                <button onClick={() => setShowLog(!showLog)}
                  className="w-full flex items-center justify-between text-sm text-gray-600 hover:text-gray-800">
                  <span>📋 Evacuation Log</span>
                  {showLog ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {showLog && (
                  <div className="bg-gray-900 text-green-400 p-3 rounded-lg text-[10px] font-mono max-h-40 overflow-y-auto">
                    {result.log?.map((l, i) => <div key={i}>{l}</div>)}
                  </div>
                )}

                {/* Actions */}
                <div className="flex gap-2">
                  <button onClick={downloadLog}
                    className="flex-1 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm flex items-center justify-center gap-1">
                    <Download size={14} /> Log
                  </button>
                  <button onClick={emailAuthorities} disabled={loading === 'email'}
                    className="flex-1 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm flex items-center justify-center gap-1 disabled:opacity-50">
                    <Mail size={14} /> {loading === 'email' ? '...' : 'Email'}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <Map {...viewState} onMove={e => setViewState(e.viewState)}
          mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json" attributionControl={false}>
          <NavigationControl position="top-right" />

          {appState.edgesGeojson && (
            <Source id="evac-roads" type="geojson" data={appState.edgesGeojson}>
              <Layer {...roadBgStyle} />
            </Source>
          )}

          {appState.floodGeojson && (
            <Source id="evac-flood" type="geojson" data={appState.floodGeojson}>
              <Layer {...floodBgStyle} />
            </Source>
          )}

          {result?.routes_geojson && (
            <Source id="evac-routes" type="geojson" data={result.routes_geojson}>
              <Layer {...routeLayerStyle} />
            </Source>
          )}

          {/* Safe center markers */}
          {appState.safeCenters?.map((c, i) => (
            <Marker key={`sc-${i}`} longitude={c.lon} latitude={c.lat} anchor="center">
              <div title={c.center_id} className={`${c.type === 'hospital' ? 'bg-red-500' : 'bg-blue-600'} text-white rounded-full w-6 h-6 flex items-center justify-center text-[10px] font-bold shadow-lg border-2 border-white`}>
                {c.type === 'hospital' ? '+' : 'P'}
              </div>
            </Marker>
          ))}
        </Map>

        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white/95 backdrop-blur p-4 rounded-xl border border-gray-200 text-xs shadow-lg min-w-[140px]">
          <p className="font-bold text-gray-800 mb-2">Routes</p>
          <div className="flex items-center gap-2 mb-1"><div className="w-4 h-1 bg-purple-600 rounded" /> Evacuation Route</div>
          <div className="flex items-center gap-2 mb-1"><div className="w-3 h-3 rounded-full bg-red-500 text-white flex items-center justify-center text-[8px]">+</div> Hospital</div>
          <div className="flex items-center gap-2 mb-1"><div className="w-3 h-3 rounded-full bg-blue-600 text-white flex items-center justify-center text-[8px]">P</div> Police</div>
          <div className="flex items-center gap-2"><div className="w-4 h-3 bg-blue-200 opacity-50 rounded" /> Flood Zone</div>
        </div>
      </div>
    </div>
  );
}
