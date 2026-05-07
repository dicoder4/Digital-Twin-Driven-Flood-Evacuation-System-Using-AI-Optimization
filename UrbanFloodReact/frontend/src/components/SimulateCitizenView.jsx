import React, { useState, useRef, useEffect } from 'react';
import Map, { Source, Layer, NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { AlertCircle, RotateCcw, Navigation, Cloud, Droplets, MapPin, Clock } from 'lucide-react';
import { API_URL } from '../config';
import '../styles/simulate.css';

const INITIAL_VIEW_STATE = {
  longitude: 77.5946,
  latitude: 12.9716,
  zoom: 13,
};

function toHeatmapFeatures(items) {
  if (!items || items.length === 0) return [];
  return items.map(h => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [h.lon, h.lat] },
    properties: { intensity: h.intensity, hobli: h.hobli },
  }));
}

// Rain particles background overlay
const RainOverlay = ({ intensity }) => {
  if (intensity < 50) return null;
  const opacity = Math.min(0.4, intensity / 200);
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        background: `radial-gradient(circle at 50% 50%, rgba(100, 181, 246, ${opacity}), transparent)`,
        pointerEvents: 'none',
        zIndex: 5,
        animation: `rainPulse ${2 + Math.random()}s infinite`,
      }}
    />
  );
};

// Phone-like notification banner
const NotificationBanner = ({ message, type, icon: Icon }) => {
  if (!message) return null;
  const bgColor = {
    warning: '#fef3c7',
    error: '#fee2e2',
    info: '#dbeafe',
    success: '#dcfce7',
  }[type] || '#f3f4f6';
  const borderColor = {
    warning: '#fcd34d',
    error: '#fca5a5',
    info: '#93c5fd',
    success: '#86efac',
  }[type] || '#e5e7eb';
  const textColor = {
    warning: '#92400e',
    error: '#991b1b',
    info: '#0c4a6e',
    success: '#166534',
  }[type] || '#374151';

  return (
    <div
      style={{
        background: bgColor,
        border: `1px solid ${borderColor}`,
        color: textColor,
        padding: '0.75rem 1rem',
        borderRadius: '0.375rem',
        display: 'flex',
        gap: '0.75rem',
        alignItems: 'flex-start',
        animation: 'slideInDown 0.3s ease-out',
        marginBottom: '0.75rem',
      }}
    >
      {Icon && <Icon size={20} style={{ flexShrink: 0, marginTop: '2px' }} />}
      <div style={{ flex: 1, fontSize: '0.875rem', lineHeight: '1.5' }}>{message}</div>
    </div>
  );
};

