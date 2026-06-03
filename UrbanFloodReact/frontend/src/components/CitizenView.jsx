import React, { useState, useEffect, useRef } from 'react';
import MapComponent from './MapComponent';
import { Marker, Source, Layer } from 'react-map-gl/maplibre';
import { MapPin, Navigation, AlertCircle, ChevronUp, ChevronDown, Phone, Cloud, Search, Shield, X, GraduationCap, LogOut } from 'lucide-react';
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
  const [searchTarget, setSearchTarget] = useState('destination');
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
    if (searchTarget === 'start') {
      setUserLoc({ lat: parseFloat(result.lat), lon: parseFloat(result.lon) });
      setSearchTarget('destination');
      setSearchResults([]);
      setSearchQuery('');
    } else {
      setDestination({ lat: parseFloat(result.lat), lon: parseFloat(result.lon), label: result.display_name });
      setSearchResults([]);
      setSearchQuery('');
      handleComputeRoute(parseFloat(result.lat), parseFloat(result.lon));
    }
  };

  const handleMapClick = (coords) => {
    if (draggedMarker) return;
    if (mapTapMode && phase === 'DESTINATION_INPUT') {
      if (searchTarget === 'start') {
        setUserLoc({ lat: coords.lat, lon: coords.lon });
        setSearchTarget('destination');
        setMapTapMode(false);
      } else {
        setDestination({ lat: coords.lat, lon: coords.lon, label: 'Selected Location' });
        setMapTapMode(false);
        handleComputeRoute(coords.lat, coords.lon);
      }
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

  const handleSheetTouchStart = (e) => {
    sheetTouchStartY.current = e.touches[0].clientY;
  };
  const handleSheetTouchMove = (e) => {
    if (!sheetTouchStartY.current) return;
    const currentY = e.touches[0].clientY;
    const diff = sheetTouchStartY.current - currentY;
    if (diff > 50) setBottomSheetExpanded(true);
    else if (diff < -50) setBottomSheetExpanded(false);
  };
  const handleSheetTouchEnd = () => {
    sheetTouchStartY.current = null;
  };

  return (
    <div className="citizen-view">
      {/* ─── FULL-SCREEN MAP ─── */}
      <div id="tutorial-sim-map" style={{ position: 'absolute', inset: 0, zIndex: 10 }}>
        {error && (
          <div style={{ position: 'absolute', top: 80, left: '50%', transform: 'translateX(-50%)', zIndex: 100, background: '#fee2e2', border: '1px solid #fca5a5', color: '#991b1b', padding: '12px 16px', borderRadius: 14, display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, fontWeight: 600, boxShadow: '0 4px 12px rgba(0,0,0,0.08)', width: 'max-content', maxWidth: '90%' }}>
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
                  width: '28px', height: '28px', background: '#2563eb', borderRadius: '50%',
                  border: draggedMarker === 'start' ? '3px solid #fbbf24' : '3px solid white',
                  boxShadow: draggedMarker === 'start' ? '0 0 0 8px rgba(251, 191, 36, 0.3)' : '0 2px 8px rgba(37, 99, 235, 0.4)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '12px', fontWeight: 'bold', color: 'white',
                  cursor: draggedMarker === 'start' ? 'grabbing' : 'grab',
                  transition: 'box-shadow 0.2s', userSelect: 'none',
                }}
                onMouseDown={(e) => handleMarkerMouseDown(e, 'start')}
                onClick={(e) => handleMarkerClick(e, 'start')}
                title="Drag to move, double-click to remove"
              />
            </Marker>
          )}

          {destination && (
            <Marker longitude={destination.lon} latitude={destination.lat} anchor="bottom">
              <div
                style={{
                  width: '32px', height: '32px', background: '#dc2626', borderRadius: '50%',
                  border: draggedMarker === 'end' ? '3px solid #fbbf24' : '3px solid white',
                  boxShadow: draggedMarker === 'end' ? '0 0 0 8px rgba(251, 191, 36, 0.3)' : '0 2px 8px rgba(220, 38, 38, 0.4)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '14px', fontWeight: 'bold', color: 'white',
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

      {/* ─── FLOATING SEARCH CARD ─── */}
      {(phase === 'IDLE' || phase === 'LOCATING' || phase === 'ARRIVED') && (
        <div className="floating-search-card" id="tutorial-sim-header" onClick={() => setPhase('DESTINATION_INPUT')}>
          <div className="search-icon"><Search size={20} /></div>
          <input 
            type="text" 
            placeholder={translations.search_destination} 
            readOnly 
            style={{ cursor: 'pointer' }}
          />
          <div className="profile-actions">
            <button onClick={(e) => { e.stopPropagation(); startTutorial('citizen'); }} className="tutorial-trigger-btn tutorial-trigger-btn--header logout-icon-btn" style={{ color: '#64748b' }}>
              <GraduationCap size={18} />
            </button>
            <button onClick={(e) => { e.stopPropagation(); onLogout(); }} className="logout-icon-btn">
              <LogOut size={18} />
            </button>
            <div className="profile-avatar" onClick={(e) => e.stopPropagation()}>
              {user?.username ? user.username.charAt(0).toUpperCase() : 'U'}
            </div>
          </div>
        </div>
      )}

      {/* ─── FLOATING IDLE ACTIONS ─── */}
      {phase === 'IDLE' && (
        <div style={{ position: 'absolute', bottom: '24px', left: '16px', right: '16px', zIndex: 50, display: 'flex', gap: '12px', justifyContent: 'center' }}>
          <button
            onClick={handleNearestShelter}
            disabled={isLoading}
            className="citizen-btn btn-green"
            style={{ padding: '14px 24px', borderRadius: '100px', fontSize: '15px', fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.2)' }}
          >
            <Shield size={18} /> {isLoading ? 'Searching...' : translations.nearest_shelter}
          </button>
        </div>
      )}

      {/* ─── NAVIGATING TOP BAR (Google Maps style) ─── */}
      {phase === 'NAVIGATING' && routeData && currentStep && (
        <div className="nav-top-bar">
          <div className="nav-instruction-area">
            <div className="nav-label">
              <Navigation size={12} style={{ animation: 'citizen-pulse 2s infinite' }} />
              NEXT TURN
            </div>
            <div className="nav-instruction">{currentStep.instruction}</div>
            
            <div className="nav-meta-row">
              <div className="nav-distance-block">
                <div className="nav-distance-label">DISTANCE</div>
                <div className="nav-distance-value">
                  {currentStep.distance_m >= 1000 ? `${(currentStep.distance_m / 1000).toFixed(1)} km` : `${currentStep.distance_m} m`}
                </div>
              </div>
              
              {currentStep.flood_depth_m > 0.1 && (
                <div className="nav-flood-chip">
                  <div className="nav-flood-chip-label">⚠️ FLOOD</div>
                  <div className="nav-flood-chip-value">{currentStep.flood_depth_m.toFixed(2)}m</div>
                </div>
              )}
            </div>
          </div>
          
          <div className="nav-progress-bar">
            <div className="nav-progress-bar-fill" style={{ width: `${progressPercent}%` }}></div>
          </div>

          {isRerouting && (
            <div style={{ background: '#f59e0b', padding: '6px 16px', color: '#fff', fontWeight: 'bold', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center' }}>
              <AlertCircle size={14} /> Rerouting due to live conditions...
            </div>
          )}
        </div>
      )}

      {/* ─── FLOATING NOTIFICATIONS ─── */}
      <div style={{ position: 'absolute', top: phase === 'NAVIGATING' ? '140px' : '80px', left: '16px', right: '16px', zIndex: 100, pointerEvents: 'none' }}>
        {notifications.map(n => (
          <div key={n.id} style={{ pointerEvents: 'auto' }}>
            <NotificationBanner message={n.msg} type={n.type} icon={n.type === 'warning' ? AlertCircle : n.type === 'error' ? AlertCircle : n.type === 'success' ? MapPin : Cloud} />
          </div>
        ))}
      </div>

      {/* ─── FLOATING ACTION BUTTONS (Right side) ─── */}
      {(phase === 'IDLE' || phase === 'CONFIG') && userLoc && (
        <div style={{ position: 'absolute', right: '16px', bottom: bottomSheetExpanded ? '85vh' : '45vh', zIndex: 50, display: 'flex', flexDirection: 'column', gap: '10px', transition: 'bottom 0.3s cubic-bezier(0.4, 0, 0.2, 1)' }}>
           <button onClick={() => setViewState(prev => ({ ...prev, longitude: userLoc.lon, latitude: userLoc.lat, zoom: 15 }))} style={{ width: 44, height: 44, borderRadius: '50%', background: 'white', border: '1px solid #e2e8f0', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#2563eb' }}>
             <Navigation size={20} />
           </button>
        </div>
      )}

      {/* ─── BOTTOM SHEET ─── */}
      {phase !== 'IDLE' && (
        <div 
          className="citizen-bottom-sheet" id="tutorial-sim-config"
          style={{ maxHeight: bottomSheetExpanded ? '85vh' : (phase === 'NAVIGATING' ? '40vh' : '45vh') }}
          onTouchStart={handleSheetTouchStart}
          onTouchMove={handleSheetTouchMove}
          onTouchEnd={handleSheetTouchEnd}
        >
          <div className="bottom-sheet-handle"></div>

          {/* ── LOCATING ── */}
          {phase === 'LOCATING' && (
            <div style={{ textAlign: 'center', padding: '20px 0', color: '#64748b' }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>📍</div>
              <div style={{ fontWeight: 600 }}>{translations.finding_location}</div>
            </div>
          )}

        {/* ── DESTINATION INPUT ── */}
        {phase === 'DESTINATION_INPUT' && (
          <div style={{ height: bottomSheetExpanded ? '75vh' : 'auto' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: '#f8fafc', borderRadius: 16, padding: 12, marginBottom: 16, border: '1px solid #e2e8f0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: searchTarget === 'start' ? '#fff' : '#f1f5f9', border: searchTarget === 'start' ? '1px solid #93c5fd' : '1px solid transparent', borderRadius: 10, padding: '4px 12px', cursor: 'pointer' }} onClick={() => setSearchTarget('start')}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#3b82f6', flexShrink: 0 }}></div>
                <input
                  type="text"
                  placeholder={userLoc ? "Your Location" : "Choose start location"}
                  value={searchTarget === 'start' ? searchQuery : ''}
                  onChange={e => { setSearchTarget('start'); handleSearchInputChange(e.target.value); }}
                  autoFocus={searchTarget === 'start'}
                  style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', padding: '10px 0', fontSize: 14, fontWeight: 500, color: '#1e293b' }}
                />
                {searchTarget === 'start' && searchQuery && (
                  <button onClick={(e) => { e.stopPropagation(); setSearchQuery(''); setSearchResults([]); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}><X size={16} style={{ color: '#94a3b8' }} /></button>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: searchTarget === 'destination' ? '#fff' : '#f1f5f9', border: searchTarget === 'destination' ? '1px solid #93c5fd' : '1px solid transparent', borderRadius: 10, padding: '4px 12px', cursor: 'pointer' }} onClick={() => setSearchTarget('destination')}>
                <MapPin size={16} style={{ color: '#ef4444', flexShrink: 0 }} />
                <input
                  type="text"
                  placeholder={translations.search_destination}
                  value={searchTarget === 'destination' ? searchQuery : ''}
                  onChange={e => { setSearchTarget('destination'); handleSearchInputChange(e.target.value); }}
                  autoFocus={searchTarget === 'destination'}
                  style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', padding: '10px 0', fontSize: 14, fontWeight: 500, color: '#1e293b' }}
                />
                {searchTarget === 'destination' && searchQuery && (
                  <button onClick={(e) => { e.stopPropagation(); setSearchQuery(''); setSearchResults([]); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}><X size={16} style={{ color: '#94a3b8' }} /></button>
                )}
              </div>
            </div>

            <button
              onClick={() => setMapTapMode(!mapTapMode)}
              style={{
                background: mapTapMode ? '#dbeafe' : '#f8fafc',
                border: mapTapMode ? '1px solid #93c5fd' : '1px solid #e2e8f0',
                padding: '12px', borderRadius: 12, cursor: 'pointer',
                fontSize: 14, color: mapTapMode ? '#2563eb' : '#475569', fontWeight: 600, marginBottom: 12,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, transition: 'all 0.15s', width: '100%'
              }}
            >
              <MapPin size={16} />
              {translations.tap_on_map}
              {mapTapMode && ' ✓'}
            </button>

            <div style={{ overflowY: 'auto', maxHeight: '50vh', paddingBottom: '16px' }}>
              {searchResults.map((r, i) => (
                <button
                  key={i}
                  onClick={() => handleSelectDestination(r)}
                  style={{
                    width: '100%', textAlign: 'left', padding: '16px',
                    background: 'white', borderBottom: '1px solid #f1f5f9',
                    cursor: 'pointer', fontSize: 14, color: '#374151', fontWeight: 500,
                    display: 'flex', alignItems: 'center', gap: 14,
                  }}
                >
                  <MapPin size={18} style={{ color: '#94a3b8', flexShrink: 0 }} />
                  <span>{r.display_name}</span>
                </button>
              ))}
            </div>

            <button onClick={() => setPhase('IDLE')} className="citizen-btn btn-secondary" style={{ marginTop: '16px' }}>
              Cancel
            </button>
          </div>
        )}

        {/* ── ROUTING ── */}
        {phase === 'ROUTING' && (
          <div style={{ textAlign: 'center', padding: '30px 0', color: '#64748b' }}>
            <div style={{ fontSize: 36, marginBottom: 16, animation: 'citizen-pulse 1.5s infinite' }}>🗺️</div>
            <div style={{ fontWeight: 600, fontSize: '1.05rem' }}>{translations.calculating_route}</div>
          </div>
        )}

        {/* ── CONFIG ── */}
        {phase === 'CONFIG' && routeData && (
          <div>
            <div style={{ background: routeData.safe ? '#f0fdf4' : '#fef2f2', border: `1px solid ${routeData.safe ? '#86efac' : '#fecaca'}`, padding: '1rem', borderRadius: '16px', marginBottom: '1rem' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: routeData.safe ? '#059669' : '#dc2626', lineHeight: 1 }}>
                {routeData.eta_minutes || Math.round((routeData.total_distance_m / 1000) / 30 * 60)} min
              </div>
              <div style={{ fontSize: 13, color: '#64748b', fontWeight: 600, marginTop: 6 }}>
                {(routeData.total_distance_m / 1000).toFixed(1)} km • Fastest route
              </div>
            </div>

            <div style={{ background: 'white', padding: '12px 16px', borderRadius: '12px', border: '1px solid #f1f5f9', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                <span style={{ color: '#64748b', fontSize: '14px', fontWeight: 600 }}>💧 Max Flood Depth</span>
                <strong style={{ color: getFloodColor(floodDepth), fontSize: '14px' }}>{floodDepth.toFixed(2)} m</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b', fontSize: '14px', fontWeight: 600 }}>🛡️ Safety Status</span>
                <strong style={{ color: routeData.safe ? '#16a34a' : '#dc2626', fontSize: '14px' }}>{routeData.safe ? 'SAFE ✅' : 'RISKY ⚠️'}</strong>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button onClick={cancelRoute} className="citizen-btn btn-secondary" style={{ flex: 1, padding: '14px' }}>Cancel</button>
              <button onClick={() => { setPhase('NAVIGATING'); setStepIdx(0); setBottomSheetExpanded(false); }} className="citizen-btn btn-primary" style={{ flex: 2, padding: '14px', fontSize: '1.05rem' }}>
                <Navigation size={18} /> Start
              </button>
            </div>
          </div>
        )}

        {/* ── SHELTER EVACUATION ── */}
        {phase === 'SHELTER_EVACUATION' && (
          <div>
            <div style={{ padding: '1.25rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '16px', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <AlertCircle size={24} style={{ color: '#dc2626' }} />
                <span style={{ fontWeight: 800, fontSize: 18, color: '#991b1b' }}>Severe Flood</span>
              </div>
              <p style={{ fontSize: 14, color: '#7f1d1d', lineHeight: 1.5, margin: 0, fontWeight: 500 }}>
                Destination unreachable. Evacuate to the nearest shelter immediately.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <button onClick={() => { setPhase('IDLE'); setDestination(null); }} className="citizen-btn btn-secondary" style={{ flex: 1 }}>Cancel</button>
              <button onClick={handleNearestShelter} disabled={isLoading} className="citizen-btn btn-danger" style={{ flex: 2 }}>
                <Shield size={18} /> {isLoading ? '...' : 'Route to Shelter'}
              </button>
            </div>
          </div>
        )}

        {/* ── NAVIGATING ── */}
        {phase === 'NAVIGATING' && routeData && (
          <div style={{ display: 'flex', flexDirection: 'column', height: bottomSheetExpanded ? '75vh' : 'auto' }}>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 24, fontWeight: 900, color: '#059669', lineHeight: 1 }}>
                  {routeData.eta_minutes || Math.round((routeData.total_distance_m / 1000) / 30 * 60)} min
                </div>
                <div style={{ fontSize: 13, color: '#64748b', fontWeight: 600, marginTop: 4 }}>
                  {Math.round(distanceRemaining / 1000 * 10) / 10} km • {routeData.steps.length - stepIdx} steps left
                </div>
              </div>
              <button
                onClick={cancelRoute}
                style={{ background: '#fee2e2', color: '#dc2626', border: 'none', borderRadius: '24px', padding: '8px 16px', fontWeight: 700, fontSize: '13px', cursor: 'pointer' }}
              >
                Exit
              </button>
            </div>

            {/* Turns List - Only visible if expanded */}
            {bottomSheetExpanded && (
              <div style={{ flex: 1, overflowY: 'auto', background: '#f8fafc', borderRadius: '12px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', marginBottom: 12 }}>
                <div style={{ padding: '12px', background: 'white', borderBottom: '1px solid #e2e8f0', fontWeight: 700, color: '#334155', position: 'sticky', top: 0 }}>📍 Route Steps</div>
                <div style={{ padding: '8px' }}>
                  {routeData.steps.map((step, idx) => (
                    <div key={idx} style={{ padding: '12px', marginBottom: '8px', borderRadius: '8px', background: idx === stepIdx ? '#eff6ff' : idx < stepIdx ? 'white' : '#f1f5f9', border: `1px solid ${idx === stepIdx ? '#bfdbfe' : 'transparent'}`, opacity: idx < stepIdx ? 0.6 : 1 }}>
                      <div style={{ display: 'flex', gap: '8px', fontWeight: 600, color: idx === stepIdx ? '#1d4ed8' : '#334155', fontSize: '13px' }}>
                        <span>{idx === stepIdx ? '▶️' : idx < stepIdx ? '✓' : '◯'}</span>
                        <span>{step.instruction}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Manual Controls for demo purposes */}
            <div style={{ display: 'flex', gap: 8, marginTop: bottomSheetExpanded ? 'auto' : '0' }}>
              <button onClick={prevStep} disabled={stepIdx === 0} className="citizen-btn btn-secondary" style={{ flex: 1, padding: '10px' }}>←</button>
              <button onClick={() => setStepIdx(0)} className="citizen-btn btn-secondary" style={{ flex: 1, padding: '10px' }}>Reset</button>
              <button onClick={nextStep} className="citizen-btn btn-primary" style={{ flex: 2, padding: '10px' }}>Next →</button>
            </div>
          </div>
        )}

        {/* ── ARRIVED ── */}
        {phase === 'ARRIVED' && (
          <div style={{ textAlign: 'center', padding: '10px 0 20px' }}>
            <div style={{ fontSize: 50, marginBottom: 10 }}>🎉</div>
            <p style={{ fontSize: 22, fontWeight: 800, color: '#059669', margin: '0 0 8px 0' }}>{translations.arrived}</p>
            {routeData?.shelter && <p style={{ fontSize: 14, color: '#64748b', fontWeight: 500 }}>{translations.shelter_arrived.replace('{name}', routeData.shelter.name)}</p>}
            <button onClick={() => { setPhase('IDLE'); setRouteData(null); setDestination(null); }} className="citizen-btn btn-primary" style={{ marginTop: '24px' }}>Start New Route</button>
          </div>
        )}
      </div>
    </div>
  );
}
