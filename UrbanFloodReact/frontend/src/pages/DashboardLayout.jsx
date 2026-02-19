import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Droplets, Map, CloudRain, Route, BarChart3, Activity, LogOut, ChevronRight, CheckCircle2, XCircle, User } from 'lucide-react';

import NetworkSetupPage from './NetworkSetupPage';
import FloodSimulationPage from './FloodSimulationPage';
import EvacuationPage from './EvacuationPage';
import AlgorithmComparisonPage from './AlgorithmComparisonPage';
import AnalyticsPage from './AnalyticsPage';

const TABS = [
  { id: 'setup', label: 'Network Setup', icon: Map },
  { id: 'simulation', label: 'Flood Simulation', icon: CloudRain },
  { id: 'evacuation', label: 'Evacuation Planning', icon: Route },
  { id: 'comparison', label: 'Algorithm Comparison', icon: BarChart3 },
  { id: 'analytics', label: 'Analytics', icon: Activity },
];

export default function DashboardLayout() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState('setup');

  // Global state shared across all pages
  const [appState, setAppState] = useState({
    networkLoaded: false,
    infrastructureLoaded: false,
    simulatorInitialized: false,
    simulationRun: false,
    safeCentersPrepared: false,
    evacuationDone: false,
    // Data
    edgesGeojson: null,
    infrastructure: null,
    simStats: null,
    floodGeojson: null,
    blockedRoadsGeojson: null,
    peopleGeojson: null,
    safeCenters: null,
    evacuationResult: null,
    comparisonResults: null,
    center: null,
  });

  const updateState = (updates) => setAppState(prev => ({ ...prev, ...updates }));

  const STATUS_ITEMS = [
    { label: 'Road Network', ok: appState.networkLoaded },
    { label: 'Infrastructure', ok: appState.infrastructureLoaded },
    { label: 'Flood Simulation', ok: appState.simulationRun },
    { label: 'Safe Centers', ok: appState.safeCentersPrepared },
    { label: 'Evacuation Routes', ok: appState.evacuationDone },
  ];
  const completedSteps = STATUS_ITEMS.filter(s => s.ok).length;
  const progress = (completedSteps / STATUS_ITEMS.length) * 100;

  const renderPage = () => {
    switch (activeTab) {
      case 'setup': return <NetworkSetupPage appState={appState} updateState={updateState} />;
      case 'simulation': return <FloodSimulationPage appState={appState} updateState={updateState} />;
      case 'evacuation': return <EvacuationPage appState={appState} updateState={updateState} />;
      case 'comparison': return <AlgorithmComparisonPage appState={appState} updateState={updateState} />;
      case 'analytics': return <AnalyticsPage appState={appState} updateState={updateState} />;
      default: return null;
    }
  };

  return (
    <div className="flex h-screen w-screen bg-gray-50 overflow-hidden font-sans">
      {/* Sidebar */}
      <div className="w-72 bg-white flex flex-col shadow-xl z-10 border-r border-gray-200">
        {/* Logo */}
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="bg-blue-100 p-2 rounded-lg">
              <Droplets className="w-6 h-6 text-blue-600" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-800">Flood Evacuation</h1>
              <p className="text-xs text-gray-500">AI-Powered System</p>
            </div>
          </div>
        </div>

        {/* User info */}
        <div className="px-5 py-3 bg-blue-50 border-b border-blue-100">
          <div className="flex items-center gap-2">
            <User size={14} className="text-blue-600" />
            <span className="text-sm font-medium text-blue-800">{user?.name || user?.username}</span>
          </div>
          <span className="text-xs text-blue-500 capitalize ml-5">{user?.role}</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {TABS.map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-5 py-3 text-sm font-medium transition-all
                  ${isActive
                    ? 'bg-blue-50 text-blue-700 border-r-3 border-blue-600'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-800'
                  }`}
              >
                <Icon size={18} />
                <span className="flex-1 text-left">{tab.label}</span>
                {isActive && <ChevronRight size={14} />}
              </button>
            );
          })}
        </nav>

        {/* System Status */}
        <div className="px-5 py-4 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">System Status</p>
          {STATUS_ITEMS.map((item, i) => (
            <div key={i} className="flex items-center gap-2 py-1">
              {item.ok
                ? <CheckCircle2 size={14} className="text-green-500" />
                : <XCircle size={14} className="text-red-400" />
              }
              <span className={`text-xs ${item.ok ? 'text-green-700' : 'text-gray-500'}`}>{item.label}</span>
            </div>
          ))}
          <div className="mt-2 w-full bg-gray-200 rounded-full h-1.5">
            <div className="bg-blue-500 h-1.5 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
          <p className="text-xs text-gray-400 mt-1">{completedSteps}/{STATUS_ITEMS.length} steps</p>
        </div>

        {/* Logout */}
        <button onClick={logout}
          className="flex items-center gap-2 px-5 py-3 text-sm text-red-600 hover:bg-red-50 border-t border-gray-100 transition-colors">
          <LogOut size={16} /> Sign Out
        </button>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        {renderPage()}
      </div>
    </div>
  );
}