export default function SimulateCitizenView({ user, onLogout, lang, onToggleLang }) {
  const [phase, setPhase] = useState('SELECT_START');
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [routeData, setRouteData] = useState(null);
  const [alternativeRoutes, setAlternativeRoutes] = useState([]);
  const [floodOverlay, setFloodOverlay] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [personPos, setPersonPos] = useState(null);
  const [heatmap, setHeatmap] = useState([]);
  const [routeHistory, setRouteHistory] = useState([]);
  const [tick, setTick] = useState(0);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [maxFloodIntensity, setMaxFloodIntensity] = useState(0);
  const [shelterEvacuation, setShelterEvacuation] = useState(null);
  const [originalRouteMaxDepth, setOriginalRouteMaxDepth] = useState(null);

  // Config
  const [speedMode, setSpeedMode] = useState('car');
  const [intensity, setIntensity] = useState('heavy'); // Heavy rainfall to show realistic floods
  const [evolutionMode, setEvolutionMode] = useState('random');
  const [month, setMonth] = useState('random');
  const [searchQuery, setSearchQuery] = useState('');
  const [draggedMarker, setDraggedMarker] = useState(null);
  const clickCountRef = useRef({ start: 0, end: 0, startTime: 0, endTime: 0 });

  // Speed reference (must match backend SPEED_MAP)
  const SPEED_CONFIG = {
    car: { label: '🚗 Car (30 km/h)', speed_kph: 30 },
    bike: { label: '🚴 Bike (15 km/h)', speed_kph: 15 },
    walk: { label: '🚶 Walking (4 km/h)', speed_kph: 4 },
  };

  const tickTimerRef = useRef(null);
  const mapRef = useRef(null);
  const notificationTimeoutRef = useRef(null);
  const markerStartRef = useRef({ lat: 0, lon: 0 });

  useEffect(() => () => { if (tickTimerRef.current) clearInterval(tickTimerRef.current); }, []);

  // Auto-compute routes when both points are set
  useEffect(() => {
    if (startPoint && endPoint && phase === 'SELECT_END') {
      addNotification('🔄 Computing routes...', 'info');
      fetchRoutes(startPoint, endPoint);
    }
  }, [startPoint, endPoint, phase]);

  const addNotification = (msg, type = 'info') => {
    const id = Date.now();
    setNotifications(prev => [...prev, { id, msg, type }]);
    if (notificationTimeoutRef.current) clearTimeout(notificationTimeoutRef.current);
    notificationTimeoutRef.current = setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 3500);
  };

  const handleMapClick = (e) => {
    const { lat, lng: lon } = e.lngLat;

    if (draggedMarker) return; // Don't click if dragging

    if (phase === 'SELECT_START') {
      setStartPoint({ lat, lon });
      setPhase('SELECT_END');
      addNotification('📍 Start point set. Tap destination.', 'info');
    } else if (phase === 'SELECT_END') {
      setEndPoint({ lat, lon });
      addNotification('🔄 Computing routes...', 'info');
      fetchRoutes(startPoint, { lat, lon });
    }
  };

  const handleSearchLocation = async (query) => {
    if (!query.trim()) return;
    setSearchQuery('');
    addNotification('🔍 Searching location...', 'info');

    try {
      const res = await fetch(`${API_URL}/citizen/geocode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query,
          near_lat: viewState.latitude,
          near_lon: viewState.longitude,
        }),
      }).then(r => r.json());

      if (!res || res.length === 0) {
        addNotification('❌ Location not found', 'error');
        return;
      }

      const { lat, lon } = res[0];
      const newPoint = { lat: parseFloat(lat), lon: parseFloat(lon) };

      if (phase === 'SELECT_START') {
        setStartPoint(newPoint);
        setPhase('SELECT_END');
        addNotification(`📍 Start: ${res[0].display_name.split(',')[0]}`, 'success');
        setViewState(prev => ({ ...prev, latitude: parseFloat(lat), longitude: parseFloat(lon), zoom: 14 }));
      } else if (phase === 'SELECT_END' && startPoint) {
        // Set end point and immediately trigger route computation
        setEndPoint(newPoint);
        setViewState(prev => ({ ...prev, latitude: parseFloat(lat), longitude: parseFloat(lon) }));
        addNotification(`🎯 End: ${res[0].display_name.split(',')[0]}`, 'success');

        // Compute routes with slight delay to ensure state updates
        setTimeout(async () => {
          addNotification('🔄 Computing routes...', 'info');
          try {
            const tickMins = 0.2; // Match handleStartSimulation timing
            const routeRes = await fetch(`${API_URL}/simulate/start`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                src_lat: startPoint.lat,
                src_lon: startPoint.lon,
                dst_lat: newPoint.lat,
                dst_lon: newPoint.lon,
                speed_mode: 'car',
                intensity: 'heavy',
                month: null,
                evolution_mode: 'random',
                tick_mins: tickMins,
              }),
            }).then(r => r.json());

            if (routeRes.status === 'error' || routeRes.status === 'severe_flood') {
              if (routeRes.status === 'severe_flood') {
                // Handle shelter evacuation
                setShelterEvacuation(routeRes.shelter);
                setSessionId(routeRes.session_id);
                addNotification('🌊 ' + routeRes.message, 'error');
                addNotification('📍 ' + routeRes.alert, 'warning');
                setPhase('SHELTER_EVACUATION');
                return;
              }
              // If route fails, allow user to adjust location by dragging the marker
              addNotification('⚠️ Try dragging marker closer to roads', 'warning');
              setEndPoint(newPoint);
              setPhase('SELECT_END');
              return;
            }

            setRouteData(routeRes);
            const alts = routeRes.alternative_routes || [];
            setAlternativeRoutes(alts);
            setSessionId(routeRes.session_id);
            addNotification(`✅ Found ${alts.length + 1} routes (${routeRes.summary.total_distance_m}m)`, 'success');
            setPhase('CONFIG');
          } catch (err) {
            addNotification('⚠️ Route computation failed', 'error');
          }
        }, 100);
      }
    } catch (err) {
      addNotification('⚠️ Search failed', 'error');
    }
  };

  const handleMarkerDragStart = (marker) => {
    setDraggedMarker(marker);
    clickCountRef.current.startTime = Date.now() + 1000; // Block double-tap during drag
  };

  const handleMarkerDrag = (e, marker) => {
    if (e.type !== 'move') return;
    const { lat, lng: lon } = e.lngLat;
    if (marker === 'start') {
      setStartPoint({ lat, lon });
    } else {
      setEndPoint({ lat, lon });
    }
  };

  const handleMarkerDragEnd = (marker) => {
    setDraggedMarker(null);
    // Recalculate routes if dragging end point
    if (marker === 'end' && startPoint && endPoint) {
      setTimeout(() => {
        addNotification('🔄 Recomputing routes...', 'info');
        fetchRoutes(startPoint, endPoint);
      }, 100);
    }
  };

  const handleMarkerDoubleClick = (marker) => {
    if (draggedMarker) return;
    if (marker === 'start') {
      setStartPoint(null);
      setPhase('SELECT_START');
      addNotification('❌ Start point cleared', 'info');
    } else {
      setEndPoint(null);
      setPhase('SELECT_END');
      addNotification('❌ Destination cleared', 'info');
    }
  };

  const handleEvacuateToShelter = async (shelter) => {
    if (!startPoint || !shelter) return;
    setPhase('RUNNING');
    setError(null);
    setNotifications([]);
    setMaxFloodIntensity(0);
    setShelterEvacuation(null);
    addNotification(`📍 Routing to shelter: ${shelter.name}`, 'success');
    addNotification('⏱️ Emergency evacuation starting...', 'warning');

    try {
      const res = await fetch(`${API_URL}/simulate/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          src_lat: startPoint.lat,
          src_lon: startPoint.lon,
          dst_lat: shelter.lat,
          dst_lon: shelter.lon,
          speed_mode: 'car',
          intensity,
          month: month === 'random' ? null : month,
          evolution_mode: evolutionMode,
          tick_mins: 5.0,
        }),
      }).then(r => r.json());

      if (res.status === 'error') {
        setError(res.message);
        addNotification('❌ ' + res.message, 'error');
        setPhase('SHELTER_EVACUATION');
        return;
      }

      setSessionId(res.session_id);
      setRouteData(res);
      const alts = res.alternative_routes || [];
      setAlternativeRoutes(alts);
      setPersonPos(res.person_position);
      setHeatmap(toHeatmapFeatures(res.rainfall_heatmap));
      setStats(res.summary);
      setTick(0);
      addNotification(`🚗 Emergency evacuation in progress`, 'success');
      startTickLoop(res.session_id);
    } catch (err) {
      setError(err.message);
      addNotification('❌ Error starting evacuation', 'error');
      setPhase('SHELTER_EVACUATION');
    }
  };

  const fetchRoutes = async (start, end) => {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/simulate/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          src_lat: start.lat,
          src_lon: start.lon,
          dst_lat: end.lat,
          dst_lon: end.lon,
          speed_mode: 'car',
          intensity: 'random',
          month: null,
          evolution_mode: 'random',
          tick_mins: 0.2,
        }),
      }).then(r => r.json());

      if (res.status === 'severe_flood') {
        setShelterEvacuation(res.shelter);
        setSessionId(res.session_id);
        addNotification('🌊 ' + res.message, 'error');
        addNotification('📍 ' + res.alert, 'warning');
        setPhase('SHELTER_EVACUATION');
        return;
      }

      if (res.status === 'error') {
        setError(res.message);
        addNotification('❌ ' + res.message, 'error');
        setPhase('SELECT_END');
        return;
      }

      setRouteData(res);
      const alts = res.alternative_routes || [];
      console.log('Alternative routes received:', alts.length, alts);
      setAlternativeRoutes(alts);
      setSessionId(res.session_id);
      if (res.rainfall_heatmap) setHeatmap(toHeatmapFeatures(res.rainfall_heatmap));
      if (res.flood_overlay) setFloodOverlay(res.flood_overlay);
      if (res.summary) setStats(res.summary);
      addNotification(`✅ Found ${alts.length + 1} routes (${res.summary.total_distance_m}m)`, 'success');
      setPhase('CONFIG');
    } catch (err) {
      setError(err.message);
      addNotification('⚠️ Network error', 'error');
      setPhase('SELECT_END');
    }
  };

  const handleStartSimulation = async () => {
    if (!startPoint || !endPoint) return;
    setPhase('RUNNING');
    setError(null);
    setNotifications([]);
    setMaxFloodIntensity(0);
    addNotification('⏱️ Simulation starting...', 'info');

    try {
      // Calculate tick duration: show 7-8 second sim for realistic times
      // If ETA is 10 min, show 70-80 ticks in 7-8 secs = ~90ms per tick
      // So for backend: use tick_mins that matches this speed
      // For 5km at 30km/h = 10 min ETA, we want: 10min / 70ticks = 8.5 sec per tick (backend)
      const tickDurationMs = 250; // 250ms per frontend tick — slower, more realistic pace
      const tickMins = 0.2; // Backend: each 250ms represents 0.2 minutes (12 seconds real time)

      const res = await fetch(`${API_URL}/simulate/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          src_lat: startPoint.lat,
          src_lon: startPoint.lon,
          dst_lat: endPoint.lat,
          dst_lon: endPoint.lon,
          speed_mode: speedMode,
          intensity,
          month: month === 'random' ? null : month,
          evolution_mode: evolutionMode,
          tick_mins: tickMins,
        }),
      }).then(r => r.json());

      if (res.status === 'error') {
        setError(res.message);
        addNotification('❌ ' + res.message, 'error');
        setPhase('CONFIG');
        return;
      }

      setSessionId(res.session_id);
      setRouteData(res);
      const alts = res.alternative_routes || [];
      console.log('Alternative routes in simulation:', alts.length, alts);
      setAlternativeRoutes(alts);
      setPersonPos(res.person_position);
      setHeatmap(toHeatmapFeatures(res.rainfall_heatmap));
      if (res.flood_overlay) setFloodOverlay(res.flood_overlay);
      setStats(res.summary);
      setTick(0);
      addNotification(`🚗 Starting evacuation navigation`, 'success');
      startTickLoop(res.session_id, tickDurationMs);
    } catch (err) {
      setError(err.message);
      addNotification('❌ Error starting simulation', 'error');
      setPhase('CONFIG');
    }
  };

  const startTickLoop = (sid, tickDurationMs = 110) => {
    if (tickTimerRef.current) clearInterval(tickTimerRef.current);

    tickTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/simulate/tick`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid }),
        }).then(r => r.json());

        if (res.status === 'error') {
          setPhase('COMPLETE');
          clearInterval(tickTimerRef.current);
          return;
        }

        setTick(res.tick);
        setPersonPos(res.person_position);
        setRouteData(prev => prev ? { ...prev, route_geojson: res.route_geojson } : prev);

        if (res.route_history_geojson) {
          setRouteHistory(res.route_history_geojson.map(g => ({ geojson: g })));
        }

        if (res.original_route_max_depth !== undefined && res.original_route_max_depth !== null) {
          setOriginalRouteMaxDepth(res.original_route_max_depth);
        }

        // We removed the heatmap UI, so we just calculate max flood intensity but don't draw it
        const newHeatmap = res.rainfall_heatmap || [];
        setHeatmap(newHeatmap);

        // Track max flood intensity
        const maxIntensity = Math.max(...(newHeatmap.map(h => h.properties.intensity) || [0]));
        setMaxFloodIntensity(maxIntensity);

        setStats(res.summary);

        // Show realistic notifications
        if (res.rerouted && res.reroute_reason) {
          addNotification(`⚠️ Route recalculating: ${res.reroute_reason}`, 'warning');
        }

        if (res.summary.max_flood_depth_m > 0.8) {
          addNotification('🌊 FLOOD INTENSIFIED - Finding safer route', 'error');
        } else if (res.summary.max_flood_depth_m > 0.4) {
          addNotification('💧 Moderate flooding ahead', 'warning');
        }

        if (res.arrived) {
          setPhase('COMPLETE');
          clearInterval(tickTimerRef.current);
          addNotification('✅ Arrived at destination!', 'success');
        }
      } catch (err) {
        console.error(err);
      }
    }, tickDurationMs);
  };

  const handleReset = async () => {
    if (tickTimerRef.current) clearInterval(tickTimerRef.current);
    if (sessionId) {
      try {
        await fetch(`${API_URL}/simulate/reset`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
        });
      } catch { }
    }
    setSessionId(null);
    setPhase('SELECT_START');
    setStartPoint(null);
    setEndPoint(null);
    setRouteData(null);
    setAlternativeRoutes([]);
    setFloodOverlay(null);
    setPersonPos(null);
    setHeatmap([]);
    setRouteHistory([]);
    setTick(0);
    setStats(null);
    setError(null);
    setNotifications([]);
    setMaxFloodIntensity(0);
    setOriginalRouteMaxDepth(null);
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#f9fafb' }}>
      {/* Header */}
      <div style={{
        background: '#4f46e5',
        color: 'white',
        padding: '1rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Navigation size={24} />
          <h1 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 'bold' }}>Evacuation Navigator</h1>
        </div>
        <button onClick={onLogout} style={{
          background: '#ef4444',
          color: 'white',
          border: 'none',
          padding: '0.5rem 1rem',
          borderRadius: '0.5rem',
          cursor: 'pointer',
          fontWeight: 'bold',
          fontSize: '0.875rem',
        }}>
          Logout
        </button>
      </div>

      {/* Main layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', gap: '0' }}>
        {/* Left: Full map */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          <Map
            {...viewState}
            onMove={e => setViewState(e.viewState)}
            onClick={handleMapClick}
            style={{ width: '100%', height: '100%' }}
            mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
            ref={mapRef}
          >
            <NavigationControl position="top-right" />



            {/* ── Flood corridor overlay — shows all flooded roads in the area ── */}
            {floodOverlay != null && floodOverlay.features && floodOverlay.features.length > 0 && (
              <Source id="flood-corridor" type="geojson" data={floodOverlay}>
                <Layer
                  id="flood-corridor-line"
                  type="line"
                  paint={{
                    'line-color': [
                      'match',
                      ['get', 'flood_risk'],
                      'high', '#dc2626',
                      'medium', '#f59e0b',
                      'low', '#60a5fa',
                      '#93c5fd'
                    ],
                    'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2, 16, 5],
                    'line-opacity': 0.45,
                  }}
                />
              </Source>
            )}

            {/* ── Route history — faded grey past routes (reroute trail) ── */}
            {routeHistory.map((r, i) => (
              <Source key={`history-${i}`} id={`history-${i}`} type="geojson" data={r.geojson}>
                <Layer
                  id={`history-line-${i}`}
                  type="line"
                  paint={{
                    'line-color': '#9ca3af',
                    'line-width': 2,
                    'line-opacity': 0.2,
                    'line-dasharray': [4, 3],
                  }}
                />
              </Source>
            ))}

            {/* ── Alternative routes — grey ghost lines, CONFIG phase only ── */}
            {phase === 'CONFIG' && alternativeRoutes != null && alternativeRoutes.map((alt, idx) => (
              <Source key={`alt-route-${idx}`} id={`alt-route-${idx}`} type="geojson" data={alt.geojson}>
                <Layer
                  id={`alt-route-line-${idx}`}
                  type="line"
                  paint={{
                    'line-color': '#9ca3af',
                    'line-width': 3,
                    'line-opacity': 0.5,
                    'line-dasharray': [6, 4],
                  }}
                />
              </Source>
            ))}

            {/* ── Primary route — Google Maps blue with flood-risk segments ── */}
            {routeData != null && routeData.route_geojson != null && (
              <Source id="route" type="geojson" data={routeData.route_geojson}>
                {/* Glow / shadow */}
                <Layer
                  id="route-glow"
                  type="line"
                  paint={{
                    'line-color': '#4285F4',
                    'line-width': 10,
                    'line-opacity': 0.15,
                    'line-blur': 4,
                  }}
                />
                {/* Main line — blue for safe, coloured for flooded segments */}
                <Layer
                  id="route-line"
                  type="line"
                  paint={{
                    'line-color': [
                      'match',
                      ['get', 'flood_risk'],
                      'high', '#dc2626',
                      'medium', '#f59e0b',
                      '#4285F4'
                    ],
                    'line-width': 5,
                    'line-opacity': 0.95,
                  }}
                />
              </Source>
            )}

            {/* Start point marker - draggable */}
            {startPoint != null && (
              <Marker
                longitude={startPoint.lon}
                latitude={startPoint.lat}
                anchor="bottom"
                draggable
                onDragStart={() => handleMarkerDragStart('start')}
                onDrag={(e) => handleMarkerDrag(e, 'start')}
                onDragEnd={() => handleMarkerDragEnd('start')}
              >
                <button
                  title="Drag to move, double-click to remove"
                  style={{
                    width: '40px',
                    height: '40px',
                    background: '#3b82f6',
                    borderRadius: '50%',
                    border: draggedMarker === 'start' ? '4px solid #fbbf24' : '3px solid white',
                    boxShadow: draggedMarker === 'start'
                      ? '0 0 0 8px rgba(251, 191, 36, 0.3)'
                      : '0 4px 12px rgba(59, 130, 246, 0.5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '20px',
                    fontWeight: 'bold',
                    cursor: draggedMarker === 'start' ? 'grabbing' : 'grab',
                    transition: 'all 0.2s',
                    color: 'white',
                    padding: 0,
                  }}
                  onDoubleClick={() => handleMarkerDoubleClick('start')}
                >
                  A
                </button>
              </Marker>
            )}

            {/* End point marker - draggable */}
            {endPoint != null && (
              <Marker
                longitude={endPoint.lon}
                latitude={endPoint.lat}
                anchor="bottom"
                draggable
                onDragStart={() => handleMarkerDragStart('end')}
                onDrag={(e) => handleMarkerDrag(e, 'end')}
                onDragEnd={() => handleMarkerDragEnd('end')}
              >
                <button
                  title="Drag to move, double-click to remove"
                  style={{
                    width: '40px',
                    height: '40px',
                    background: '#ef4444',
                    borderRadius: '50%',
                    border: draggedMarker === 'end' ? '4px solid #fbbf24' : '3px solid white',
                    boxShadow: draggedMarker === 'end'
                      ? '0 0 0 8px rgba(251, 191, 36, 0.3)'
                      : '0 4px 12px rgba(239, 68, 68, 0.5)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '20px',
                    fontWeight: 'bold',
                    cursor: draggedMarker === 'end' ? 'grabbing' : 'grab',
                    transition: 'all 0.2s',
                    color: 'white',
                    padding: 0,
                  }}
                  onDoubleClick={() => handleMarkerDoubleClick('end')}
                >
                  B
                </button>
              </Marker>
            )}

            {/* Person during simulation */}
            {personPos != null && phase === 'RUNNING' && (
              <Marker longitude={personPos.lon} latitude={personPos.lat} anchor="bottom">
                <div style={{
                  width: '36px',
                  height: '36px',
                  background: 'white',
                  borderRadius: '50%',
                  border: '3px solid #3b82f6',
                  boxShadow: '0 0 0 4px rgba(59, 130, 246, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '18px',
                  animation: 'pulse 2s infinite',
                }}>
                  🚗
                </div>
              </Marker>
            )}
            {/* Map Legend */}
            <div style={{
              position: 'absolute',
              bottom: '24px',
              left: '24px',
              background: 'white',
              padding: '12px',
              borderRadius: '8px',
              boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
              zIndex: 10,
              fontSize: '12px',
              color: '#374151',
            }}>
              <div style={{ fontWeight: 'bold', marginBottom: '8px', fontSize: '13px' }}>Route Legend</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <div style={{ width: '20px', height: '4px', background: '#4285F4', borderRadius: '2px' }} />
                <span>Safe Passage</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <div style={{ width: '20px', height: '4px', background: '#f59e0b', borderRadius: '2px' }} />
                <span>Moderate Flood Risk</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <div style={{ width: '20px', height: '4px', background: '#dc2626', borderRadius: '2px' }} />
                <span>High Flood Risk</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ width: '20px', height: '0', borderTop: '3px dashed #9ca3af' }} />
                <span>Alternate Route</span>
              </div>
            </div>

          </Map>

          {/* Rain overlay effect */}
          {phase === 'RUNNING' && <RainOverlay intensity={maxFloodIntensity} />}
        </div>

        {/* Right: Phone-like panel */}
        <div style={{
          width: '420px',
          background: 'white',
          borderRadius: '20px 0 0 20px',
          border: '1px solid #e5e7eb',
          boxShadow: '-4px 0 16px rgba(0,0,0,0.1)',
          padding: '1.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
          overflowY: 'auto',
          position: 'relative',
        }}>
          {/* Notifications */}
          <div style={{ minHeight: 0 }}>
            {notifications.map(n => (
              <NotificationBanner
                key={n.id}
                message={n.msg}
                type={n.type}
                icon={
                  n.type === 'warning' ? AlertCircle :
                    n.type === 'error' ? AlertCircle :
                      n.type === 'success' ? MapPin :
                        Cloud
                }
              />
            ))}
          </div>

          <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: '700', color: '#1f2937' }}>Navigation</h2>

          {error && (
            <NotificationBanner message={error} type="error" icon={AlertCircle} />
          )}

          {/* Phase-specific UI */}
          {(phase === 'SELECT_START' || phase === 'SELECT_END') && (
            <div style={{ background: '#eff6ff', padding: '1rem', borderRadius: '0.75rem', border: '1px solid #93c5fd' }}>
              <p style={{ margin: '0 0 0.75rem 0', fontWeight: '600', color: '#0369a1', fontSize: '0.875rem' }}>
                {phase === 'SELECT_START' ? '📍 TAP MAP OR SEARCH START' : '🎯 TAP MAP OR SEARCH DESTINATION'}
              </p>

              {/* Search box */}
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <input
                  type="text"
                  placeholder={phase === 'SELECT_START' ? 'Search start location...' : 'Search destination...'}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearchLocation(searchQuery)}
                  style={{
                    flex: 1,
                    padding: '0.5rem',
                    borderRadius: '0.375rem',
                    border: '1px solid #93c5fd',
                    fontSize: '0.85rem',
                  }}
                />
                <button
                  onClick={() => handleSearchLocation(searchQuery)}
                  style={{
                    padding: '0.5rem 0.75rem',
                    background: '#0369a1',
                    color: 'white',
                    border: 'none',
                    borderRadius: '0.375rem',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                    fontWeight: '600',
                  }}
                >
                  🔍
                </button>
              </div>

              {/* Location info */}
              {startPoint && (
                <div style={{
                  fontSize: '0.8rem',
                  color: '#666',
                  marginBottom: '0.5rem',
                  padding: '0.5rem',
                  background: 'white',
                  borderRadius: '0.375rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontFamily: 'monospace',
                }}>
                  <span><strong>A:</strong> {startPoint.lat.toFixed(4)}, {startPoint.lon.toFixed(4)}</span>
                  <span style={{ fontSize: '0.7rem', color: '#999' }}>Double-click marker to remove</span>
                </div>
              )}
              {endPoint && (
                <div style={{
                  fontSize: '0.8rem',
                  color: '#666',
                  padding: '0.5rem',
                  background: 'white',
                  borderRadius: '0.375rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontFamily: 'monospace',
                }}>
                  <span><strong>B:</strong> {endPoint.lat.toFixed(4)}, {endPoint.lon.toFixed(4)}</span>
                  <span style={{ fontSize: '0.7rem', color: '#999' }}>Double-click marker to remove</span>
                </div>
              )}
            </div>
          )}

          {phase === 'CONFIG' && (
            <>
              {/* Route recommendation if safer alternative exists */}
              {routeData?.route_recommendation && (
                <div style={{
                  background: '#fef3c7',
                  border: '2px solid #f59e0b',
                  color: '#92400e',
                  padding: '0.75rem',
                  borderRadius: '0.75rem',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  marginBottom: '1rem',
                }}>
                  {routeData.route_recommendation}
                </div>
              )}

              {routeData && (
                <div style={{
                  background: '#f0fdf4',
                  padding: '1rem',
                  borderRadius: '0.75rem',
                  border: '1px solid #86efac',
                  fontSize: '0.875rem'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>🛣️ Distance:</span>
                    <strong>{(routeData.summary.total_distance_m / 1000).toFixed(1)} km</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>⏱️ Time ({SPEED_CONFIG[speedMode].label.split(' ')[0]}):</span>
                    <strong>
                      {Math.round((routeData.summary.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60)} min
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>💧 Max Flood:</span>
                    <strong style={{ color: routeData.summary.max_flood_depth_m > 0.5 ? '#dc2626' : '#16a34a' }}>
                      {routeData.summary.max_flood_depth_m.toFixed(2)} m
                    </strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>🛡️ Safety:</span>
                    <strong style={{ color: routeData.summary.safe ? '#16a34a' : '#dc2626' }}>
                      {routeData.summary.safe ? 'SAFE ✅' : 'RISKY ⚠️'}
                    </strong>
                  </div>
                  {routeData.summary.flooded_segments > 0 && (
                    <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid #e5e7eb' }}>
                      ⚠️ Passes through {routeData.summary.flooded_segments} flooded segment(s)
                    </div>
                  )}
                </div>
              )}

              {/* Route legend — Google Maps style */}
              {alternativeRoutes != null && alternativeRoutes.length > 0 && (
                <div style={{
                  background: '#f8fafc',
                  padding: '0.75rem',
                  borderRadius: '0.75rem',
                  border: '1px solid #e2e8f0',
                  fontSize: '0.8rem',
                }}>
                  <div style={{ fontWeight: '700', marginBottom: '0.5rem', color: '#374151' }}>
                    🗺️ {1 + alternativeRoutes.length} Routes Found
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                    <div style={{ width: '24px', height: '4px', background: '#4285F4', borderRadius: '2px' }} />
                    <span><strong>Best route</strong> — {(routeData.summary.total_distance_m / 1000).toFixed(1)} km, ~{Math.round((routeData.summary.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60)} min</span>
                  </div>
                  {alternativeRoutes.map((alt, idx) => {
                    const primaryEta = Math.round((routeData.summary.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60);
                    const altEta = Math.round((alt.summary.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60);
                    const diff = altEta - primaryEta;
                    return (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                        <div style={{ width: '24px', height: '3px', background: '#9ca3af', borderRadius: '2px' }} />
                        <span style={{ color: '#6b7280' }}>
                          Alt {idx + 1} — {(alt.summary.total_distance_m / 1000).toFixed(1)} km
                          {diff > 0 ? ` (+${diff} min)` : diff < 0 ? ` (${diff} min)` : ''}
                          {!alt.summary.safe && ' ⚠️'}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', fontSize: '0.875rem', color: '#374151' }}>Transport Mode</label>
                <select
                  value={speedMode}
                  onChange={(e) => setSpeedMode(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    border: '1px solid #d1d5db',
                    fontSize: '0.875rem',
                    background: 'white',
                    cursor: 'pointer',
                  }}
                >
                  <option value="car">🚗 Car (30 km/h)</option>
                  <option value="bike">🚴 Bike (15 km/h)</option>
                  <option value="walk">🚶 Walking (4 km/h)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', fontSize: '0.875rem', color: '#374151' }}>Rainfall Intensity</label>
                <select
                  value={intensity}
                  onChange={(e) => setIntensity(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    border: '1px solid #d1d5db',
                    fontSize: '0.875rem',
                    background: 'white',
                    cursor: 'pointer',
                  }}
                >
                  <option value="random">🎲 Random</option>
                  <option value="light">🌧️ Light (50mm)</option>
                  <option value="moderate">⛈️ Moderate (100mm)</option>
                  <option value="heavy">🌊 Heavy (150mm)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '600', fontSize: '0.875rem', color: '#374151' }}>Evolution Mode</label>
                <select
                  value={evolutionMode}
                  onChange={(e) => setEvolutionMode(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    border: '1px solid #d1d5db',
                    fontSize: '0.875rem',
                    background: 'white',
                    cursor: 'pointer',
                  }}
                >
                  <option value="random">🎲 Random</option>
                  <option value="intensify">⬆️ Intensify</option>
                  <option value="dissipate">⬇️ Dissipate</option>
                  <option value="move">➡️ Move</option>
                </select>
              </div>

              <button
                onClick={handleStartSimulation}
                style={{
                  width: '100%',
                  background: '#4f46e5',
                  color: 'white',
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  boxShadow: '0 4px 12px rgba(79, 70, 229, 0.3)',
                  transition: 'all 0.2s',
                }}
                onMouseOver={(e) => e.target.style.background = '#4338ca'}
                onMouseOut={(e) => e.target.style.background = '#4f46e5'}
              >
                ▶️ START SIMULATION
              </button>
            </>
          )}

          {phase === 'SHELTER_EVACUATION' && shelterEvacuation && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{
                background: '#fee2e2',
                border: '2px solid #dc2626',
                color: '#991b1b',
                padding: '1.25rem',
                borderRadius: '0.75rem',
                textAlign: 'center',
                fontWeight: '600',
                fontSize: '0.95rem',
              }}>
                🌊 SEVERE FLOOD ALERT
              </div>

              <div style={{ background: '#fef2f2', padding: '1rem', borderRadius: '0.75rem', border: '1px solid #fecaca', fontSize: '0.875rem', lineHeight: '1.6', color: '#7f1d1d' }}>
                Direct route to your destination is <strong>blocked by severe flooding</strong>. Emergency shelter identified nearby for your safety.
              </div>

              {shelterEvacuation && (
                <div style={{
                  background: '#f0fdf4',
                  padding: '1.25rem',
                  borderRadius: '0.75rem',
                  border: '2px solid #86efac',
                }}>
                  <div style={{ fontWeight: '700', marginBottom: '0.75rem', color: '#166534', fontSize: '0.95rem' }}>
                    📍 Nearest Safe Shelter
                  </div>
                  <div style={{ fontSize: '0.875rem', lineHeight: '1.8', color: '#374151' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                      <span>🏛️ Name:</span>
                      <strong>{shelterEvacuation.name}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                      <span>📦 Type:</span>
                      <strong>{shelterEvacuation.type}</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                      <span>👥 Capacity:</span>
                      <strong>{shelterEvacuation.capacity} persons</strong>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>📏 Distance:</span>
                      <strong>{(shelterEvacuation.distance_m / 1000).toFixed(1)} km</strong>
                    </div>
                  </div>
                </div>
              )}

              <button
                onClick={() => handleEvacuateToShelter(shelterEvacuation)}
                style={{
                  width: '100%',
                  background: '#dc2626',
                  color: 'white',
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  boxShadow: '0 4px 12px rgba(220, 38, 38, 0.3)',
                }}
                onMouseOver={(e) => e.target.style.background = '#b91c1c'}
                onMouseOut={(e) => e.target.style.background = '#dc2626'}
              >
                🚨 EVACUATE TO SHELTER
              </button>

              <button
                onClick={() => setPhase('SELECT_START')}
                style={{
                  width: '100%',
                  background: '#6b7280',
                  color: 'white',
                  padding: '0.75rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: '600',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                ↻ Choose Different Location
              </button>
            </div>
          )}

          {phase === 'RUNNING' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* Location info - Google Maps style */}
              <div style={{ fontSize: '0.75rem', color: '#6b7280', padding: '0.75rem', background: '#f9fafb', borderRadius: '0.5rem' }}>
                <div style={{ marginBottom: '0.4rem' }}>📍 <strong>From:</strong> {startPoint ? `${startPoint.lat.toFixed(4)}, ${startPoint.lon.toFixed(4)}` : 'Unknown'}</div>
                <div>🎯 <strong>To:</strong> {endPoint ? `${endPoint.lat.toFixed(4)}, ${endPoint.lon.toFixed(4)}` : 'Unknown'}</div>
              </div>

              {/* Elapsed time matching vehicle movement */}
              <div style={{
                background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
                color: 'white',
                padding: '1.25rem',
                borderRadius: '0.75rem',
                textAlign: 'center',
                boxShadow: '0 4px 12px rgba(79, 70, 229, 0.3)',
              }}>
                <div style={{ fontSize: '3rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>
                  {Math.round(tick * 0.2)}'
                </div>
                <div style={{ fontSize: '0.75rem', opacity: 0.9 }}>
                  Elapsed Time (of {stats ? Math.round((stats.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60) : 0} min)
                </div>
              </div>

              {stats != null && (
                <div style={{ background: '#f3f4f6', padding: '1rem', borderRadius: '0.75rem', fontSize: '0.85rem', lineHeight: '1.8' }}>
                  {/* Progress bar with actual elapsed time - using current speed mode ETA */}
                  {(() => {
                    const actualEta = Math.round((stats.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60);
                    const progress = Math.round(Math.min(100, (tick * 0.2 / actualEta) * 100));
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span style={{ fontWeight: '600' }}>📍 Progress</span>
                          <span style={{ fontWeight: 'bold', color: '#4f46e5' }}>{progress}%</span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: '#e5e7eb', borderRadius: '3px', overflow: 'hidden', marginBottom: '1rem' }}>
                          <div style={{ height: '100%', background: 'linear-gradient(90deg, #4f46e5, #7c3aed)', width: `${progress}%`, transition: 'width 0.1s linear' }} />
                        </div>
                      </>
                    );
                  })()}

                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>🛣️ Distance:</span>
                    <span><strong>{(stats.total_distance_m / 1000).toFixed(1)} km</strong></span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>⏱️ ETA:</span>
                    <span><strong>{Math.round((stats.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60)} min</strong></span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>⏱️ Time left:</span>
                    <span style={{ fontWeight: '600' }}>{Math.max(0, Math.round((stats.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60 - tick * 0.2))} min</span>
                  </div>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    color: stats.max_flood_depth_m > 1.5 ? '#dc2626' : stats.max_flood_depth_m > 0.5 ? '#ea580c' : '#16a34a',
                    fontWeight: 'bold',
                    paddingTop: '0.75rem',
                    borderTop: '1px solid #e5e7eb',
                    marginBottom: '0.5rem'
                  }}>
                    <span>💧 Flood Depth:</span>
                    <span>{stats.max_flood_depth_m.toFixed(2)}m {stats.max_flood_depth_m > 1.5 ? '🚫' : stats.max_flood_depth_m > 0.5 ? '⚠️' : '✅'}</span>
                  </div>

                  {originalRouteMaxDepth != null && (
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      color: '#6b7280',
                      fontWeight: 'bold',
                      fontSize: '0.8rem',
                      marginBottom: '0.5rem'
                    }}>
                      <span>🚫 Abandoned Route Flood:</span>
                      <span>{originalRouteMaxDepth.toFixed(2)}m</span>
                    </div>
                  )}

                  {/* Flood impact note */}
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', paddingTop: '0.5rem', borderTop: '1px solid #e5e7eb', marginTop: '0.5rem' }}>
                    {stats.max_flood_depth_m > 1.5 && '⚠️ IMPASSABLE - Depth > 1.5m'}
                    {stats.max_flood_depth_m > 0.8 && stats.max_flood_depth_m <= 1.5 && '⚠️ High flood - Walking/Biking risky'}
                    {stats.max_flood_depth_m > 0.4 && stats.max_flood_depth_m <= 0.8 && '⚡ Moderate flood - All modes passable'}
                    {stats.max_flood_depth_m > 0.1 && stats.max_flood_depth_m <= 0.4 && '💧 Light flooding - Normal travel'}
                    {stats.max_flood_depth_m <= 0.1 && '✅ No flooding - Safe passage'}
                  </div>
                </div>
              )}

              <button
                onClick={handleReset}
                style={{
                  width: '100%',
                  background: '#ef4444',
                  color: 'white',
                  padding: '0.75rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                }}
              >
                ⏹️ Stop Simulation
              </button>
            </div>
          )}

          {phase === 'COMPLETE' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{
                background: '#dcfce7',
                border: '2px solid #86efac',
                color: '#166534',
                padding: '1.25rem',
                borderRadius: '0.75rem',
                textAlign: 'center',
                fontWeight: '600',
                fontSize: '1rem',
              }}>
                ✅ ARRIVED SAFELY!
              </div>

              {/* Location summary */}
              <div style={{ fontSize: '0.8rem', color: '#374151', padding: '0.75rem', background: '#f9fafb', borderRadius: '0.5rem', borderLeft: '4px solid #4f46e5' }}>
                <div style={{ marginBottom: '0.3rem' }}><strong>📍 From:</strong> {startPoint ? `${startPoint.lat.toFixed(4)}, ${startPoint.lon.toFixed(4)}` : 'Unknown'}</div>
                <div><strong>🎯 To:</strong> {endPoint ? `${endPoint.lat.toFixed(4)}, ${endPoint.lon.toFixed(4)}` : 'Unknown'}</div>
              </div>

              {stats != null && (
                <div style={{ background: '#f3f4f6', padding: '1.25rem', borderRadius: '0.75rem', fontSize: '0.875rem', lineHeight: '1.8' }}>
                  <div style={{ fontWeight: '700', marginBottom: '0.75rem', fontSize: '0.95rem' }}>🗺️ Trip Summary</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>🛣️ Distance:</span>
                    <span style={{ fontWeight: '600', color: '#4f46e5' }}>{(stats.total_distance_m / 1000).toFixed(1)} km</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>⏱️ Time Taken:</span>
                    <span style={{ fontWeight: '600', color: '#4f46e5' }}>{stats.eta_minutes} min</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <span>🚗 Speed Mode:</span>
                    <span style={{ fontWeight: '600' }}>{speedMode === 'car' ? '🚗 Car (30 km/h)' : speedMode === 'bike' ? '🚴 Bike (15 km/h)' : '🚶 Walking (4 km/h)'}</span>
                  </div>
                  <hr style={{ margin: '0.5rem 0', border: 'none', borderTop: '1px solid #e5e7eb' }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>💧 Max Flood Depth:</span>
                    <span style={{ fontWeight: '600', color: stats.max_flood_depth_m > 0.5 ? '#dc2626' : '#16a34a' }}>{stats.max_flood_depth_m.toFixed(2)} m</span>
                  </div>
                  {originalRouteMaxDepth != null && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                      <span>🚫 Abandoned Route Flood:</span>
                      <span style={{ fontWeight: '600', color: '#6b7280' }}>{originalRouteMaxDepth.toFixed(2)} m</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>🛡️ Route Safety:</span>
                    <span style={{ fontWeight: '600', color: stats.safe ? '#16a34a' : '#dc2626' }}>{stats.safe ? '✅ SAFE' : '⚠️ FLOODED'}</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '0.75rem', padding: '0.5rem', background: '#fff', borderRadius: '0.375rem' }}>
                    {stats.flooded_segments > 0 && `⚠️ Passed through ${stats.flooded_segments} flooded segment(s)`}
                    {stats.flooded_segments === 0 && '✅ No flooded roads on your route'}
                  </div>
                </div>
              )}

              <button
                onClick={handleReset}
                style={{
                  width: '100%',
                  background: '#4f46e5',
                  color: 'white',
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                }}
              >
                ↻ New Simulation
              </button>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3); }
          50% { opacity: 0.8; box-shadow: 0 0 0 8px rgba(59, 130, 246, 0.1); }
        }
        @keyframes slideInDown {
          from {
            transform: translateY(-20px);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
        @keyframes rainPulse {
          0%, 100% { opacity: 0; }
          50% { opacity: 0.4; }
        }
        ::-webkit-scrollbar {
          width: 6px;
        }
        ::-webkit-scrollbar-track {
          background: #f3f4f6;
        }
        ::-webkit-scrollbar-thumb {
          background: #d1d5db;
          border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
          background: #9ca3af;
        }
      `}</style>
    </div>
  );
}
