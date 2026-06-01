import React, { useState, useEffect, useRef } from 'react';
import MapComponent from './MapComponent';
import { Marker, Source, Layer } from 'react-map-gl/maplibre';
import { MapPin, Navigation, AlertCircle, ChevronUp, ChevronDown, Phone, Cloud, Search, Shield, X, GraduationCap } from 'lucide-react';
import { API_URL } from '../config';
import { useTutorial } from '../context/TutorialContext';
import TutorialOverlay from './TutorialOverlay';
import '../styles/citizen.css';

const INITIAL_VIEW_STATE = {
  longitude: 77.5946,
  latitude: 12.9716,
  zoom: 13,
};

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
        borderRadius: '14px',
        display: 'flex',
        gap: '0.75rem',
        alignItems: 'flex-start',
        animation: 'slideInDown 0.3s ease-out',
        marginBottom: '0.5rem',
        boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
      }}
    >
      {Icon && <Icon size={18} style={{ flexShrink: 0, marginTop: '2px' }} />}
      <div style={{ flex: 1, fontSize: '0.85rem', lineHeight: '1.4', fontWeight: 500 }}>{message}</div>
    </div>
  );
};

export default function CitizenView({ user, onLogout, lang, onToggleLang }) {
  const { startTutorial } = useTutorial();
  const [phase, setPhase] = useState('LOCATING');
  const [userLoc, setUserLoc] = useState(null);
  const [destination, setDestination] = useState(null);
  const [routeData, setRouteData] = useState(null);
  const [stepIdx, setStepIdx] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [error, setError] = useState(null);
  const [rerouteBanner, setRerouteBanner] = useState(null);
  const [viewState, setViewState] = useState(INITIAL_VIEW_STATE);
  const [mapTapMode, setMapTapMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [mapCoords, setMapCoords] = useState(null);
  const [showAllTurns, setShowAllTurns] = useState(false);
  const [bottomSheetExpanded, setBottomSheetExpanded] = useState(false);
  const sheetTouchStartY = useRef(null);

  // New state variables for realtime mode features
  const [notifications, setNotifications] = useState([]);
  const [alternativeRoutes, setAlternativeRoutes] = useState([]);
  const [floodOverlay, setFloodOverlay] = useState(null);
  const [maxFloodIntensity, setMaxFloodIntensity] = useState(0);
  const [routeHistory, setRouteHistory] = useState([]);
  const [shelterEvacuation, setShelterEvacuation] = useState(null);
  const [draggedMarker, setDraggedMarker] = useState(null);
  const [watchId, setWatchId] = useState(null);
  const [rerouteCount, setRerouteCount] = useState(0);
  const [isRerouting, setIsRerouting] = useState(false);

  const clickCountRef = useRef({ start_lastClick: 0, end_lastClick: 0 });
  const debounceTimerRef = useRef(null);

  const rerouteIntervalRef = useRef(null);
  const mapRef = useRef(null);

  const translations = {
    citizen_title: lang === 'en' ? 'Flood Navigation' : 'ಪ್ರವಾಹ ನ್ಯಾವಿಗೇಶನ್',
    finding_location: lang === 'en' ? 'Finding your location...' : 'ಸ್ಥಳ ಪತ್ತೆಹಚ್ಚಲಾಗುತ್ತಿದೆ...',
    find_route: lang === 'en' ? 'Enter Destination' : 'ಗಮ್ಯಸ್ಥಾನ ನಮೂದಿಸಿ',
    nearest_shelter: lang === 'en' ? 'Nearest Safe Shelter' : 'ಸಮೀಪದ ಸುರಕ್ಷಿತ ಆಶ್ರಯ',
    tap_on_map: lang === 'en' ? 'Or tap to select on map' : 'ನಕ್ಷೆಯಲ್ಲಿ ಟ್ಯಾಪ್ ಮಾಡಿ',
    calculating_route: lang === 'en' ? 'Calculating safe route...' : 'ಸುರಕ್ಷಿತ ಮಾರ್ಗ ಲೆಕ್ಕಿಸಲಾಗುತ್ತಿದೆ...',
    step_of: lang === 'en' ? 'Step {n} of {total}' : 'ಹಂತ {n} / {total}',
    cancel_route: lang === 'en' ? 'Cancel Route' : 'ಮಾರ್ಗ ರದ್ದುಮಾಡಿ',
    arrived: lang === 'en' ? 'You have arrived!' : 'ನೀವು ತಲುಪಿದ್ದೀರಿ!',
    shelter_arrived: lang === 'en' ? 'You are safe at {name}' : '{name} ನಲ್ಲಿ ನೀವು ಸುರಕ್ಷಿತ',
    all_flooded: lang === 'en' ? 'All routes flooded. Call 112.' : 'ಎಲ್ಲ ಮಾರ್ಗ ಮುಳುಗಿದೆ. 112 ಕರೆ ಮಾಡಿ.',
    route_updated: lang === 'en' ? 'Route updated — flood changed' : 'ಮಾರ್ಗ ನವೀಕರಿಸಲಾಗಿದೆ',
    gps_denied: lang === 'en' ? 'Enable GPS to continue' : 'GPS ಆನ್ ಮಾಡಿ',
    flood_risk_low: lang === 'en' ? 'Low Flood Risk' : 'ಕಡಿಮೆ ಪ್ರವಾಹ ಅಪಾಯ',
    flood_risk_medium: lang === 'en' ? 'Medium Flood Risk' : 'ಮಧ್ಯಮ ಪ್ರವಾಹ ಅಪಾಯ',
    flood_risk_high: lang === 'en' ? 'High Flood Risk — Caution' : 'ಹೆಚ್ಚಿನ ಪ್ರವಾಹ ಅಪಾಯ — ಎಚ್ಚರ',
    finding_shelter: lang === 'en' ? 'Finding nearest shelter...' : 'ಸಮೀಪದ ಆಶ್ರಯ ಹುಡುಕಲಾಗುತ್ತಿದೆ...',
    prev: lang === 'en' ? '← Prev' : '← ಹಿಂದಿನ',
    next: lang === 'en' ? 'Next Step →' : 'ಮುಂದಿನ →',
    search_destination: lang === 'en' ? 'Search destination...' : 'ಗಮ್ಯಸ್ಥಾನ ಹುಡುಕಿ...',
    no_data_banner: lang === 'en' ? 'Live flood data unavailable' : 'ಲೈವ್ ಡೇಟಾ ಲಭ್ಯವಿಲ್ಲ',
  };

  const addNotification = (msg, type = 'info') => {
    const id = Date.now();
    setNotifications(prev => {
      const next = [...prev, { id, msg, type }];
      return next.length > 3 ? next.slice(-3) : next;
    });
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 4000);
  };

  useEffect(() => {
    navigator.geolocation.getCurrentPosition(
      pos => {
        const loc = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        setUserLoc(loc);
        setViewState({
          longitude: pos.coords.longitude,
          latitude: pos.coords.latitude,
          zoom: 15,
        });
        setPhase('IDLE');
      },
      () => setError('gps_denied'),
    );
  }, []);

  const handleGeocodeSearch = async (query) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    setIsLoading(true);
    try {
      const resp = await fetch(`${API_URL}/citizen/geocode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          near_lat: userLoc?.lat || 12.9716,
          near_lon: userLoc?.lon || 77.5946,
        }),
      });
      const results = await resp.json();
      setSearchResults(results);
    } catch (err) {
      console.error('Geocode error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchInputChange = (value) => {
    setSearchQuery(value);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      handleGeocodeSearch(value);
    }, 400);
  };

  const handleSelectDestination = (result) => {
    setDestination({ lat: parseFloat(result.lat), lon: parseFloat(result.lon), label: result.display_name });
    setSearchResults([]);
    setSearchQuery('');
    handleComputeRoute(parseFloat(result.lat), parseFloat(result.lon));
  };

  const handleMapClick = (coords) => {
    if (draggedMarker) return;
    if (mapTapMode && phase === 'DESTINATION_INPUT') {
      setDestination({ lat: coords.lat, lon: coords.lon, label: 'Selected Location' });
      setMapTapMode(false);
      handleComputeRoute(coords.lat, coords.lon);
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

      const dx = Math.abs(currentX - startX);
      const dy = Math.abs(currentY - startY);

      if (dx > 5 || dy > 5) {
        hasMoved = true;
        if (mapRef.current) {
          const mapEl = mapRef.current.getContainer();
          const rect = mapEl.getBoundingClientRect();
          const relX = currentX - rect.left;
          const relY = currentY - rect.top;

          try {
            const lngLat = mapRef.current.unproject([relX, relY]);
            if (marker === 'start') {
              setUserLoc({ lat: lngLat.lat, lon: lngLat.lng });
            } else {
              setDestination({ lat: lngLat.lat, lon: lngLat.lng, label: 'Selected Location' });
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

      if (hasMoved && marker === 'end' && userLoc && destination) {
        setTimeout(() => {
          addNotification('🔄 Recomputing route...', 'info');
          handleComputeRoute(destination.lat, destination.lon);
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
    const now = Date.now();
    const lastClick = clickCountRef.current[`${marker}_lastClick`] || 0;
    
    if (now - lastClick < 300) {
      if (marker === 'start') {
        setUserLoc(null);
        setPhase('LOCATING');
        addNotification('❌ Start point cleared', 'info');
      } else if (marker === 'end') {
        setDestination(null);
        setPhase('DESTINATION_INPUT');
        addNotification('❌ Destination cleared', 'info');
      }
      clickCountRef.current[`${marker}_lastClick`] = 0;
    } else {
      clickCountRef.current[`${marker}_lastClick`] = now;
    }
  };

  const handleComputeRoute = async (dstLat, dstLon) => {
    if (!userLoc) return;
    setIsLoading(true);
    setPhase('ROUTING');
    try {
      const resp = await fetch(`${API_URL}/citizen/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          src_lat: userLoc.lat,
          src_lon: userLoc.lon,
          dst_lat: dstLat,
          dst_lon: dstLon,
        }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        setRouteData(data);
        setAlternativeRoutes(data.alternative_routes || []);
        setFloodOverlay(data.flood_overlay || null);
        setMaxFloodIntensity(data.active_ward_rainfall || 0);
        addNotification(`✅ Route found (${(data.total_distance_m / 1000).toFixed(1)} km)`, 'success');
        setPhase('CONFIG');
      } else if (data.status === 'error' && data.message && data.message.toLowerCase().includes('flooded')) {
        addNotification('🌊 ' + data.message, 'error');
        setPhase('SHELTER_EVACUATION');
      } else {
        setError(data.message || 'Route computation failed');
        setPhase('IDLE');
      }
    } catch (err) {
      setError(err.message);
      setPhase('IDLE');
    } finally {
      setIsLoading(false);
    }
  };

  const handleNearestShelter = async () => {
    if (!userLoc) return;
    setIsLoading(true);
    setPhase('ROUTING');
    try {
      const resp = await fetch(`${API_URL}/citizen/nearest-shelter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          src_lat: userLoc.lat,
          src_lon: userLoc.lon,
        }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        setRouteData(data);
        setAlternativeRoutes(data.alternative_routes || []);
        setFloodOverlay(data.flood_overlay || null);
        setMaxFloodIntensity(data.active_ward_rainfall || 0);
        setDestination(data.shelter
          ? { lat: data.shelter.lat, lon: data.shelter.lon, label: data.shelter.name }
          : destination
        );
        addNotification(`✅ Safe shelter found (${(data.total_distance_m / 1000).toFixed(1)} km)`, 'success');
        setPhase('CONFIG');
      } else if (data.status === 'error' && data.message && data.message.toLowerCase().includes('flooded')) {
        addNotification('🌊 ' + data.message, 'error');
        setPhase('SHELTER_EVACUATION');
      } else {
        setError(data.message || 'Shelter search failed');
        setPhase('IDLE');
      }
    } catch (err) {
      setError(err.message);
      setPhase('IDLE');
    } finally {
      setIsLoading(false);
    }
  };

  const startRerouteLoop = (rData) => {
    if (rerouteIntervalRef.current) clearInterval(rerouteIntervalRef.current);
    rerouteIntervalRef.current = setInterval(async () => {
      try {
        if (!userLoc) return;
        setIsRerouting(true);
        const res = await fetch(`${API_URL}/citizen/location-update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: rData.session_id,
            current_lat: userLoc.lat,
            current_lon: userLoc.lon,
            dst_lat: destination.lat,
            dst_lon: destination.lon,
            active_ward_rainfall: rData.active_ward_rainfall,
          }),
        }).then(r => r.json());

        setIsRerouting(false);

        if (res.reroute_needed && res.new_route) {
          setRouteHistory(prev => [...prev, rData]);
          setRouteData(res.new_route);
          setStepIdx(0);
          setRerouteCount(prev => prev + 1);
          setRerouteBanner(res.reason);
          addNotification('🔄 Route updated — flood conditions changed', 'warning');
          setTimeout(() => setRerouteBanner(null), 5000);
        }
      } catch (err) {
        setIsRerouting(false);
        console.error('Reroute loop error:', err);
      }
    }, 30000);
  };

  useEffect(() => {
    let watchIdVal = null;
    if (phase === 'NAVIGATING' && routeData) {
      startRerouteLoop(routeData);
      watchIdVal = navigator.geolocation.watchPosition(
        (pos) => {
          setUserLoc({ lat: pos.coords.latitude, lon: pos.coords.longitude });
          setViewState(prev => ({ ...prev, longitude: pos.coords.longitude, latitude: pos.coords.latitude }));
        },
        (err) => console.error('GPS Watch error:', err),
        { enableHighAccuracy: true, maximumAge: 10000 }
      );
      setWatchId(watchIdVal);
    }
    return () => {
      if (rerouteIntervalRef.current) clearInterval(rerouteIntervalRef.current);
      if (watchIdVal !== null) navigator.geolocation.clearWatch(watchIdVal);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [phase, routeData, destination]);

  const cancelRoute = () => {
    setPhase('IDLE');
    setRouteData(null);
    setDestination(null);
    setAlternativeRoutes([]);
    setFloodOverlay(null);
    setRouteHistory([]);
    setStepIdx(0);
    setRerouteCount(0);
    setIsRerouting(false);
    setShowAllTurns(false);
    if (rerouteIntervalRef.current) clearInterval(rerouteIntervalRef.current);
    if (watchId) {
      navigator.geolocation.clearWatch(watchId);
      setWatchId(null);
    }
  };

  const nextStep = () => {
    if (routeData && stepIdx < routeData.steps.length - 1) {
      setStepIdx(stepIdx + 1);
    } else if (routeData && stepIdx === routeData.steps.length - 1) {
      setPhase('ARRIVED');
    }
  };

  const prevStep = () => {
    if (stepIdx > 0) setStepIdx(stepIdx - 1);
  };

  const currentStep = routeData?.steps[stepIdx];
  const distanceRemaining = routeData
    ? routeData.steps.slice(stepIdx).reduce((sum, s) => sum + s.distance_m, 0)
    : 0;
  const totalDistance = routeData?.total_distance_m || 1;
  const progressPercent = routeData
    ? Math.round(Math.min(99, (1 - distanceRemaining / totalDistance) * 100))
    : 0;

  // Flood depth helpers
  const floodDepth = routeData?.max_flood_depth_m || 0;
  const getFloodColor = (depth) => depth > 1.5 ? '#dc2626' : depth > 0.5 ? '#ea580c' : '#16a34a';
  const getFloodNote = (depth) => {
    if (depth > 1.5) return '⚠️ IMPASSABLE — Depth > 1.5m';
    if (depth > 0.8) return '⚠️ High flood — Proceed with caution';
    if (depth > 0.4) return '⚡ Moderate flood — All modes passable';
    if (depth > 0.1) return '💧 Light flooding — Normal travel';
    return '✅ No flooding — Safe passage';
  };

  return (
    <div className="citizen-view">

      {/* ─── FLOATING GLASS HEADER (non-navigation phases) ─── */}
      {phase !== 'NAVIGATING' && (
        <div className="floating-glass-header">
          <h1>
            <Navigation size={18} />
            {translations.citizen_title}
          </h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="tutorial-trigger-btn tutorial-trigger-btn--header"
              onClick={() => startTutorial('citizen')}
              title={lang === 'en' ? 'Take a guided tutorial' : 'ಮಾರ್ಗದರ್ಶಿ ಟ್ಯುಟೋರಿಯಲ್'}
            >
              <GraduationCap size={13} />
              {lang === 'en' ? 'Tutorial' : 'ಟ್ಯುಟೋರಿಯಲ್'}
            </button>
            <button onClick={onLogout}>Logout</button>
          </div>
        </div>
      )}

      {/* ─── NOTIFICATION TOASTS ─── */}
      <div style={{ position: 'absolute', top: phase === 'NAVIGATING' ? '160px' : '70px', left: '12px', right: '12px', zIndex: 200, pointerEvents: 'none' }}>
        {notifications.map(n => (
          <div key={n.id} style={{ pointerEvents: 'auto' }}>
            <NotificationBanner message={n.msg} type={n.type} icon={n.type === 'warning' ? AlertCircle : n.type === 'error' ? AlertCircle : n.type === 'success' ? MapPin : Cloud} />
          </div>
        ))}
      </div>

      {/* ─── MAP (full-bleed) ─── */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 0 }}>
        {error && (
          <div style={{ position: 'absolute', top: 70, left: 12, right: 12, zIndex: 100, background: '#fee2e2', border: '1px solid #fca5a5', color: '#991b1b', padding: '12px 16px', borderRadius: 14, display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, fontWeight: 600, boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
            <AlertCircle size={16} />
            {error === 'gps_denied' ? translations.gps_denied : error}
            <button onClick={() => setError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: '#991b1b' }}><X size={16} /></button>
          </div>
        )}

        <MapComponent
          viewState={viewState}
          onMove={setViewState}
          onMapClick={handleMapClick}
          mapRef={mapRef}
          routeData={routeData}
          routeHistory={routeHistory}
        >
          {floodOverlay?.features?.length > 0 && (
            <Source id="flood-corridor" type="geojson" data={floodOverlay}>
              <Layer
                id="flood-corridor-line"
                type="line"
                paint={{
                  'line-color': ['match', ['get', 'flood_risk'], 'high', '#dc2626', 'medium', '#f59e0b', 'low', '#60a5fa', '#93c5fd'],
                  'line-width': ['interpolate', ['linear'], ['zoom'], 12, 2, 16, 5],
                  'line-opacity': 0.45,
                }}
              />
            </Source>
          )}

          {phase === 'CONFIG' && alternativeRoutes?.map((alt, idx) => (
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

          {userLoc && (
            <Marker longitude={userLoc.lon} latitude={userLoc.lat} anchor="bottom">
              <div
                style={{
                  width: '36px', height: '36px', background: '#2563eb', borderRadius: '50%',
                  border: draggedMarker === 'start' ? '3px solid #fbbf24' : '3px solid white',
                  boxShadow: draggedMarker === 'start' ? '0 0 0 8px rgba(251, 191, 36, 0.3)' : '0 2px 8px rgba(37, 99, 235, 0.4)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '16px', fontWeight: 'bold', color: 'white',
                  cursor: draggedMarker === 'start' ? 'grabbing' : 'grab',
                  transition: 'box-shadow 0.2s', userSelect: 'none',
                }}
                onMouseDown={(e) => handleMarkerMouseDown(e, 'start')}
                onClick={(e) => handleMarkerClick(e, 'start')}
                title="Drag to move, double-click to remove"
              >
                A
              </div>
            </Marker>
          )}

          {destination && (
            <Marker longitude={destination.lon} latitude={destination.lat} anchor="bottom">
              <div
                style={{
                  width: '36px', height: '36px', background: '#dc2626', borderRadius: '50%',
                  border: draggedMarker === 'end' ? '3px solid #fbbf24' : '3px solid white',
                  boxShadow: draggedMarker === 'end' ? '0 0 0 8px rgba(251, 191, 36, 0.3)' : '0 2px 8px rgba(220, 38, 38, 0.4)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '16px', fontWeight: 'bold', color: 'white',
                  cursor: draggedMarker === 'end' ? 'grabbing' : 'grab',
                  transition: 'box-shadow 0.2s', userSelect: 'none',
                }}
                onMouseDown={(e) => handleMarkerMouseDown(e, 'end')}
                onClick={(e) => handleMarkerClick(e, 'end')}
                title="Drag to move, double-click to remove"
              >
                B
              </div>
            </Marker>
          )}
        </MapComponent>

        {(phase === 'NAVIGATING' || phase === 'SHELTER_EVACUATION') && <RainOverlay intensity={maxFloodIntensity} />}
      </div>

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/*  BOTTOM SHEETS — one per phase                                */}
      {/* ═══════════════════════════════════════════════════════════════ */}

      {/* ── LOCATING ── */}
      {phase === 'LOCATING' && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 24 }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ textAlign: 'center', padding: '20px 0', color: '#64748b' }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>📍</div>
            <div style={{ fontWeight: 600 }}>{translations.finding_location}</div>
          </div>
        </div>
      )}

      {/* ── IDLE — Google Maps style home screen ── */}
      {phase === 'IDLE' && userLoc && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 28 }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, fontSize: 13, color: '#64748b', fontWeight: 500 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#22c55e' }}></div>
            Your location detected
          </div>
          <button
            onClick={() => setPhase('DESTINATION_INPUT')}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '14px 18px',
              background: '#f1f5f9',
              border: 'none',
              borderRadius: 16,
              cursor: 'pointer',
              marginBottom: 12,
              transition: 'background 0.15s',
            }}
            onMouseOver={e => e.currentTarget.style.background = '#e2e8f0'}
            onMouseOut={e => e.currentTarget.style.background = '#f1f5f9'}
          >
            <Search size={18} style={{ color: '#2563eb' }} />
            <span style={{ color: '#64748b', fontSize: 15, fontWeight: 500 }}>Search destination...</span>
          </button>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={() => setPhase('DESTINATION_INPUT')}
              className="citizen-btn btn-primary"
              style={{ flex: 1 }}
            >
              <Navigation size={16} />
              {translations.find_route}
            </button>
            <button
              onClick={handleNearestShelter}
              disabled={isLoading}
              className="citizen-btn btn-green"
              style={{ flex: 1 }}
            >
              <Shield size={16} />
              {isLoading ? '...' : translations.nearest_shelter}
            </button>
          </div>
        </div>
      )}

      {/* ── DESTINATION INPUT ── */}
      {phase === 'DESTINATION_INPUT' && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 24 }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#f1f5f9', borderRadius: 14, padding: '4px 4px 4px 16px', marginBottom: 10 }}>
            <Search size={16} style={{ color: '#94a3b8', flexShrink: 0 }} />
            <input
              type="text"
              placeholder={translations.search_destination}
              value={searchQuery}
              onChange={e => handleSearchInputChange(e.target.value)}
              autoFocus
              style={{
                flex: 1, border: 'none', outline: 'none', background: 'transparent',
                padding: '12px 0', fontSize: 15, fontWeight: 500, color: '#1e293b',
                fontFamily: 'Inter, sans-serif',
              }}
            />
            {searchQuery && (
              <button onClick={() => { setSearchQuery(''); setSearchResults([]); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8 }}>
                <X size={16} style={{ color: '#94a3b8' }} />
              </button>
            )}
          </div>

          <button
            onClick={() => setMapTapMode(!mapTapMode)}
            style={{
              background: mapTapMode ? '#dbeafe' : 'transparent',
              border: mapTapMode ? '1px solid #93c5fd' : '1px solid transparent',
              padding: '8px 12px', borderRadius: 10, cursor: 'pointer',
              fontSize: 13, color: '#2563eb', fontWeight: 600, marginBottom: 8,
              display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s',
            }}
          >
            <MapPin size={14} />
            {translations.tap_on_map}
            {mapTapMode && ' ✓'}
          </button>

          <div style={{ maxHeight: 200, overflowY: 'auto', borderRadius: 12 }}>
            {searchResults.map((r, i) => (
              <button
                key={i}
                onClick={() => handleSelectDestination(r)}
                style={{
                  width: '100%', textAlign: 'left', padding: '12px 14px',
                  background: 'transparent', border: 'none', borderBottom: '1px solid #f1f5f9',
                  cursor: 'pointer', fontSize: 13, color: '#374151', fontWeight: 500,
                  transition: 'background 0.1s', display: 'flex', alignItems: 'flex-start', gap: 10,
                }}
                onMouseOver={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseOut={e => e.currentTarget.style.background = 'transparent'}
              >
                <MapPin size={14} style={{ color: '#94a3b8', marginTop: 2, flexShrink: 0 }} />
                <span>{r.display_name}</span>
              </button>
            ))}
          </div>

          <button onClick={() => setPhase('IDLE')} className="citizen-btn btn-secondary" style={{ marginTop: 8 }}>
            Back
          </button>
        </div>
      )}

      {/* ── ROUTING (loading) ── */}
      {phase === 'ROUTING' && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 24 }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ textAlign: 'center', padding: '24px 0', color: '#64748b' }}>
            <div style={{ fontSize: 28, marginBottom: 8, animation: 'citizen-pulse 1.5s infinite' }}>🗺️</div>
            <div style={{ fontWeight: 600 }}>{translations.calculating_route}</div>
          </div>
        </div>
      )}

      {/* ── CONFIG — Route preview ── */}
      {phase === 'CONFIG' && routeData && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 24 }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 26, fontWeight: 900, color: '#059669', lineHeight: 1 }}>
                {routeData.eta_minutes || Math.round((routeData.total_distance_m / 1000) / 30 * 60)} min
              </div>
              <div style={{ fontSize: 12, color: '#64748b', fontWeight: 500, marginTop: 4 }}>
                {(routeData.total_distance_m / 1000).toFixed(1)} km • ETA (inc. traffic)
              </div>
            </div>
            <div style={{
              padding: '6px 14px',
              borderRadius: 10,
              fontWeight: 700,
              fontSize: 12,
              background: routeData.safe ? '#dcfce7' : '#fef3c7',
              color: routeData.safe ? '#166534' : '#92400e',
            }}>
              {routeData.safe ? '✅ Safe Route' : '⚠️ Has Flooding'}
            </div>
          </div>

          <div className="journey-stats" style={{ marginBottom: 12 }}>
            <div className="stat-row">
              <span>🛣️ Distance</span>
              <strong>{(routeData.total_distance_m / 1000).toFixed(1)} km</strong>
            </div>
            <hr className="stat-divider" />
            <div className="stat-row">
              <span>💧 Max Flood Depth</span>
              <strong style={{ color: getFloodColor(floodDepth) }}>{floodDepth.toFixed(2)} m</strong>
            </div>
            <hr className="stat-divider" />
            <div className="stat-row">
              <span>📊 Flood Assessment</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: getFloodColor(floodDepth) }}>{getFloodNote(floodDepth)}</span>
            </div>
            {alternativeRoutes?.length > 0 && (
              <>
                <hr className="stat-divider" />
                <div className="stat-row">
                  <span>🔀 Alternative Routes</span>
                  <strong>{alternativeRoutes.length} found</strong>
                </div>
              </>
            )}
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={() => { setPhase('NAVIGATING'); setStepIdx(0); }}
              className="citizen-btn btn-primary"
              style={{ flex: 2 }}
            >
              <Navigation size={16} /> Start Navigation
            </button>
            <button
              onClick={cancelRoute}
              className="citizen-btn btn-secondary"
              style={{ flex: 1 }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── SHELTER EVACUATION ── */}
      {phase === 'SHELTER_EVACUATION' && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 24, borderTop: '4px solid #dc2626' }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
            <AlertCircle size={22} style={{ color: '#dc2626' }} />
            <span style={{ fontWeight: 800, fontSize: 17, color: '#991b1b' }}>Severe Flood Warning</span>
          </div>
          <p style={{ fontSize: 13, color: '#64748b', lineHeight: 1.6, marginBottom: 14 }}>
            Your destination route is blocked by impassable floods. 
            For your safety, evacuate to the nearest emergency shelter immediately.
          </p>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={handleNearestShelter}
              disabled={isLoading}
              className="citizen-btn btn-danger"
              style={{ flex: 2 }}
            >
              {isLoading ? 'Routing...' : '🚨 Route to Safe Shelter'}
            </button>
            <button
              onClick={() => { setPhase('IDLE'); setDestination(null); }}
              className="citizen-btn btn-secondary"
              style={{ flex: 1 }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════ */}
      {/*  NAVIGATING — Google Maps style top bar + bottom sheet        */}
      {/* ═══════════════════════════════════════════════════════════════ */}
      {phase === 'NAVIGATING' && routeData && currentStep && (
        <>
          {/* ── Top Navigation Bar (Google Maps green bar) ── */}
          <div className="nav-top-bar">
            <div className="nav-instruction-area">
              <div className="nav-label">
                <Navigation size={12} style={{ animation: 'citizen-pulse 2s infinite' }} />
                NEXT TURN
              </div>
              <div className="nav-instruction">{currentStep.instruction}</div>
              <div className="nav-meta-row">
                <div className="nav-distance-block">
                  <div className="nav-distance-label">Distance</div>
                  <div className="nav-distance-value">
                    {currentStep.distance_m >= 1000
                      ? `${(currentStep.distance_m / 1000).toFixed(1)} km`
                      : `${currentStep.distance_m} m`}
                  </div>
                </div>
                {currentStep.flood_depth_m > 0.1 && (
                  <div className="nav-flood-chip">
                    <span className="nav-flood-chip-label">⚠️ Flood</span>
                    <span className="nav-flood-chip-value">{currentStep.flood_depth_m.toFixed(2)}m</span>
                  </div>
                )}
              </div>
            </div>
            {/* Progress bar */}
            <div className="nav-progress-bar">
              <div className="nav-progress-bar-fill" style={{ width: `${progressPercent}%` }}></div>
            </div>
          </div>

          {/* ── Rerouting Banner ── */}
          {isRerouting && (
            <div style={{ position: 'absolute', top: 170, left: 12, right: 12, zIndex: 100 }}>
              <div className="reroute-banner">
                🔄 Checking for safer route...
              </div>
            </div>
          )}

          {/* ── Bottom Navigation Sheet (expandable) ── */}
          <div
            className="citizen-bottom-sheet"
            style={{
              paddingBottom: 28,
              maxHeight: bottomSheetExpanded ? '80vh' : '200px',
              transition: 'max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
              overflowY: bottomSheetExpanded ? 'auto' : 'hidden',
            }}
          >
            {/* Draggable / tappable handle */}
            <div
              className="bottom-sheet-handle"
              style={{ cursor: 'grab', padding: '8px 0', marginBottom: 8 }}
              onClick={() => setBottomSheetExpanded(prev => !prev)}
              onTouchStart={(e) => { sheetTouchStartY.current = e.touches[0].clientY; }}
              onTouchEnd={(e) => {
                if (sheetTouchStartY.current !== null) {
                  const dy = e.changedTouches[0].clientY - sheetTouchStartY.current;
                  if (dy < -30) setBottomSheetExpanded(true);   // swipe up → expand
                  if (dy > 30)  setBottomSheetExpanded(false);  // swipe down → collapse
                  sheetTouchStartY.current = null;
                }
              }}
            ></div>

            {/* ── ALWAYS VISIBLE: ETA row + Prev/Next ── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span className="live-badge" style={{ fontSize: 14, padding: '6px 12px' }}>LIVE</span>
                  <span style={{ fontSize: 22, fontWeight: 900, color: '#059669' }}>
                    {routeData.eta_minutes || Math.round((routeData.total_distance_m / 1000) / 30 * 60)} min
                  </span>
                </div>
                <div style={{ fontSize: 12, color: '#64748b', fontWeight: 500, marginTop: 4 }}>
                  {Math.round(distanceRemaining / 1000 * 10) / 10} km remaining • with live traffic • Step {stepIdx + 1}/{routeData.steps.length}
                </div>
              </div>
              <button
                onClick={cancelRoute}
                style={{
                  background: '#fee2e2', color: '#dc2626', border: 'none',
                  borderRadius: 12, padding: '10px 18px', fontWeight: 700, fontSize: 13,
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
                onMouseOver={e => { e.currentTarget.style.background = '#fecaca'; }}
                onMouseOut={e => { e.currentTarget.style.background = '#fee2e2'; }}
              >
                Exit
              </button>
            </div>

            {/* Prev / Next controls — always visible */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 6 }}>
              <button onClick={prevStep} disabled={stepIdx === 0} className="citizen-btn btn-secondary" style={{ flex: 1 }}>← Prev</button>
              <button onClick={nextStep} className="citizen-btn btn-primary" style={{ flex: 1 }}>Next →</button>
            </div>

            {/* Expand hint */}
            <div
              onClick={() => setBottomSheetExpanded(prev => !prev)}
              style={{ textAlign: 'center', padding: '6px 0 2px 0', cursor: 'pointer', color: '#94a3b8', fontSize: 11, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}
            >
              {bottomSheetExpanded ? <><ChevronDown size={14} /> Less details</> : <><ChevronUp size={14} /> More details</>}
            </div>

            {/* ── EXPANDED CONTENT ── */}
            {bottomSheetExpanded && (
              <div style={{ animation: 'fadeIn 0.25s ease-out', marginTop: 8 }}>
                {/* Journey progress */}
                <div className="journey-stats" style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>📍 Journey Progress</span>
                    <span style={{ fontWeight: 800, color: '#059669', fontSize: 13 }}>{progressPercent}%</span>
                  </div>
                  <div style={{ width: '100%', height: 5, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden', marginBottom: 10 }}>
                    <div style={{
                      height: '100%',
                      background: 'linear-gradient(90deg, #10b981, #34d399)',
                      width: `${progressPercent}%`,
                      transition: 'width 0.4s ease',
                      borderRadius: '0 3px 3px 0',
                    }} />
                  </div>
                  <div className="stat-row">
                    <span>🛣️ Distance Remaining</span>
                    <strong>{(distanceRemaining / 1000).toFixed(1)} km</strong>
                  </div>
                  <hr className="stat-divider" />
                  <div className="stat-row" style={{ color: getFloodColor(floodDepth), fontWeight: 700 }}>
                    <span>💧 Max Flood Level</span>
                    <span>{floodDepth.toFixed(2)}m {floodDepth > 1.5 ? '🚫' : floodDepth > 0.5 ? '⚠️' : '✅'}</span>
                  </div>
                  <hr className="stat-divider" />
                  <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 500 }}>
                    {getFloodNote(floodDepth)}
                  </div>
                </div>

                {/* Reroute count */}
                {rerouteCount > 0 && (
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 12px', background: '#fef3c7', border: '1px solid #fcd34d',
                    borderRadius: 10, fontSize: 12, color: '#92400e', fontWeight: 600, marginBottom: 10,
                  }}>
                    🔄 <strong>{rerouteCount}</strong> reroute{rerouteCount > 1 ? 's' : ''} so far
                  </div>
                )}

                {/* ── Full Turn-by-turn list (collapsible within expanded) ── */}
                <div className="turns-list-container" style={{ marginBottom: 10 }}>
                  <div className="turns-list-header" onClick={() => setShowAllTurns(!showAllTurns)} style={{ cursor: 'pointer' }}>
                    <span>📍 ALL TURNS</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {stepIdx + 1} of {routeData.steps.length}
                      {showAllTurns ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </span>
                  </div>
                  {showAllTurns && (
                    <div className="turns-list-body">
                      {routeData.steps.map((step, idx) => (
                        <div
                          key={idx}
                          className={`turn-item ${idx === stepIdx ? 'active' : idx < stepIdx ? 'done' : ''}`}
                        >
                          <div className="turn-instruction">
                            {idx === stepIdx ? '▶️ ' : idx < stepIdx ? '✓ ' : '◯ '}
                            {step.instruction}
                          </div>
                          <div className="turn-meta">
                            <span>{step.distance_m >= 1000 ? `${(step.distance_m / 1000).toFixed(1)} km` : `${step.distance_m} m`}</span>
                            {step.flood_depth_m > 0.1 && (
                              <span className={`turn-flood-badge ${step.flood_depth_m > 0.25 ? 'danger' : 'warning'}`}>
                                ⚠️ {step.flood_depth_m.toFixed(2)}m
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── ARRIVED ── */}
      {phase === 'ARRIVED' && (
        <div className="citizen-bottom-sheet" style={{ paddingBottom: 28 }}>
          <div className="bottom-sheet-handle"></div>
          <div style={{ textAlign: 'center', padding: '12px 0 20px 0' }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>🎉</div>
            <p style={{ fontSize: 20, fontWeight: 800, color: '#059669', marginBottom: 4 }}>
              {translations.arrived}
            </p>
            {routeData?.shelter && (
              <p style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>
                {translations.shelter_arrived.replace('{name}', routeData.shelter.name)}
              </p>
            )}

            {routeData && (
              <div className="journey-stats" style={{ margin: '16px 0', textAlign: 'left' }}>
                <div className="stat-row">
                  <span>🛣️ Distance Covered</span>
                  <strong style={{ color: '#059669' }}>{(routeData.total_distance_m / 1000).toFixed(1)} km</strong>
                </div>
                <hr className="stat-divider" />
                <div className="stat-row">
                  <span>💧 Max Flood Encountered</span>
                  <strong style={{ color: getFloodColor(floodDepth) }}>{floodDepth.toFixed(2)} m</strong>
                </div>
                <hr className="stat-divider" />
                <div className="stat-row">
                  <span>🛡️ Route Status</span>
                  <strong style={{ color: routeData.safe ? '#16a34a' : '#dc2626' }}>{routeData.safe ? '✅ SAFE' : '⚠️ CHALLENGING'}</strong>
                </div>
                {rerouteCount > 0 && (
                  <>
                    <hr className="stat-divider" />
                    <div className="stat-row">
                      <span>🔄 Reroutes</span>
                      <strong>{rerouteCount}</strong>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
          <button
            onClick={() => {
              setPhase('IDLE');
              setRouteData(null);
              setDestination(null);
              setRerouteCount(0);
            }}
            className="citizen-btn btn-primary"
          >
            Start New Route
          </button>
        </div>
      )}
      <TutorialOverlay />
    </div>
  );
}
