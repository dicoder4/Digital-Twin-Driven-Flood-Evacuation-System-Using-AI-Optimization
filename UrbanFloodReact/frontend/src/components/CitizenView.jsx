import React, { useState, useEffect, useRef } from 'react';
import MapComponent from './MapComponent';
import CitizenRouteLayer from './CitizenRouteLayer';
import { MapPin, Navigation, AlertCircle, ChevronUp, ChevronDown, Phone } from 'lucide-react';
import { API_URL } from '../config';
import '../styles/citizen.css';

const INITIAL_VIEW_STATE = {
  longitude: 77.5946,
  latitude: 12.9716,
  zoom: 13,
};

export default function CitizenView({ user, onLogout, lang, onToggleLang }) {
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

  const rerouteIntervalRef = useRef(null);
  const mapRef = useRef(null);

  const translations = {
    citizen_title: lang === 'en' ? 'Flood Navigation' : 'ಪ್ರವಾಹ ನ್ಯಾವಿಗೇಶನ್',
    finding_location: lang === 'en' ? 'Finding your location...' : 'ಸ್ಥಳ ಪತ್ತೆಹಚ್ಚಲಾಗುತ್ತಿದೆ...',
    find_route: lang === 'en' ? 'Enter Destination' : 'ಗಮ್ಯಸ್ಥಾನ ನಮೂದಿಸಿ',
    nearest_shelter: lang === 'en' ? 'Nearest Safe Shelter' : 'ಸಮೀಪದ ಸುರಕ್ಷಿತ ಆಶ್ರಯ',
    tap_on_map: lang === 'en' ? 'Tap to select on map' : 'ನಕ್ಷೆಯಲ್ಲಿ ಟ್ಯಾಪ್ ಮಾಡಿ',
    calculating_route: lang === 'en' ? 'Calculating safe route...' : 'ಸುರಕ್ಷಿತ ಮಾರ್ಗ ಲೆಕ್ಕಿಸಲಾಗುತ್ತಿದೆ...',
    step_of: lang === 'en' ? 'Step {n} of {total}' : 'ಹಂತ {n} / {total}',
    cancel_route: lang === 'en' ? 'Cancel Route' : 'ಮಾರ್ಗ ರದ್ದುಮಾಡಿ',
    arrived: lang === 'en' ? 'You have arrived' : 'ನೀವು ತಲುಪಿದ್ದೀರಿ',
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

  const handleSelectDestination = (result) => {
    setDestination({ lat: parseFloat(result.lat), lon: parseFloat(result.lon), label: result.display_name });
    setSearchResults([]);
    setSearchQuery('');
    handleComputeRoute(parseFloat(result.lat), parseFloat(result.lon));
  };

  const handleMapClick = (coords) => {
    if (mapTapMode && phase === 'DESTINATION_INPUT') {
      setDestination({ lat: coords.lat, lon: coords.lon, label: 'Selected Location' });
      setMapTapMode(false);
      handleComputeRoute(coords.lat, coords.lon);
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
        setPhase('NAVIGATING');
        setStepIdx(0);
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
        setDestination(data.shelter
          ? { lat: data.shelter.lat, lon: data.shelter.lon, label: data.shelter.name }
          : destination
        );
        setPhase('NAVIGATING');
        setStepIdx(0);
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
        const pos = await new Promise((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(
            p => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
            reject
          );
        });
        const res = await fetch(`${API_URL}/citizen/location-update`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: rData.session_id,
            current_lat: pos.lat,
            current_lon: pos.lon,
            dst_lat: destination.lat,
            dst_lon: destination.lon,
            active_ward_rainfall: rData.active_ward_rainfall,
          }),
        }).then(r => r.json());

        if (res.reroute_needed && res.new_route) {
          setRouteData(res.new_route);
          setStepIdx(0);
          setRerouteBanner(res.reason);
          setTimeout(() => setRerouteBanner(null), 5000);
        }
      } catch (err) {
        console.error('Reroute loop error:', err);
      }
    }, 30000);
  };

  useEffect(() => {
    if (phase === 'NAVIGATING' && routeData) {
      startRerouteLoop(routeData);
    }
    return () => {
      if (rerouteIntervalRef.current) clearInterval(rerouteIntervalRef.current);
    };
  }, [phase, routeData, destination]);

  const cancelRoute = () => {
    setPhase('IDLE');
    setRouteData(null);
    setDestination(null);
    setStepIdx(0);
    if (rerouteIntervalRef.current) clearInterval(rerouteIntervalRef.current);
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

  return (
    <div className="citizen-view h-screen w-screen flex flex-col bg-gray-50">
      <div className="citizen-header bg-blue-600 text-white px-4 py-3 flex justify-between items-center">
        <h1 className="text-lg font-bold flex items-center gap-2">
          <Navigation size={20} />
          {translations.citizen_title}
        </h1>
        <button onClick={onLogout} className="text-sm bg-blue-700 px-3 py-1 rounded">
          Logout
        </button>
      </div>

      <div className="flex-1 relative">
        {error && (
          <div className="absolute top-4 left-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded flex items-center gap-2 z-50">
            <AlertCircle size={18} />
            {error === 'gps_denied' ? translations.gps_denied : error}
          </div>
        )}

        {rerouteBanner && (
          <div className="absolute top-16 left-4 right-4 bg-amber-100 border border-amber-400 text-amber-700 px-4 py-2 rounded z-50">
            {rerouteBanner}
          </div>
        )}

        <MapComponent
          viewState={viewState}
          onMove={setViewState}
          onMapClick={handleMapClick}
          mapRef={mapRef}
          routeData={routeData}
          routeHistory={[]}
        />
      </div>

      {phase === 'LOCATING' && (
        <div className="citizen-bottom-sheet h-32">
          <div className="text-center text-gray-600 py-8">
            {translations.finding_location}
          </div>
        </div>
      )}

      {phase === 'IDLE' && userLoc && (
        <div className="citizen-bottom-sheet h-40 flex flex-col gap-4">
          <p className="text-sm text-gray-600 flex items-center gap-1">
            <MapPin size={16} /> Your location detected
          </p>
          <button
            onClick={() => setPhase('DESTINATION_INPUT')}
            className="citizen-btn bg-blue-600 text-white hover:bg-blue-700"
          >
            <Navigation size={18} />
            {translations.find_route}
          </button>
          <button
            onClick={handleNearestShelter}
            disabled={isLoading}
            className="citizen-btn bg-green-600 text-white hover:bg-green-700"
          >
            {isLoading ? translations.finding_shelter : translations.nearest_shelter}
          </button>
        </div>
      )}

      {phase === 'DESTINATION_INPUT' && (
        <div className="citizen-bottom-sheet h-auto max-h-96 flex flex-col gap-3 pb-6">
          <input
            type="text"
            placeholder={translations.search_destination}
            value={searchQuery}
            onChange={e => {
              setSearchQuery(e.target.value);
              handleGeocodeSearch(e.target.value);
            }}
            className="w-full px-4 py-2 border border-gray-300 rounded"
          />
          <button
            onClick={() => {
              setMapTapMode(!mapTapMode);
            }}
            className="text-sm text-blue-600 flex items-center gap-1"
          >
            <MapPin size={16} />
            {translations.tap_on_map}
            {mapTapMode && ' (active)'}
          </button>
          <div className="divide-y max-h-40 overflow-y-auto">
            {searchResults.map((r, i) => (
              <button
                key={i}
                onClick={() => handleSelectDestination(r)}
                className="w-full text-left px-3 py-2 hover:bg-gray-100 text-sm"
              >
                {r.display_name}
              </button>
            ))}
          </div>
          <button
            onClick={() => setPhase('IDLE')}
            className="citizen-btn bg-gray-400 text-white hover:bg-gray-500"
          >
            Back
          </button>
        </div>
      )}

      {phase === 'ROUTING' && (
        <div className="citizen-bottom-sheet h-32">
          <div className="text-center text-gray-600 py-8">
            {translations.calculating_route}
          </div>
        </div>
      )}

      {phase === 'NAVIGATING' && routeData && currentStep && (
        <div className="citizen-bottom-sheet h-56 flex flex-col gap-3">
          <div className="flex justify-between text-xs text-gray-600">
            <span>
              {translations.step_of.replace('{n}', stepIdx + 1).replace('{total}', routeData.steps.length)}
            </span>
            <span>{Math.round(distanceRemaining / 1000 * 10) / 10} km remaining</span>
          </div>

          <div className="bg-gray-100 p-3 rounded">
            <p className="font-semibold text-sm">{currentStep.instruction}</p>
            <p className="text-xs text-gray-600 mt-1">
              Distance: {currentStep.distance_m}m
            </p>
          </div>

          {currentStep.flood_depth_m > 0.1 && (
            <div className={`p-2 rounded text-xs font-semibold flex items-center gap-2 ${
              currentStep.flood_risk === 'high' ? 'bg-red-100 text-red-700' :
              currentStep.flood_risk === 'medium' ? 'bg-yellow-100 text-yellow-700' :
              'bg-green-100 text-green-700'
            }`}>
              <AlertCircle size={16} />
              {currentStep.flood_risk === 'high' ? translations.flood_risk_high :
               currentStep.flood_risk === 'medium' ? translations.flood_risk_medium :
               translations.flood_risk_low}
              {currentStep.flood_depth_m > 0 && ` (${currentStep.flood_depth_m.toFixed(2)}m)`}
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={prevStep}
              disabled={stepIdx === 0}
              className="citizen-btn bg-gray-400 text-white hover:bg-gray-500 disabled:opacity-50"
            >
              {translations.prev}
            </button>
            <button
              onClick={nextStep}
              className="citizen-btn bg-blue-600 text-white hover:bg-blue-700"
            >
              {translations.next}
            </button>
            <button
              onClick={cancelRoute}
              className="citizen-btn bg-red-500 text-white hover:bg-red-600"
            >
              {translations.cancel_route}
            </button>
          </div>
        </div>
      )}

      {phase === 'ARRIVED' && (
        <div className="citizen-bottom-sheet h-40 flex flex-col items-center justify-center gap-4">
          <div className="text-center">
            <p className="text-xl font-bold text-green-600">✓ {translations.arrived}</p>
            {routeData?.shelter && (
              <p className="text-sm text-gray-600 mt-2">
                {translations.shelter_arrived.replace('{name}', routeData.shelter.name)}
              </p>
            )}
          </div>
          <button
            onClick={() => {
              setPhase('IDLE');
              setRouteData(null);
              setDestination(null);
            }}
            className="citizen-btn bg-blue-600 text-white hover:bg-blue-700 w-40"
          >
            Start New Route
          </button>
        </div>
      )}
    </div>
  );
}
