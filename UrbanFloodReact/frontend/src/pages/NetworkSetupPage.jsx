import React, { useState, useEffect, useRef } from 'react';
import Map, { Source, Layer, Marker, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import api from '../api';
import { MapPin, RefreshCw, Building2, Loader, CheckCircle2, Zap } from 'lucide-react';

const roadLayerStyle = {
  id: 'setup-road-layer',
  type: 'line',
  paint: { 'line-color': '#3b82f6', 'line-width': 1.5, 'line-opacity': 0.7 },
};

export default function NetworkSetupPage({ appState, updateState }) {
  const [states, setStates] = useState([]);
  const [stations, setStations] = useState([]);
  const [selectedState, setSelectedState] = useState('');
  const [selectedStation, setSelectedStation] = useState(null);
  const [networkDist, setNetworkDist] = useState(2000);
  const [filterMinor, setFilterMinor] = useState(true);
  const [loading, setLoading] = useState('');
  const [stationsLoading, setStationsLoading] = useState(false);
  const [geoWarning, setGeoWarning] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef(null);

  const [viewState, setViewState] = useState({
    longitude: 77.6101, latitude: 12.9166, zoom: 13,
  });

  useEffect(() => {
    api.get('/locations/states').then(r => setStates(r.data.states));
  }, []);

  const loadStations = async (state) => {
    setSelectedState(state);
    setStationsLoading(true);
    setGeoWarning(null);
    try {
      const r = await api.get(`/locations/stations?state=${state}`);
      setStations(r.data.stations);
    } catch (e) {
      console.error(e);
    } finally {
      setStationsLoading(false);
    }
  };

  const loadNetwork = async () => {
    if (!selectedStation) return;
    setLoading('network');
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed(t => t + 1), 1000);
    try {
      const r = await api.post('/locations/network', {
        location_name: `${selectedStation.station}, ${selectedStation.district}, ${selectedState}, India`,
        lat: selectedStation.lat,
        lon: selectedStation.lon,
        station_name: selectedStation.station,
        peak_flood_level: selectedStation.peak_flood_level,
        network_dist: networkDist,
        filter_minor: filterMinor,
      }, { timeout: 120000 });
      updateState({
        networkLoaded: true,
        edgesGeojson: r.data.edges_geojson,
        center: r.data.center,
      });
      setViewState({ longitude: r.data.center.lon, latitude: r.data.center.lat, zoom: 14 });
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to load network');
    } finally {
      clearInterval(timerRef.current);
      setLoading('');
    }
  };

  const loadInfra = async () => {
    if (!selectedStation) return;
    setLoading('infra');
    try {
      const locationName = `${selectedStation.station}, ${selectedStation.district}, ${selectedState}, India`;
      const r = await api.post('/locations/infrastructure', { location_name: locationName });
      updateState({
        infrastructureLoaded: true,
        infrastructure: {
          hospitals: r.data.hospitals_geojson || [],
          police: r.data.police_geojson || [],
        },
      });
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to load infrastructure');
    } finally {
      setLoading('');
    }
  };

  const initializeAll = async () => {
    if (!selectedStation) return;
    setLoading('all');
    setElapsed(0);
    timerRef.current = setInterval(() => setElapsed(t => t + 1), 1000);

    try {
      // 1. Load Network
      const netReq = {
        location_name: `${selectedStation.station}, ${selectedStation.district}, ${selectedState}, India`,
        lat: selectedStation.lat,
        lon: selectedStation.lon,
        station_name: selectedStation.station,
        peak_flood_level: selectedStation.peak_flood_level,
        network_dist: networkDist,
        filter_minor: filterMinor,
      };
      const networkRes = await api.post('/locations/network', netReq, { timeout: 120000 });
      updateState({
        networkLoaded: true,
        edgesGeojson: networkRes.data.edges_geojson,
        center: networkRes.data.center,
      });
      setViewState({ longitude: networkRes.data.center.lon, latitude: networkRes.data.center.lat, zoom: 14 });

      // 2. Load Infrastructure
      const infraRes = await api.post('/locations/infrastructure', { location_name: netReq.location_name });
      updateState({
        infrastructureLoaded: true,
        infrastructure: {
          hospitals: infraRes.data.hospitals_geojson || [],
          police: infraRes.data.police_geojson || [],
        },
      });

      // 3. Initialize Simulator (default 50 people)
      await api.post('/simulation/init', { initial_people: 50 }, { timeout: 30000 });
      updateState({ simulatorInitialized: true });

      alert("✅ System Ready! Network, Infrastructure, and Simulator initialized.");
      
    } catch (e) {
      console.error(e);
      alert(e.response?.data?.detail || 'Initialization failed');
    } finally {
      clearInterval(timerRef.current);
      setLoading('');
    }
  };

  return (
    <div className="flex h-full">
      {/* Controls */}
      <div className="w-80 bg-white p-6 overflow-y-auto border-r border-gray-200 space-y-5">
        <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
          <MapPin size={20} className="text-blue-600" /> Network Setup
        </h2>

        {/* State */}
        <div>
          <label className="text-sm font-medium text-gray-600 block mb-1">State</label>
          <select value={selectedState} onChange={e => loadStations(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
            <option value="">Select state...</option>
            {states.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
          </select>
        </div>

        {/* Station */}
        {stationsLoading && <p className="text-sm text-blue-600 flex items-center gap-2"><Loader size={14} className="animate-spin" /> Loading stations...</p>}
        {stations.length > 0 && (
          <div>
            <label className="text-sm font-medium text-gray-600 block mb-1">Station ({stations.length} found)</label>
            <select
              value={selectedStation ? `${selectedStation.station}|${selectedStation.district}` : ''}
              onChange={async (e) => {
                const [st, di] = e.target.value.split('|');
                const s = stations.find(x => x.station === st && x.district === di);
                if (!s) { setSelectedStation(null); return; }
                
                setSelectedStation({ ...s, lat: null, lon: null });
                setGeoWarning(null);
                setLoading('geocode');
                
                try {
                  const r = await api.get(`/locations/geocode?station=${encodeURIComponent(st)}&district=${encodeURIComponent(di)}&state=${encodeURIComponent(selectedState)}`);
                  const updated = { ...s, lat: r.data.lat, lon: r.data.lon };
                  setSelectedStation(updated);
                  setViewState({ longitude: r.data.lon, latitude: r.data.lat, zoom: 13 });
                  
                  if (r.data.warning) {
                    setGeoWarning(r.data.warning);
                  }
                } catch (err) {
                  console.error('Geocoding failed', err);
                  alert("Could not locate station. Please try another or check connection.");
                } finally {
                  setLoading('');
                }
              }}
              className="w-full px-3 py-2 rounded-lg border border-gray-200 text-sm focus:ring-2 focus:ring-blue-500 outline-none">
              <option value="">Select station...</option>
              {stations.map(s => (
                <option key={`${s.station}|${s.district}`} value={`${s.station}|${s.district}`}>
                  {s.station} ({s.district})
                </option>
              ))}
            </select>
          </div>
        )}

        {loading === 'geocode' && <p className="text-sm text-blue-600 flex items-center gap-2"><Loader size={14} className="animate-spin" /> Locating station...</p>}
        
        {geoWarning && (
          <div className="bg-yellow-50 border border-yellow-200 p-2 rounded text-xs text-yellow-700">
            ⚠️ {geoWarning}
          </div>
        )}

        {selectedStation && (
          <div className="bg-blue-50 p-3 rounded-lg text-sm text-blue-800 space-y-1">
            <p><strong>{selectedStation.station}</strong></p>
            <p>District: {selectedStation.district}</p>
            {selectedStation.lat && <p>Coords: {selectedStation.lat.toFixed(4)}, {selectedStation.lon.toFixed(4)}</p>}
            <div className="flex items-center gap-2 mt-1">
              <label className="text-gray-700 font-medium">Peak Flood:</label>
              <input type="number" step="0.1" min="1" max="50"
                value={selectedStation.peak_flood_level}
                onChange={e => setSelectedStation({...selectedStation, peak_flood_level: Number(e.target.value)})}
                className="w-20 px-2 py-1 rounded border border-blue-300 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
              />
              <span className="text-gray-500">m</span>
            </div>
          </div>
        )}

        {/* Network Params */}
        <div>
          <label className="flex justify-between text-sm font-medium text-gray-600">
            Network Radius <span className="text-blue-600 font-bold">{networkDist}m</span>
          </label>
          <input type="range" min="1000" max="5000" step="100" value={networkDist}
            onChange={e => setNetworkDist(Number(e.target.value))}
            className="w-full h-2 bg-gray-200 rounded-lg accent-blue-600 mt-1" />
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" checked={filterMinor} onChange={e => setFilterMinor(e.target.checked)}
            className="accent-blue-600" /> Filter minor roads
        </label>

        {/* Buttons */}
        <button onClick={initializeAll} disabled={!selectedStation || !selectedStation.lat || loading !== ''}
          className="w-full py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-md">
          {loading === 'all' ? <Loader className="animate-spin" size={16} /> : <Zap size={16} fill="white" />}
          {loading === 'all' ? 'Initializing System...' : '⚡ Initialize Everything'}
        </button>

        <div className="flex items-center gap-2 my-2">
          <div className="h-px bg-gray-200 flex-1"></div>
          <span className="text-xs text-gray-400">OR LOAD INDIVIDUALLY</span>
          <div className="h-px bg-gray-200 flex-1"></div>
        </div>

        <button onClick={loadNetwork} disabled={!selectedStation || !selectedStation.lat || loading !== ''}
          className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
          {loading === 'network' ? <Loader className="animate-spin" size={16} /> : <RefreshCw size={16} />}
          {loading === 'network' ? 'Loading...' : 'Load Road Network'}
        </button>
        {loading === 'network' && (
          <p className="text-xs text-gray-500 text-center animate-pulse">
            Downloading road data from OSM... {elapsed}s {elapsed > 10 && '(first load is slower, cached next time)'}
          </p>
        )}

        <button onClick={loadInfra} disabled={!appState.networkLoaded || loading === 'infra'}
          className="w-full py-3 bg-white border-2 border-blue-600 text-blue-600 hover:bg-blue-50 font-bold rounded-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2">
          {loading === 'infra' ? <Loader className="animate-spin" size={16} /> : <Building2 size={16} />}
          {loading === 'infra' ? 'Loading...' : 'Load Infrastructure'}
        </button>

        {/* Status */}
        {appState.networkLoaded && (
          <div className="flex items-center gap-2 text-green-600 text-sm">
            <CheckCircle2 size={14} /> Network loaded
          </div>
        )}
        {appState.infrastructureLoaded && (
          <div className="flex items-center gap-2 text-green-600 text-sm">
            <CheckCircle2 size={14} /> Infrastructure loaded
            <span className="text-gray-500">
              ({appState.infrastructure?.hospitals?.length || 0} hospitals, {appState.infrastructure?.police?.length || 0} police)
            </span>
          </div>
        )}
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <Map {...viewState} onMove={e => setViewState(e.viewState)}
          mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json" attributionControl={false}>
          <NavigationControl position="top-right" />

          {appState.edgesGeojson && (
            <Source id="setup-roads" type="geojson" data={appState.edgesGeojson}>
              <Layer {...roadLayerStyle} />
            </Source>
          )}

          {/* Hospital markers */}
          {appState.infrastructure?.hospitals?.map((h, i) => (
            <Marker key={`h-${i}`} longitude={h.lon} latitude={h.lat} anchor="center">
              <div title={h.name} className="bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold shadow">+</div>
            </Marker>
          ))}

          {/* Police markers */}
          {appState.infrastructure?.police?.map((p, i) => (
            <Marker key={`p-${i}`} longitude={p.lon} latitude={p.lat} anchor="center">
              <div title={p.name} className="bg-blue-600 text-white rounded-full w-5 h-5 flex items-center justify-center text-[10px] font-bold shadow">P</div>
            </Marker>
          ))}

          {/* Center marker */}
          {selectedStation && selectedStation.lat && (
            <Marker longitude={selectedStation.lon} latitude={selectedStation.lat} anchor="center">
              <div className="bg-green-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-[10px] font-bold shadow-lg border-2 border-white">★</div>
            </Marker>
          )}
        </Map>

        {!appState.edgesGeojson && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="bg-white/90 backdrop-blur p-6 rounded-xl shadow-lg text-center">
              <MapPin size={32} className="mx-auto text-blue-400 mb-2" />
              <p className="text-gray-600 font-medium">Select a station and load the road network</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
