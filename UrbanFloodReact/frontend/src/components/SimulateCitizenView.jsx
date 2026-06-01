import React, { useState, useRef, useEffect } from 'react';
import Map, { Source, Layer, NavigationControl, Marker } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { AlertCircle, RotateCcw, Navigation, Cloud, Droplets, MapPin, Clock, GraduationCap } from 'lucide-react';
import { API_URL } from '../config';
import { useTutorial } from '../context/TutorialContext';
import TutorialOverlay from './TutorialOverlay';
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
  const { startTutorial } = useTutorial();
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
  const [rainfallLog, setRainfallLog] = useState([]);
  const [isRerouting, setIsRerouting] = useState(false);
  const [rerouteCount, setRerouteCount] = useState(0);
  const [routeSteps, setRouteSteps] = useState([]); // Turn-by-turn directions
  const [currentStepIndex, setCurrentStepIndex] = useState(0); // Track which step we're on
  const [recordedTicks, setRecordedTicks] = useState([]); // Record each tick for replay
  const [isReplaying, setIsReplaying] = useState(false); // Track if we're in replay mode
  const [replayIndex, setReplayIndex] = useState(0); // Current tick index in replay

  // Config
  const [speedMode, setSpeedMode] = useState('car');
  const [intensity, setIntensity] = useState('heavy'); // Heavy rainfall to show realistic floods
  const [evolutionMode, setEvolutionMode] = useState('random');
  const [month, setMonth] = useState('random');
  const [searchQuery, setSearchQuery] = useState('');
  const [navMode, setNavMode] = useState('simulated'); // 'simulated' or 'realtime'
  const [rainfallSource, setRainfallSource] = useState('live'); // 'live' or 'simulated'
  const [watchId, setWatchId] = useState(null);
  const [gpsCoords, setGpsCoords] = useState(null);
  const [draggedMarker, setDraggedMarker] = useState(null);
  const [useTraffic, setUseTraffic] = useState(false); // Traffic toggle for SIMULATED mode (OFF by default for scenario testing)
  const [playbackSpeed, setPlaybackSpeed] = useState(250); // Playback speed in ms per tick (50-500ms range)
  const clickCountRef = useRef({ start: 0, end: 0, startTime: 0, endTime: 0 });
  const doubleClickTimeoutRef = useRef(null);

  // Speed reference (must match backend SPEED_MAP)
  const SPEED_CONFIG = {
    car: { label: '🚗 Car (40 km/h)', speed_kph: 40 },
    bike: { label: '🚴 Bike (30 km/h)', speed_kph: 30 },
    walk: { label: '🚶 Walking (4 km/h)', speed_kph: 4 },
  };

  const tickTimerRef = useRef(null);
  const playbackSpeedRef = useRef(250);  // Track current playback speed
  const mapRef = useRef(null);
  const notificationTimeoutRef = useRef(null);
  const markerStartRef = useRef({ lat: 0, lon: 0 });

  useEffect(() => () => {
    if (tickTimerRef.current) clearInterval(tickTimerRef.current);
    if (watchId) navigator.geolocation.clearWatch(watchId);
  }, [watchId]);

  // Clean up backend session on page unload/reload
  useEffect(() => {
    const handleBeforeUnload = async () => {
      if (sessionId) {
        try {
          await fetch(`${API_URL}/simulate/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
            keepalive: true, // Ensure request completes even during unload
          });
        } catch { }
      }
      if (tickTimerRef.current) clearTimeout(tickTimerRef.current);
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    window.addEventListener('pagehide', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      window.removeEventListener('pagehide', handleBeforeUnload);
    };
  }, [sessionId]);

  // Auto-detect location when switching to real-time mode
  useEffect(() => {
    if (navMode === 'realtime') {
      detectCurrentLocation();
    } else {
      stopGpsTracking();
    }
  }, [navMode]);

  const detectCurrentLocation = () => {
    if (!navigator.geolocation) {
      addNotification('❌ Geolocation not supported', 'error');
      return;
    }

    addNotification('📡 Detecting current location...', 'info');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords;
        setStartPoint({ lat, lon });
        setGpsCoords({ lat, lon });
        setViewState(prev => ({ ...prev, latitude: lat, longitude: lon, zoom: 15 }));
        setPhase('SELECT_END');
        addNotification('📍 Location detected!', 'success');
      },
      (err) => {
        addNotification('❌ Could not detect location', 'error');
        console.error(err);
      },
      { enableHighAccuracy: true }
    );
  };

  const startGpsTracking = () => {
    if (watchId) navigator.geolocation.clearWatch(watchId);

    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords;
        setGpsCoords({ lat, lon });
        // In real-time, the car marker follows the GPS
        setPersonPos({ lat, lon });
      },
      (err) => console.error(err),
      { enableHighAccuracy: true }
    );
    setWatchId(id);
  };

  const stopGpsTracking = () => {
    if (watchId) {
      navigator.geolocation.clearWatch(watchId);
      setWatchId(null);
    }
  };

  // Auto-compute routes when both points are set
  useEffect(() => {
    if (startPoint && endPoint && phase === 'SELECT_END') {
      addNotification('🔄 Computing routes...', 'info');
      fetchRoutes(startPoint, endPoint);
    }
  }, [startPoint, endPoint, phase]);

  const addNotification = (msg, type = 'info') => {
    const id = Date.now();
    setNotifications(prev => {
      const next = [...prev, { id, msg, type }];
      return next.length > 3 ? next.slice(-3) : next; // Limit to 3 active notifications
    });
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 4000);
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
                mode: navMode,
                rainfall_source: navMode === 'realtime' ? 'ksndmc' : 'simulated',
                use_traffic: useTraffic,
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
            setRouteSteps(routeRes.steps || []);
            setCurrentStepIndex(0);
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

  const handleMarkerMouseDown = (e, marker) => {
    e.preventDefault();
    e.stopPropagation();

    const startX = e.clientX || e.touches?.[0]?.clientX;
    const startY = e.clientY || e.touches?.[0]?.clientY;
    let hasMoved = false;

    setDraggedMarker(marker);

    const handleMouseMove = (moveEvent) => {
      const currentX = moveEvent.clientX || moveEvent.touches?.[0]?.clientX;
      const currentY = moveEvent.clientY || moveEvent.touches?.[0]?.clientY;

      // Calculate distance moved
      const dx = Math.abs(currentX - startX);
      const dy = Math.abs(currentY - startY);

      if (dx > 5 || dy > 5) {
        hasMoved = true;
        // Get map container rect
        if (mapRef.current) {
          const mapEl = mapRef.current.getContainer();
          const rect = mapEl.getBoundingClientRect();
          const relX = currentX - rect.left;
          const relY = currentY - rect.top;

          // Convert pixel coords to lat/lng
          try {
            const lngLat = mapRef.current.unproject([relX, relY]);
            if (marker === 'start') {
              setStartPoint({ lat: lngLat.lat, lon: lngLat.lng });
            } else {
              setEndPoint({ lat: lngLat.lat, lon: lngLat.lng });
            }
          } catch (err) {
            console.error('Map unproject error:', err);
          }
        }
      }
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('touchmove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('touchend', handleMouseUp);

      setDraggedMarker(null);

      // Recalculate routes if dragging end point and actually moved
      if (hasMoved && marker === 'end' && startPoint && endPoint) {
        setTimeout(() => {
          addNotification('🔄 Recomputing routes...', 'info');
          fetchRoutes(startPoint, endPoint);
        }, 100);
      }
    };

    document.addEventListener('mousemove', handleMouseMove, { passive: false });
    document.addEventListener('touchmove', handleMouseMove, { passive: false });
    document.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('touchend', handleMouseUp);
  };

  const handleMarkerClick = (e, marker) => {
    e.stopPropagation();

    // Detect double-click by tracking time between clicks
    const now = Date.now();
    const lastClick = clickCountRef.current[`${marker}_lastClick`] || 0;
    const timeSinceLastClick = now - lastClick;

    clickCountRef.current[`${marker}_lastClick`] = now;

    if (timeSinceLastClick < 300) {
      // Double-click detected
      console.log(`[DOUBLE-CLICK] Marker ${marker}`);

      if (marker === 'start') {
        setStartPoint(null);
        setPhase('SELECT_START');
        addNotification('❌ Start point cleared', 'info');
      } else if (marker === 'end') {
        setEndPoint(null);
        setPhase('SELECT_END');
        addNotification('❌ Destination cleared', 'info');
      }

      // Reset click tracking
      clickCountRef.current[`${marker}_lastClick`] = 0;
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
          mode: navMode,
          rainfall_source: navMode === 'realtime' ? 'ksndmc' : 'simulated',
          use_traffic: useTraffic,
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
          mode: navMode,
          rainfall_source: navMode === 'realtime' ? 'ksndmc' : 'simulated',
          use_traffic: useTraffic,
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
    setRainfallLog([]);
    setRerouteCount(0);
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
          mode: navMode,
          rainfall_source: navMode === 'realtime' ? 'ksndmc' : 'simulated',
          use_traffic: useTraffic,
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
      addNotification(`🚗 Starting ${navMode === 'realtime' ? 'real-time journey' : 'evacuation navigation'}`, 'success');
      if (navMode === 'realtime') startGpsTracking();
      startTickLoop(res.session_id, tickDurationMs);
    } catch (err) {
      setError(err.message);
      addNotification('❌ Error starting simulation', 'error');
      setPhase('CONFIG');
    }
  };

  const startTickLoop = (sid, tickDurationMs = 110) => {
    if (tickTimerRef.current) clearTimeout(tickTimerRef.current);

    const runTick = async () => {
      try {
        const body = { session_id: sid };
        if (navMode === 'realtime' && gpsCoords) {
          body.current_lat = gpsCoords.lat;
          body.current_lon = gpsCoords.lon;
        }
        const res = await fetch(`${API_URL}/simulate/tick`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }).then(r => r.json());

        if (res.status === 'error') {
          setPhase('COMPLETE');
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

        if (res.flood_overlay) {
          setFloodOverlay(res.flood_overlay);
        }

        if (res.rainfall_log) {
          const logEntry = res.rainfall_log;
          console.log(
            `[Tick ${logEntry.tick}] ${logEntry.message} | ` +
            `avg=${logEntry.avg_rainfall_mm_hr}mm/hr max=${logEntry.max_rainfall_mm_hr}mm/hr | ` +
            `flood_depth=${logEntry.max_flood_depth_m}m roads=${logEntry.flooded_roads} impassable=${logEntry.impassable_roads}`
          );
          setRainfallLog(prev => {
            const next = [...prev, logEntry];
            return next.length > 50 ? next.slice(-50) : next;
          });
        }

        const newHeatmap = res.rainfall_heatmap || [];
        setHeatmap(newHeatmap);

        const maxIntensity = Math.max(...(newHeatmap.map(h => h.properties?.intensity ?? h.intensity ?? 0) || [0]));
        setMaxFloodIntensity(maxIntensity);

        setStats(res.summary);

        // Record tick for replay (including rerouting events)
        setRecordedTicks(prev => [...prev, {
          tick: res.tick,
          personPos: res.person_position,
          floodOverlay: res.flood_overlay,
          heatmap: newHeatmap,
          routeHistory: res.route_history_geojson,
          stats: res.summary,
          rerouted: res.rerouted,
          reroute_reason: res.reroute_reason,
          route_steps: res.steps,
          current_step_index: currentStepIndex,
        }]);

        if (routeSteps.length > 0 && res.summary) {
          const distRemaining = res.summary.total_distance_m;
          let completedDistance = 0;
          let newStepIndex = 0;
          for (let i = 0; i < routeSteps.length; i++) {
            if (completedDistance < res.summary.total_distance_m) {
              newStepIndex = i;
              break;
            }
            completedDistance += routeSteps[i].distance_m || 0;
          }
          setCurrentStepIndex(Math.min(newStepIndex, routeSteps.length - 1));
        }

        if (res.rerouted && res.reroute_reason) {
          console.log(`%c[REROUTE] ${res.reroute_reason}`, 'color: #dc2626; font-weight: bold; font-size: 14px;');
          setIsRerouting(true);
          setRerouteCount(prev => prev + 1);
          addNotification(`🔄 REROUTING: ${res.reroute_reason}`, 'warning');

          // Update route with new steps from backend
          if (res.steps && res.steps.length > 0) {
            setRouteSteps(res.steps);
            setCurrentStepIndex(0); // Reset to first step of new route
          }

          setTimeout(() => {
            setIsRerouting(false);
            addNotification('✅ New route calculated — resuming navigation', 'success');
            startTickLoop(sid, playbackSpeedRef.current);
          }, 1500);
          return;
        }

        if (res.rainfall_log) {
          const log = res.rainfall_log;
          if (log.flood_status === 'critical' && log.tick % 5 === 0) {
            addNotification(`🌊 ${log.impassable_roads} roads now impassable!`, 'error');
          } else if (log.flood_status === 'building' && log.tick % 8 === 0) {
            addNotification(`💧 Flooding increasing: ${log.flooded_roads} roads affected`, 'warning');
          }
        }

        if (res.arrived) {
          setPhase('COMPLETE');
          addNotification('✅ Arrived at destination!', 'success');
        } else {
          tickTimerRef.current = setTimeout(runTick, playbackSpeedRef.current);
        }
      } catch (err) {
        console.error(err);
        tickTimerRef.current = setTimeout(runTick, playbackSpeedRef.current);
      }
    };

    runTick();
  };

  const startReplay = () => {
    if (!recordedTicks || recordedTicks.length === 0) {
      addNotification('❌ No frames recorded to replay', 'error');
      return;
    }

    // CRITICAL: Stop any active simulation tick loop first
    if (tickTimerRef.current) {
      clearTimeout(tickTimerRef.current);
      tickTimerRef.current = null;
    }

    setIsReplaying(true);
    setReplayIndex(0);
    setPhase('RUNNING');
    setTick(0);
    setPersonPos(null);
    setRouteHistory([]);
    setFloodOverlay(null);
    setHeatmap([]);
    setStats(null);
    setCurrentStepIndex(0);
    addNotification(`🎬 Replaying ${recordedTicks.length} frames...`, 'info');

    let currentIdx = 0;

    const playNextFrame = () => {
      if (currentIdx >= recordedTicks.length) {
        // Replay finished - resume simulation from where it left off
        setIsReplaying(false);
        addNotification('✅ Replay finished - resuming simulation', 'success');
        // Resume the simulation tick loop
        if (sessionId) {
          startTickLoop(sessionId, playbackSpeedRef.current);
        }
        return;
      }

      const frame = recordedTicks[currentIdx];
      setTick(frame.tick);
      setPersonPos(frame.personPos);
      setFloodOverlay(frame.floodOverlay);
      setHeatmap(frame.heatmap || []);
      if (frame.routeHistory) {
        setRouteHistory(frame.routeHistory.map(g => ({ geojson: g })));
      }
      setStats(frame.stats);
      setReplayIndex(currentIdx + 1);

      // Restore rerouting state during replay
      if (frame.rerouted) {
        setIsRerouting(true);
        if (frame.route_steps) {
          setRouteSteps(frame.route_steps);
          setCurrentStepIndex(frame.current_step_index || 0);
        }
        // Show rerouting banner for 1.5s then hide
        setTimeout(() => {
          setIsRerouting(false);
        }, 1500);
      }

      currentIdx++;
      tickTimerRef.current = setTimeout(playNextFrame, playbackSpeedRef.current);
    };

    playNextFrame();
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
    stopGpsTracking();
    setNotifications([]);
    setPhase('SELECT_START');
    setStartPoint(null);
    setEndPoint(null);
    setRouteData(null);
    setAlternativeRoutes([]);
    setFloodOverlay(null);
    setPersonPos(null);
    setHeatmap([]);
    setRouteHistory([]);
    setRouteSteps([]);
    setCurrentStepIndex(0);
    setTick(0);
    setStats(null);
    setError(null);
    setNotifications([]);
    setMaxFloodIntensity(0);
    setOriginalRouteMaxDepth(null);
    setRainfallLog([]);
    setIsRerouting(false);
    setRerouteCount(0);
    setRecordedTicks([]);
    setIsReplaying(false);
    setReplayIndex(0);
  };

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#f9fafb' }}>
      {/* Header */}
      <div id="tutorial-sim-header" style={{
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
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            className="tutorial-trigger-btn tutorial-trigger-btn--header"
            onClick={() => startTutorial('simulate')}
            title={lang === 'en' ? 'Take a guided tutorial' : '\u0CAE\u0CBE\u0CB0\u0CCD\u0C97\u0CA6\u0CB0\u0CCD\u0CB6\u0CBF \u0C9F\u0CCD\u0CAF\u0CC1\u0C9F\u0CCB\u0CB0\u0CBF\u0CAF\u0CB2\u0CCD'}
          >
            <GraduationCap size={13} />
            {lang === 'en' ? 'Tutorial' : '\u0C9F\u0CCD\u0CAF\u0CC1\u0C9F\u0CCB\u0CB0\u0CBF\u0CAF\u0CB2\u0CCD'}
          </button>
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
      </div>

      {/* Main layout */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', gap: '0' }}>
        {/* Left: Full map */}
        <div id="tutorial-sim-map" style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
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
              >
                <div
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
                    color: 'white',
                    cursor: draggedMarker === 'start' ? 'grabbing' : 'grab',
                    transition: 'all 0.2s',
                    userSelect: 'none',
                  }}
                  onMouseDown={(e) => handleMarkerMouseDown(e, 'start')}
                  onClick={(e) => handleMarkerClick(e, 'start')}
                  title="Drag to move, double-click to remove"
                >
                  A
                </div>
              </Marker>
            )}

            {/* End point marker - draggable */}
            {endPoint != null && (
              <Marker
                longitude={endPoint.lon}
                latitude={endPoint.lat}
                anchor="bottom"
              >
                <div
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
                    color: 'white',
                    cursor: draggedMarker === 'end' ? 'grabbing' : 'grab',
                    transition: 'all 0.2s',
                    userSelect: 'none',
                  }}
                  onMouseDown={(e) => handleMarkerMouseDown(e, 'end')}
                  onClick={(e) => handleMarkerClick(e, 'end')}
                  title="Drag to move, double-click to remove"
                >
                  B
                </div>
              </Marker>
            )}

            {/* Person during simulation */}
            {personPos != null && (phase === 'RUNNING' || phase === 'PAUSED') && (
              <Marker longitude={personPos.lon} latitude={personPos.lat} anchor="bottom">
                <div style={{
                  width: '36px',
                  height: '36px',
                  background: navMode === 'realtime' ? '#3b82f6' : 'white',
                  borderRadius: '50%',
                  border: '3px solid white',
                  boxShadow: navMode === 'realtime' ? '0 0 15px rgba(59, 130, 246, 0.6)' : '0 0 0 4px rgba(59, 130, 246, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '18px',
                  animation: 'pulse 2s infinite',
                }}>
                  {navMode === 'realtime' ? (
                    <div style={{ width: '12px', height: '12px', background: 'white', borderRadius: '50%' }} />
                  ) : '🚗'}
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
          {(phase === 'RUNNING' || phase === 'PAUSED') && <RainOverlay intensity={maxFloodIntensity} />}
        </div>

        {/* Right: Phone-like panel */}
        <div id="tutorial-sim-config" style={{
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
          {/* Floating Notifications Container */}
          <div style={{
            position: 'absolute',
            top: '1rem',
            left: '1rem',
            right: '1rem',
            zIndex: 100,
            pointerEvents: 'none'
          }}>
            {notifications.map(n => (
              <div key={n.id} style={{ pointerEvents: 'auto' }}>
                <NotificationBanner
                  message={n.msg}
                  type={n.type}
                  icon={
                    n.type === 'warning' ? AlertCircle :
                      n.type === 'error' ? AlertCircle :
                        n.type === 'success' ? MapPin :
                          Cloud
                  }
                />
              </div>
            ))}
          </div>

          <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: '700', color: '#1f2937', paddingTop: notifications.length > 0 ? '0.5rem' : 0 }}>Navigation</h2>

          {/* Mode Toggle */}
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => setNavMode('simulated')}
              style={{
                flex: 1,
                padding: '0.6rem',
                borderRadius: '0.75rem',
                border: 'none',
                background: navMode === 'simulated' ? '#4f46e5' : '#f3f4f6',
                color: navMode === 'simulated' ? 'white' : '#374151',
                fontWeight: 'bold',
                fontSize: '0.8rem',
                cursor: 'pointer',
                transition: 'all 0.2s',
                boxShadow: navMode === 'simulated' ? '0 2px 8px rgba(79, 70, 229, 0.4)' : 'none'
              }}
            >
              🎮 Simulated
            </button>
            <button
              onClick={() => setNavMode('realtime')}
              style={{
                flex: 1,
                padding: '0.6rem',
                borderRadius: '0.75rem',
                border: 'none',
                background: navMode === 'realtime' ? '#4f46e5' : '#f3f4f6',
                color: navMode === 'realtime' ? 'white' : '#374151',
                fontWeight: 'bold',
                fontSize: '0.8rem',
                cursor: 'pointer',
                transition: 'all 0.2s',
                boxShadow: navMode === 'realtime' ? '0 2px 8px rgba(79, 70, 229, 0.4)' : 'none'
              }}
            >
              📍 Real-Time
            </button>
          </div>

          {/* Mode Explanation */}
          <div style={{
            background: navMode === 'realtime' ? '#dbeafe' : '#f3f4f6',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            border: `1px solid ${navMode === 'realtime' ? '#93c5fd' : '#d1d5db'}`,
            fontSize: '0.75rem',
            color: navMode === 'realtime' ? '#0c4a6e' : '#374151',
            lineHeight: '1.5'
          }}>
            {navMode === 'realtime' ? (
              <>
                <strong>📡 Real-Time Mode:</strong> Live GPS tracking + live rainfall from KSNDMC. Traffic data fetched automatically. Shows actual conditions.
              </>
            ) : (
              <>
                <strong>🎮 Simulated Mode:</strong> Test evacuation scenarios with historical rainfall patterns. Control rainfall intensity, evolution, and toggle traffic for testing. Fast-forward with speed slider.
              </>
            )}
          </div>


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

          {/* Real-time CONFIG: Minimal navigation info only */}
          {phase === 'CONFIG' && navMode === 'realtime' && (
            <>
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
                </div>
              )}

              <div style={{
                background: '#ecfdf5',
                padding: '1rem',
                borderRadius: '0.75rem',
                border: '1px solid #6ee7b7',
                fontSize: '0.85rem',
                color: '#065f46',
                lineHeight: '1.6'
              }}>
                <div style={{ fontWeight: '700', marginBottom: '0.5rem' }}>📡 Real-Time Navigation</div>
                Live rainfall tracking from KSNDMC • GPS-based position updates • Dynamic flood alerts during journey
              </div>

              <button
                onClick={handleStartSimulation}
                style={{
                  width: '100%',
                  background: '#10b981',
                  color: 'white',
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                  boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                  transition: 'all 0.2s',
                  marginTop: '0.5rem'
                }}
                onMouseOver={(e) => e.target.style.background = '#059669'}
                onMouseOut={(e) => e.target.style.background = '#10b981'}
              >
                ▶️ START JOURNEY
              </button>
            </>
          )}

          {/* Simulated CONFIG: Full scenario testing controls */}
          {phase === 'CONFIG' && navMode === 'simulated' && (
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
                  <option value="car">🚗 Car (40 km/h)</option>
                  <option value="bike">🚴 Bike (30 km/h)</option>
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
                  <option value="random">🎲 Random (0-200mm)</option>
                  <option value="light">🌧️ Light (0-10mm)</option>
                  <option value="moderate">⛈️ Moderate (10-30mm)</option>
                  <option value="heavy">🌊 Heavy (30-60mm, synth: 45mm)</option>
                  <option value="extreme">🌪️ Extreme (60-200mm, synth: 100mm)</option>
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

              <div style={{
                background: '#dbeafe',
                padding: '0.75rem',
                borderRadius: '0.5rem',
                border: '1px solid #93c5fd',
                fontSize: '0.875rem'
              }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={useTraffic}
                    onChange={(e) => setUseTraffic(e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <span style={{ fontWeight: '600' }}>🚗 Consider Traffic</span>
                </label>
                <div style={{ fontSize: '0.75rem', color: '#0369a1', marginTop: '0.5rem', marginLeft: '1.75rem' }}>
                  {useTraffic ? '✓ Realistic congestion' : '⚡ Ignore traffic'}
                </div>
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
                  marginTop: '0.5rem'
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

          {(phase === 'RUNNING' || phase === 'PAUSED') && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {/* Location info - Google Maps style */}
              <div style={{ fontSize: '0.75rem', color: '#6b7280', padding: '0.75rem', background: '#f9fafb', borderRadius: '0.5rem' }}>
                <div style={{ marginBottom: '0.4rem' }}>📍 <strong>From:</strong> {startPoint ? `${startPoint.lat.toFixed(4)}, ${startPoint.lon.toFixed(4)}` : 'Unknown'}</div>
                <div>🎯 <strong>To:</strong> {endPoint ? `${endPoint.lat.toFixed(4)}, ${endPoint.lon.toFixed(4)}` : 'Unknown'}</div>
              </div>

              {/* Elapsed time matching vehicle movement */}
              <div style={{
                background: navMode === 'realtime' ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
                color: 'white',
                padding: '1.25rem',
                borderRadius: '0.75rem',
                textAlign: 'center',
                boxShadow: navMode === 'realtime' ? '0 4px 12px rgba(16, 185, 129, 0.3)' : '0 4px 12px rgba(79, 70, 229, 0.3)',
              }}>
                <div style={{ fontSize: '3rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>
                  {navMode === 'realtime' ? 'LIVE' : `${Math.round(tick * 0.2)}'`}
                </div>
                <div style={{ fontSize: '0.75rem', opacity: 0.9 }}>
                  {navMode === 'realtime' ? 'Real-Time Navigation Active' : `Elapsed Time (of ${stats ? Math.round((stats.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60) : 0} min)`}
                </div>
              </div>

              {/* Real-time mode: GPS-based journey info only */}
              {navMode === 'realtime' && stats != null && (
                <div style={{ background: '#f3f4f6', padding: '1rem', borderRadius: '0.75rem', fontSize: '0.85rem', lineHeight: '1.8' }}>
                  {(() => {
                    const totalDist = routeData?.summary?.total_distance_m || 1;
                    const progress = Math.round(Math.min(99, (1 - (stats.total_distance_m / totalDist)) * 100));
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span style={{ fontWeight: '600' }}>📍 Journey Progress</span>
                          <span style={{ fontWeight: 'bold', color: '#10b981' }}>{progress}%</span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: '#e5e7eb', borderRadius: '3px', overflow: 'hidden', marginBottom: '1rem' }}>
                          <div style={{
                            height: '100%',
                            background: 'linear-gradient(90deg, #10b981, #34d399)',
                            width: `${progress}%`,
                            transition: 'width 0.1s linear'
                          }} />
                        </div>
                      </>
                    );
                  })()}

                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>🛣️ Distance Remaining:</span>
                    <span><strong>{(stats.total_distance_m / 1000).toFixed(1)} km</strong></span>
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
                    <span>💧 Current Flood Level:</span>
                    <span>{stats.max_flood_depth_m.toFixed(2)}m {stats.max_flood_depth_m > 1.5 ? '🚫' : stats.max_flood_depth_m > 0.5 ? '⚠️' : '✅'}</span>
                  </div>

                  {/* Flood impact note */}
                  <div style={{ fontSize: '0.75rem', color: '#6b7280', paddingTop: '0.5rem', borderTop: '1px solid #e5e7eb', marginTop: '0.5rem' }}>
                    {stats.max_flood_depth_m > 1.5 && '⚠️ IMPASSABLE - Depth > 1.5m'}
                    {stats.max_flood_depth_m > 0.8 && stats.max_flood_depth_m <= 1.5 && '⚠️ High flood - Proceed with caution'}
                    {stats.max_flood_depth_m > 0.4 && stats.max_flood_depth_m <= 0.8 && '⚡ Moderate flood - All modes passable'}
                    {stats.max_flood_depth_m > 0.1 && stats.max_flood_depth_m <= 0.4 && '💧 Light flooding - Normal travel'}
                    {stats.max_flood_depth_m <= 0.1 && '✅ No flooding - Safe passage'}
                  </div>
                </div>
              )}

              {/* Simulated mode: Full statistics with ETA and time remaining */}
              {navMode === 'simulated' && stats != null && (
                <div style={{ background: '#f3f4f6', padding: '1rem', borderRadius: '0.75rem', fontSize: '0.85rem', lineHeight: '1.8' }}>
                  {(() => {
                    const actualEta = Math.round((stats.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60);
                    const progress = Math.round(Math.min(100, (tick * 0.2 / (tick * 0.2 + actualEta)) * 100));
                    return (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                          <span style={{ fontWeight: '600' }}>📍 Simulation Progress</span>
                          <span style={{ fontWeight: 'bold', color: '#4f46e5' }}>{progress}%</span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: '#e5e7eb', borderRadius: '3px', overflow: 'hidden', marginBottom: '1rem' }}>
                          <div style={{
                            height: '100%',
                            background: 'linear-gradient(90deg, #4f46e5, #7c3aed)',
                            width: `${progress}%`,
                            transition: 'width 0.1s linear'
                          }} />
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

              {/* ── Next Turn (Google Maps style) — PROMINENT ── */}
              {navMode === 'realtime' && routeSteps && routeSteps.length > 0 && currentStepIndex < routeSteps.length && (
                <div style={{
                  background: 'linear-gradient(135deg, #ffffff 0%, #f0fdf4 100%)',
                  border: '2px solid #10b981',
                  borderRadius: '1rem',
                  padding: '1rem',
                  boxShadow: '0 4px 16px rgba(16, 185, 129, 0.2)',
                }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: '600', color: '#6b7280', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                    📍 Next Turn
                  </div>
                  <div style={{ fontSize: '1.75rem', fontWeight: '800', color: '#065f46', marginBottom: '0.75rem', lineHeight: 1.2 }}>
                    {routeSteps[currentStepIndex].instruction}
                  </div>
                  <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: '0.25rem' }}>Distance to turn</div>
                      <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#059669' }}>
                        {routeSteps[currentStepIndex].distance_m >= 1000
                          ? `${(routeSteps[currentStepIndex].distance_m / 1000).toFixed(1)} km`
                          : `${routeSteps[currentStepIndex].distance_m} m`}
                      </div>
                    </div>
                    {routeSteps[currentStepIndex].flood_depth_m > 0.1 && (
                      <div style={{
                        flex: 1,
                        padding: '0.75rem',
                        background: routeSteps[currentStepIndex].flood_depth_m > 0.25 ? '#fee2e2' : '#fef3c7',
                        border: `1px solid ${routeSteps[currentStepIndex].flood_depth_m > 0.25 ? '#fca5a5' : '#fcd34d'}`,
                        borderRadius: '0.5rem'
                      }}>
                        <div style={{ fontSize: '0.7rem', fontWeight: '600', color: routeSteps[currentStepIndex].flood_depth_m > 0.25 ? '#991b1b' : '#92400e' }}>
                          ⚠️ Flood Alert
                        </div>
                        <div style={{ fontSize: '1.1rem', fontWeight: '700', color: routeSteps[currentStepIndex].flood_depth_m > 0.25 ? '#dc2626' : '#f59e0b', marginTop: '0.25rem' }}>
                          {routeSteps[currentStepIndex].flood_depth_m.toFixed(2)} m
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── Full Turn-by-turn list ── */}
              {navMode === 'realtime' && routeSteps && routeSteps.length > 0 && (
                <div style={{
                  background: '#f0fdf4',
                  border: '1px solid #86efac',
                  borderRadius: '0.75rem',
                  overflow: 'hidden',
                }}>
                  <div style={{
                    padding: '0.6rem 0.75rem',
                    background: '#10b981',
                    color: 'white',
                    fontSize: '0.75rem',
                    fontWeight: '700',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                    <span>📍 ALL TURNS</span>
                    <span>{currentStepIndex + 1} of {routeSteps.length}</span>
                  </div>
                  <div style={{ padding: '0.75rem', maxHeight: '200px', overflowY: 'auto' }}>
                    {routeSteps.map((step, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '0.5rem',
                          marginBottom: idx < routeSteps.length - 1 ? '0.5rem' : '0',
                          borderLeft: `3px solid ${idx === currentStepIndex ? '#10b981' : idx < currentStepIndex ? '#d1d5db' : '#e5e7eb'}`,
                          paddingLeft: '0.75rem',
                          background: idx === currentStepIndex ? '#ecfdf5' : 'transparent',
                          borderRadius: '0.375rem',
                          fontSize: '0.8rem',
                          opacity: idx <= currentStepIndex ? 1 : 0.6,
                        }}
                      >
                        <div style={{ fontWeight: idx === currentStepIndex ? '700' : '600', color: '#1f2937' }}>
                          {idx === currentStepIndex ? '▶️ ' : idx < currentStepIndex ? '✓ ' : '◯ '}
                          {step.instruction}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: '#6b7280', marginTop: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
                          <span>
                            {step.distance_m >= 1000 ? `${(step.distance_m / 1000).toFixed(1)} km` : `${step.distance_m} m`}
                          </span>
                          {step.flood_depth_m > 0.1 && (
                            <span style={{ color: step.flood_depth_m > 0.25 ? '#dc2626' : '#f59e0b', fontWeight: '600' }}>
                              ⚠️ {step.flood_depth_m.toFixed(2)}m
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Rerouting Animation Banner ── */}
              {isRerouting && (
                <div style={{
                  background: 'linear-gradient(135deg, #1d4ed8 0%, #3b82f6 50%, #1d4ed8 100%)',
                  backgroundSize: '200% 100%',
                  animation: 'shimmer 1.5s infinite',
                  color: 'white',
                  padding: '1rem',
                  borderRadius: '0.75rem',
                  textAlign: 'center',
                  fontWeight: 'bold',
                  fontSize: '1rem',
                  boxShadow: '0 4px 16px rgba(59, 130, 246, 0.5)',
                }}>
                  <div style={{ fontSize: '1.5rem', marginBottom: '0.25rem' }}>🔄</div>
                  <div>Rerouting...</div>
                  <div style={{ fontSize: '0.75rem', fontWeight: '400', opacity: 0.8, marginTop: '0.25rem' }}>
                    Finding safer path around flooded road
                  </div>
                </div>
              )}

              {/* ── Reroute Count Badge ── */}
              {rerouteCount > 0 && !isRerouting && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.5rem 0.75rem',
                  background: '#fef3c7',
                  border: '1px solid #fcd34d',
                  borderRadius: '0.5rem',
                  fontSize: '0.8rem',
                  color: '#92400e',
                }}>
                  <span>🔄</span>
                  <span><strong>{rerouteCount}</strong> reroute{rerouteCount > 1 ? 's' : ''} so far</span>
                </div>
              )}

              {/* ── Live Rainfall & Flood Log ── */}
              <div style={{
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '0.75rem',
                overflow: 'hidden',
              }}>
                <div style={{
                  padding: '0.6rem 0.75rem',
                  background: '#1e293b',
                  color: '#94a3b8',
                  fontSize: '0.75rem',
                  fontWeight: '700',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}>
                  <span>📡 {navMode === 'realtime' ? 'LIVE FLOOD ALERTS' : 'LIVE UPDATES'}</span>
                  <span style={{ fontFamily: 'monospace', color: '#67e8f9' }}>
                    {rainfallLog.length > 0 ? `${rainfallLog[rainfallLog.length - 1].avg_rainfall_mm_hr}mm/hr` : '--'}
                  </span>
                </div>
                <div
                  id="rainfall-log-scroll"
                  style={{
                    maxHeight: '160px',
                    overflowY: 'auto',
                    padding: '0.25rem',
                  }}
                  ref={el => {
                    if (el) el.scrollTop = el.scrollHeight;
                  }}
                >
                  {rainfallLog.length === 0 && (
                    <div style={{ padding: '0.5rem', fontSize: '0.75rem', color: '#94a3b8', textAlign: 'center' }}>
                      {navMode === 'realtime' ? 'Monitoring for flood alerts...' : 'Waiting for simulation data...'}
                    </div>
                  )}
                  {rainfallLog.map((entry, idx) => {
                    const statusColor = {
                      none: '#6b7280',
                      building: '#d97706',
                      critical: '#dc2626',
                      rerouting: '#7c3aed',
                    }[entry.flood_status] || '#6b7280';
                    const statusBg = {
                      none: 'transparent',
                      building: '#fffbeb',
                      critical: '#fef2f2',
                      rerouting: '#f5f3ff',
                    }[entry.flood_status] || 'transparent';
                    return (
                      <div
                        key={idx}
                        style={{
                          padding: '0.35rem 0.5rem',
                          fontSize: '0.7rem',
                          fontFamily: 'monospace',
                          borderBottom: '1px solid #f1f5f9',
                          background: statusBg,
                          display: 'flex',
                          gap: '0.4rem',
                          alignItems: 'baseline',
                          animation: idx === rainfallLog.length - 1 ? 'fadeIn 0.3s ease-out' : 'none',
                        }}
                      >
                        <span style={{ color: '#94a3b8', flexShrink: 0, width: '28px' }}>T{entry.tick}</span>
                        <span style={{
                          width: '6px', height: '6px', borderRadius: '50%',
                          background: statusColor, flexShrink: 0, marginTop: '4px'
                        }} />
                        <span style={{ color: statusColor, flex: 1, lineHeight: '1.4' }}>
                          {entry.message}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {navMode === 'simulated' && (
                <div style={{
                  background: '#f0fdf4',
                  padding: '1rem',
                  borderRadius: '0.75rem',
                  border: '1px solid #86efac',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <label style={{ fontWeight: '600', fontSize: '0.875rem' }}>⚡ Playback Speed</label>
                    <span style={{ fontSize: '0.75rem', color: '#666', fontWeight: '600' }}>
                      {(250 / playbackSpeed).toFixed(1)}x
                    </span>
                  </div>
                  <input
                    type="range"
                    min="50"
                    max="500"
                    value={playbackSpeed}
                    onChange={(e) => {
                      const newSpeed = Number(e.target.value);
                      setPlaybackSpeed(newSpeed);
                      playbackSpeedRef.current = newSpeed;  // Update ref for active playback
                    }}
                    style={{
                      width: '100%',
                      cursor: 'pointer',
                    }}
                  />
                  <div style={{ fontSize: '0.7rem', color: '#666', marginTop: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
                    <span>⏩ Fast (0.5x)</span>
                    <span>⏯️ Normal</span>
                    <span>🐢 Slow (5x)</span>
                  </div>
                </div>
              )}

              {/* Pause button - only during active simulation */}
              {navMode === 'simulated' && phase === 'RUNNING' && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => {
                      if (tickTimerRef.current) {
                        clearTimeout(tickTimerRef.current);
                        tickTimerRef.current = null;
                      }
                      setPhase('PAUSED');
                      addNotification('⏸️ Simulation paused', 'info');
                    }}
                    style={{
                      flex: 1,
                      background: '#f59e0b',
                      color: 'white',
                      padding: '0.75rem',
                      borderRadius: '0.5rem',
                      border: 'none',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                    }}
                  >
                    ⏸️ Pause
                  </button>
                </div>
              )}

              {/* Resume button - only when paused */}
              {navMode === 'simulated' && phase === 'PAUSED' && (
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={() => {
                      setPhase('RUNNING');
                      addNotification('▶️ Simulation resumed', 'success');
                      if (isReplaying) {
                        // Resume replay from paused index
                        const playNextFrame = (idx) => {
                          if (idx >= recordedTicks.length) {
                            setPhase('COMPLETE');
                            setIsReplaying(false);
                            addNotification('✅ Replay finished', 'success');
                            return;
                          }
                          const frame = recordedTicks[idx];
                          setTick(frame.tick);
                          setPersonPos(frame.personPos);
                          setFloodOverlay(frame.floodOverlay);
                          setHeatmap(frame.heatmap);
                          if (frame.routeHistory) {
                            setRouteHistory(frame.routeHistory.map(g => ({ geojson: g })));
                          }
                          setStats(frame.stats);
                          setReplayIndex(idx + 1);
                          if (frame.rerouted) {
                            setIsRerouting(true);
                            if (frame.route_steps) {
                              setRouteSteps(frame.route_steps);
                              setCurrentStepIndex(frame.current_step_index || 0);
                            }
                            setTimeout(() => setIsRerouting(false), 1500);
                          }
                          tickTimerRef.current = setTimeout(() => playNextFrame(idx + 1), playbackSpeedRef.current);
                        };
                        playNextFrame(replayIndex);
                      } else if (sessionId) {
                        startTickLoop(sessionId, playbackSpeedRef.current);
                      }
                    }}
                    style={{
                      flex: 1,
                      background: '#10b981',
                      color: 'white',
                      padding: '0.75rem',
                      borderRadius: '0.5rem',
                      border: 'none',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                    }}
                  >
                    ▶️ Resume
                  </button>
                </div>
              )}

              {navMode === 'simulated' && phase === 'RUNNING' && (
                <>
                  {/* Replay button visible during simulation if recording exists */}
                  {recordedTicks.length > 0 && (
                    <button
                      onClick={startReplay}
                      style={{
                        width: '100%',
                        background: '#6366f1',
                        color: 'white',
                        padding: '0.75rem',
                        borderRadius: '0.5rem',
                        border: 'none',
                        fontWeight: 'bold',
                        cursor: 'pointer',
                        fontSize: '0.875rem',
                        marginBottom: '0.5rem',
                      }}
                      onMouseOver={(e) => e.target.style.background = '#4f46e5'}
                      onMouseOut={(e) => e.target.style.background = '#6366f1'}
                    >
                      🎬 Replay ({recordedTicks.length} frames so far)
                    </button>
                  )}

                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      onClick={async () => {
                        if (tickTimerRef.current) clearTimeout(tickTimerRef.current);
                        // Reset backend session to start position
                        if (sessionId) {
                          try {
                            await fetch(`${API_URL}/simulate/reset`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ session_id: sessionId }),
                            });
                          } catch { }
                        }
                        // Reset UI to start of simulation (keep recorded ticks for replay)
                        setTick(0);
                        setPersonPos(null);
                        setRouteHistory([]);
                        setStats(null);
                        setRainfallLog([]);
                        setIsRerouting(false);
                        setRerouteCount(0);
                        setCurrentStepIndex(0);
                        // Clear recorded ticks since we're starting fresh
                        setRecordedTicks([]);
                        setIsReplaying(false);
                        setReplayIndex(0);
                        setPhase('RUNNING');
                        addNotification('🔄 Simulation restarted', 'info');
                        // Resume from beginning
                        if (sessionId) {
                          startTickLoop(sessionId, playbackSpeedRef.current);
                        }
                      }}
                      style={{
                        flex: 1,
                        background: '#8b5cf6',
                        color: 'white',
                        padding: '0.75rem',
                        borderRadius: '0.5rem',
                        border: 'none',
                        fontWeight: 'bold',
                        cursor: 'pointer',
                        fontSize: '0.875rem',
                      }}
                    >
                      🔄 Restart
                    </button>
                    <button
                      onClick={handleReset}
                      style={{
                        flex: 1,
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
                </>
              )}
            </div>
          )}

          {/* Real-time COMPLETE: Minimal summary */}
          {phase === 'COMPLETE' && navMode === 'realtime' && (
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
              <div style={{ fontSize: '0.8rem', color: '#374151', padding: '0.75rem', background: '#f9fafb', borderRadius: '0.5rem', borderLeft: '4px solid #10b981' }}>
                <div style={{ marginBottom: '0.3rem' }}><strong>📍 From:</strong> {startPoint ? `${startPoint.lat.toFixed(4)}, ${startPoint.lon.toFixed(4)}` : 'Unknown'}</div>
                <div><strong>🎯 To:</strong> {endPoint ? `${endPoint.lat.toFixed(4)}, ${endPoint.lon.toFixed(4)}` : 'Unknown'}</div>
              </div>

              {stats != null && (
                <div style={{ background: '#f0fdf4', padding: '1.25rem', borderRadius: '0.75rem', fontSize: '0.875rem', lineHeight: '1.8', border: '1px solid #86efac' }}>
                  <div style={{ fontWeight: '700', marginBottom: '0.75rem', fontSize: '0.95rem' }}>📍 Journey Summary</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span>🛣️ Distance:</span>
                    <span style={{ fontWeight: '600', color: '#10b981' }}>{(stats.total_distance_m / 1000).toFixed(1)} km</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <span>💧 Max Flood Encountered:</span>
                    <span style={{ fontWeight: '600', color: stats.max_flood_depth_m > 0.5 ? '#dc2626' : '#16a34a' }}>{stats.max_flood_depth_m.toFixed(2)} m</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>🛡️ Route Status:</span>
                    <span style={{ fontWeight: '600', color: stats.safe ? '#16a34a' : '#dc2626' }}>{stats.safe ? '✅ SAFE' : '⚠️ CHALLENGING'}</span>
                  </div>
                </div>
              )}

              <button
                onClick={handleReset}
                style={{
                  width: '100%',
                  background: '#10b981',
                  color: 'white',
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  border: 'none',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.95rem',
                }}
              >
                ↻ New Journey
              </button>
            </div>
          )}

          {/* Simulated COMPLETE: Full trip analysis */}
          {phase === 'COMPLETE' && navMode === 'simulated' && (
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
                    <span style={{ fontWeight: '600', color: '#4f46e5' }}>{stats.total_time_taken_min ?? stats.eta_minutes} min</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <span>🚗 Speed Mode:</span>
                    <span style={{ fontWeight: '600' }}>{speedMode === 'car' ? '🚗 Car (40 km/h)' : speedMode === 'bike' ? '🚴 Bike (30 km/h)' : '🚶 Walking (4 km/h)'}</span>
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

              {recordedTicks.length > 0 && (
                <button
                  onClick={startReplay}
                  style={{
                    width: '100%',
                    background: '#6366f1',
                    color: 'white',
                    padding: '1rem',
                    borderRadius: '0.5rem',
                    border: 'none',
                    fontWeight: 'bold',
                    cursor: 'pointer',
                    fontSize: '0.95rem',
                    marginBottom: '0.5rem',
                  }}
                  onMouseOver={(e) => e.target.style.background = '#4f46e5'}
                  onMouseOut={(e) => e.target.style.background = '#6366f1'}
                >
                  🎬 Replay ({recordedTicks.length} frames)
                </button>
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
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(5px); }
          to { opacity: 1; transform: translateY(0); }
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
      <TutorialOverlay />
    </div>
  );
}
