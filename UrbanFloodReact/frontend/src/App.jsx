import React, { useState, useEffect, useRef } from 'react';
import Map, { Source, Layer, NavigationControl } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import axios from 'axios';
import { Play, Pause, RefreshCw, Droplets, Clock, Activity, Loader } from 'lucide-react';

const API_URL = 'http://localhost:8000'; // Adjust if backend port differs

function App() {
  const [viewState, setViewState] = useState({
    longitude: 77.6101,
    latitude: 12.9166,
    zoom: 14
  });

  const [roadData, setRoadData] = useState(null);
  const [simData, setSimData] = useState([]);       // accumulated steps
  const [currentStep, setCurrentStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [receivedSteps, setReceivedSteps] = useState(0); // for progress bar
  const [totalSteps, setTotalSteps] = useState(0);       // total expected steps

  // Simulation Params
  const [rainfall, setRainfall] = useState(150);
  const [steps, setSteps] = useState(20);
  const [decay, setDecay] = useState(0.5);

  const animationRef = useRef(null);
  const eventSourceRef = useRef(null);  // SSE connection ref

  // Load base map data on mount
  useEffect(() => {
    axios.get(`${API_URL}/map-data`)
      .then(res => setRoadData(res.data))
      .catch(err => console.error("Error loading map data:", err));
  }, []);

  // Handle Animation
  useEffect(() => {
    if (isPlaying && simData.length > 0) {
      animationRef.current = setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= simData.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 500); // 500ms per step
    } else {
      clearInterval(animationRef.current);
    }
    return () => clearInterval(animationRef.current);
  }, [isPlaying, simData]);

  const runSimulation = () => {
    // Close any existing SSE connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setIsLoading(true);
    setIsPlaying(false);
    setCurrentStep(0);
    setSimData([]);
    setReceivedSteps(0);
    setTotalSteps(steps);

    const url = `${API_URL}/simulate-stream?rainfall_mm=${rainfall}&steps=${steps}&decay_factor=${decay}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.done) {
        // All steps received
        es.close();
        setIsLoading(false);
        setIsPlaying(true);  // auto-play from step 0
        return;
      }

      // Append the new step and advance display immediately
      setSimData(prev => {
        const updated = [...prev, data];
        return updated;
      });
      setReceivedSteps(data.step);
      // Auto-advance currentStep to latest received step while streaming
      setCurrentStep(prev => data.step - 1);
    };

    es.onerror = (err) => {
      console.error('SSE error:', err);
      es.close();
      setIsLoading(false);
      alert('Simulation stream failed. Check backend.');
    };
  };

  // Layer Styles
  const roadLayerStyle = {
    id: 'road-layer',
    type: 'line',
    paint: {
      'line-color': '#999',
      'line-width': 1,
      'line-opacity': 0.5
    }
  };

  // Flooded roads — colored green/yellow/red by risk level
  const floodedRoadLayerStyle = {
    id: 'flooded-road-layer',
    type: 'line',
    paint: {
      'line-color': [
        'match',
        ['get', 'risk'],
        'low', '#4CAF50',  // green
        'medium', '#FFC107',  // amber
        'high', '#F44336',  // red
        '#999999'             // fallback
      ],
      'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.5, 16, 3],
      'line-opacity': 0.85
    }
  };

  const floodLayerStyle = {
    id: 'flood-layer',
    type: 'fill',
    paint: {
      'fill-color': [
        'interpolate',
        ['linear'],
        ['get', 'intensity'],
        0, '#e0f3db', // Very light blue/green
        0.5, '#a8ddb5', // Light blue
        1, '#43a2ca'  // Darker blue
      ],
      'fill-opacity': 0.6,
      'fill-outline-color': 'rgba(0,0,0,0)'
    }
  };

  const currentStepData = simData.length > 0 && simData[currentStep] ? simData[currentStep] : null;

  return (
    <div className="flex h-screen w-screen bg-gray-50 text-gray-800 overflow-hidden font-sans">
      {/* Sidebar - Light Theme */}
      <div className="w-80 bg-white p-6 flex flex-col gap-6 shadow-xl z-10 border-r border-gray-200">
        <div className="flex items-center gap-3 mb-2 border-b border-gray-100 pb-4">
          <Droplets className="text-blue-500 w-8 h-8" />
          <div>
            <h1 className="text-xl font-bold text-gray-800">Urban Flood Model</h1>
            <p className="text-xs text-gray-500">Drain-based Simulation</p>
          </div>
        </div>

        {/* Controls */}
        <div className="space-y-6">
          <div className="space-y-2">
            <label className="flex justify-between text-sm font-medium text-gray-600">
              <span className="flex items-center gap-2"><Droplets size={14} /> Rainfall (mm)</span>
              <span className="text-blue-600 font-bold">{rainfall}</span>
            </label>
            <input
              type="range" min="50" max="500" value={rainfall}
              onChange={e => setRainfall(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
          </div>

          <div className="space-y-2">
            <label className="flex justify-between text-sm font-medium text-gray-600">
              <span className="flex items-center gap-2"><Clock size={14} /> Duration (Steps)</span>
              <span className="text-blue-600 font-bold">{steps}</span>
            </label>
            <input
              type="range" min="10" max="100" value={steps}
              onChange={e => setSteps(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
          </div>

          <div className="space-y-2">
            <label className="flex justify-between text-sm font-medium text-gray-600">
              <span className="flex items-center gap-2"><Activity size={14} /> Flow Decay</span>
              <span className="text-blue-600 font-bold">{decay}</span>
            </label>
            <input
              type="range" min="0.1" max="0.9" step="0.1" value={decay}
              onChange={e => setDecay(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
          </div>

          <button
            onClick={runSimulation}
            disabled={isLoading}
            className={`w-full py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition-all shadow-md
              ${isLoading ? 'bg-blue-400 cursor-not-allowed text-white' : 'bg-blue-600 hover:bg-blue-700 text-white shadow-blue-200'}`}
          >
            {isLoading ? <Loader className="animate-spin" size={18} /> : <Play fill="currentColor" size={18} />}
            {isLoading ? `Loading... ${receivedSteps}/${totalSteps}` : 'Run Simulation'}
          </button>

          {/* Live progress bar during streaming */}
          {isLoading && totalSteps > 0 && (
            <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
              <div
                className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                style={{ width: `${(receivedSteps / totalSteps) * 100}%` }}
              />
            </div>
          )}
        </div>

        {/* Playback Controls */}
        {simData.length > 0 && (
          <div className="mt-auto bg-gray-50 p-4 rounded-lg border border-gray-200 shadow-inner">
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-mono text-gray-500 font-bold">STEP {currentStep + 1}/{simData.length}</span>
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className="p-2 bg-blue-500 rounded-full hover:bg-blue-600 text-white transition-colors shadow"
              >
                {isPlaying ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}
              </button>
            </div>
            <input
              type="range" min="0" max={simData.length - 1} value={currentStep}
              onChange={e => {
                setIsPlaying(false);
                setCurrentStep(Number(e.target.value));
              }}
              className="w-full h-1 bg-gray-300 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
          </div>
        )}
      </div>

      {/* Map Area */}
      <div className="flex-1 relative">
        <Map
          {...viewState}
          onMove={evt => setViewState(evt.viewState)}
          mapStyle="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
          attributionControl={false}
        >
          <NavigationControl position="top-right" />

          {/* Base Road Network */}
          {roadData && (
            <Source id="roads" type="geojson" data={roadData}>
              <Layer {...roadLayerStyle} />
            </Source>
          )}

          {/* Dynamic Flood Layer */}
          {currentStepData && (
            <Source id="flood" type="geojson" data={currentStepData.flood_geojson}>
              <Layer {...floodLayerStyle} />
            </Source>
          )}

          {/* Flooded roads — colored by risk, rendered on top */}
          {currentStepData && currentStepData.roads_geojson && (
            <Source id="flooded-roads" type="geojson" data={currentStepData.roads_geojson}>
              <Layer {...floodedRoadLayerStyle} />
            </Source>
          )}
        </Map>

        {/* Legend */}
        <div className="absolute bottom-6 right-6 bg-white/95 backdrop-blur p-4 rounded-xl border border-gray-200 text-xs shadow-lg text-gray-700 min-w-[160px]">
          <p className="font-bold text-gray-800 mb-2 text-sm">Flood Depth</p>

          <p className="text-gray-500 font-semibold uppercase tracking-wide mb-1 mt-2" style={{ fontSize: '10px' }}>Road Risk</p>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-6 h-2 rounded-full bg-[#4CAF50]"></div>
            <span>Low (&lt; 5 cm)</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-6 h-2 rounded-full bg-[#FFC107]"></div>
            <span>Medium (5–15 cm)</span>
          </div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-2 rounded-full bg-[#F44336]"></div>
            <span>High (&gt; 15 cm)</span>
          </div>

          <p className="text-gray-500 font-semibold uppercase tracking-wide mb-1 mt-2" style={{ fontSize: '10px' }}>Flood Area</p>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-4 rounded-sm bg-[#e0f3db]"></div>
            <span>Shallow (&lt; 50 cm)</span>
          </div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-4 h-4 rounded-sm bg-[#a8ddb5]"></div>
            <span>Moderate (50–150 cm)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded-sm bg-[#43a2ca]"></div>
            <span>Deep (&gt; 150 cm)</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
