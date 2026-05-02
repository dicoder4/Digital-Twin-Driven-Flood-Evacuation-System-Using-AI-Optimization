import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import axios from 'axios';
import { FloodMap } from '../components/FloodMap';
import { API_URL } from '../config';
import { ShieldAlert, Clock, Users, MapPin, Building2, ChevronLeft, Download, ExternalLink, Activity, Info, BrainCircuit } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export default function SharedReportPage() {
    const { reportId } = useParams();
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [viewState, setViewState] = useState({
        longitude: 77.5946, latitude: 12.9716, zoom: 13,
    });
    const [selectedShelterId, setSelectedShelterId] = useState(null);

    useEffect(() => {
        const fetchReport = async () => {
            try {
                const res = await axios.get(`${API_URL}/api/notifications/shared-report/${reportId}`);
                setReport(res.data);
                if (res.data.map_state?.evacuation_plan?.length > 0) {
                    const firstStep = res.data.map_state.evacuation_plan[0];
                    setViewState(v => ({ ...v, latitude: firstStep.lat, longitude: firstStep.lon, zoom: 14 }));
                }
            } catch (err) {
                setError(err.response?.data?.detail || "Report not found or has expired.");
            } finally {
                setLoading(false);
            }
        };
        fetchReport();
    }, [reportId]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen bg-slate-900 text-white">
                <div className="flex flex-col items-center gap-4">
                    <Activity className="animate-pulse text-blue-400" size={48} />
                    <p className="text-lg font-medium tracking-wide">Loading Secure Digital Twin Report...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-screen bg-slate-50">
                <div className="bg-white p-8 rounded-2xl shadow-xl border border-red-100 max-w-md text-center">
                    <ShieldAlert className="text-red-500 mx-auto mb-4" size={56} />
                    <h1 className="text-2xl font-bold text-slate-800 mb-2">Report Unavailable</h1>
                    <p className="text-slate-600 mb-6">{error}</p>
                    <Link to="/login" className="inline-block px-6 py-2.5 bg-slate-800 text-white rounded-lg font-bold hover:bg-slate-700 transition-colors">
                        Back to Login
                    </Link>
                </div>
            </div>
        );
    }

    if (!report || !report.map_state) {
        return (
            <div className="flex items-center justify-center h-screen bg-slate-50">
                <div className="bg-white p-8 rounded-2xl shadow-xl border border-red-100 max-w-md text-center">
                    <ShieldAlert className="text-red-500 mx-auto mb-4" size={56} />
                    <h1 className="text-2xl font-bold text-slate-800 mb-2">Report Data Missing</h1>
                    <p className="text-slate-600 mb-6">This report was generated without interactive map data. Please generate a new report from the main simulation panel.</p>
                    <Link to="/" className="inline-block px-6 py-2.5 bg-slate-800 text-white rounded-lg font-bold hover:bg-slate-700 transition-colors">
                        Return to Digital Twin
                    </Link>
                </div>
            </div>
        );
    }

    const { map_state, evacuation_data, simulation_params, ai_report, researcher, authority, timestamp, location } = report;
    const selectedShelter = selectedShelterId ? map_state.evacuation_plan?.find(s => s.id === selectedShelterId) : null;

    return (
        <div className="flex h-screen overflow-hidden bg-slate-950">
            {/* Left Sidebar - Analysis */}
            <aside className="w-96 flex-shrink-0 bg-white border-r border-slate-200 overflow-y-auto z-10 shadow-2xl custom-scrollbar">
                <div className="p-6">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-2 text-slate-500 text-xs font-bold uppercase tracking-widest">
                            <ShieldAlert size={14} className="text-blue-600" />
                            Official Report
                        </div>
                        <span className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded font-mono uppercase">{reportId}</span>
                    </div>

                    <h1 className="text-2xl font-black text-slate-900 leading-tight mb-2 uppercase italic tracking-tighter">
                        {report.is_sos ? 'Mass SOS Alert' : 'Evacuation Analysis'}
                    </h1>
                    <p className="text-slate-500 text-sm mb-6 flex items-center gap-2">
                        <MapPin size={12} /> {location} · {timestamp}
                    </p>

                    {/* Stats Grid */}
                    <div className="grid grid-cols-2 gap-3 mb-8">
                        <div className="bg-blue-50/50 p-4 rounded-xl border border-blue-100">
                            <div className="text-[10px] font-bold text-blue-600 uppercase mb-1">Evacuated</div>
                            <div className="text-2xl font-black text-blue-900 tracking-tighter">{evacuation_data.evacuated_count?.toLocaleString()}</div>
                        </div>
                        <div className="bg-red-50/50 p-4 rounded-xl border border-red-100">
                            <div className="text-[10px] font-bold text-red-600 uppercase mb-1">Success Rate</div>
                            <div className="text-2xl font-black text-red-900 tracking-tighter">{((evacuation_data.evacuated_count / evacuation_data.total_at_risk) * 100).toFixed(1)}%</div>
                        </div>
                    </div>

                    {/* AI Analysis */}
                    {ai_report && (
                        <div className="mb-8 p-5 bg-slate-900 rounded-2xl text-slate-200 border border-slate-800 shadow-lg">
                            <div className="flex items-center gap-2 text-blue-400 font-bold text-xs uppercase tracking-wider mb-3">
                                <BrainCircuit size={16} /> Civic AI Expert Field Analysis
                            </div>
                            <div className="prose prose-invert prose-sm max-w-none prose-headings:text-white prose-strong:text-blue-300">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{ai_report}</ReactMarkdown>
                            </div>
                        </div>
                    )}

                    {/* Shelter List */}
                    <div className="mb-8">
                        <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <Building2 size={12} /> Active Safe Centers
                        </h3>
                        <div className="space-y-2">
                            {map_state.evacuation_plan.map(s => (
                                <button
                                    key={s.id}
                                    onClick={() => {
                                        setSelectedShelterId(s.id);
                                        setViewState(v => ({ ...v, latitude: s.lat, longitude: s.lon, zoom: 15 }));
                                    }}
                                    className={`w-full text-left p-3 rounded-xl border transition-all ${
                                        selectedShelterId === s.id 
                                        ? 'bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-200 translate-x-1' 
                                        : 'bg-white border-slate-100 text-slate-700 hover:border-slate-300'
                                    }`}
                                >
                                    <div className="flex justify-between items-center mb-1">
                                        <span className="text-xs font-bold truncate pr-2">{s.name}</span>
                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${selectedShelterId === s.id ? 'bg-blue-500' : 'bg-slate-100 text-slate-500'}`}>
                                            {((s.count / s.capacity) * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                    <div className={`text-[10px] ${selectedShelterId === s.id ? 'text-blue-100' : 'text-slate-400'}`}>
                                        {s.count.toLocaleString()} / {s.capacity.toLocaleString()} evacuated
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="pt-6 border-t border-slate-100 text-[10px] text-slate-400 font-medium">
                        <p>Report prepared by {researcher || authority || 'Urban Flood Model'}</p>
                        <p>© 2026 Digital Twin Flood Evacuation System</p>
                    </div>
                </div>
            </aside>

            {/* Main Map */}
            <main className="flex-1 relative">
                <FloodMap
                    viewState={viewState}
                    onMove={setViewState}
                    floodData={map_state.flood_geojson}
                    roadsData={map_state.roads_geojson}
                    riskRoadsData={map_state.roads_geojson}
                    loadedHobli={location}
                    evacuationPlan={map_state.evacuation_plan}
                    simulationDone={true}
                    selectedShelter={selectedShelter}
                    trafficRoadsData={map_state.traffic_geojson}
                    showTraffic={!!map_state.traffic_geojson}
                    busManifest={map_state.bus_manifest}
                    metroLines={map_state.metro_geojson}
                    metroStations={map_state.metro_stations}
                />
                
                {/* Map Overlay Badge */}
                <div className="absolute top-6 right-6 z-10 flex flex-col items-end gap-2 pointer-events-none">
                    <div className="bg-white/90 backdrop-blur px-4 py-2 rounded-full shadow-xl border border-slate-200 flex items-center gap-3">
                        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                        <span className="text-xs font-black text-slate-800 uppercase tracking-tighter italic">Live Digital Twin View</span>
                    </div>
                    {simulation_params && (
                        <div className="bg-slate-900/80 backdrop-blur px-4 py-2 rounded-2xl shadow-xl border border-slate-700 text-white flex flex-col items-end">
                            <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest leading-none mb-1">Scenario Parameters</span>
                            <div className="flex gap-4">
                                <div className="text-right">
                                    <span className="block text-[8px] text-slate-500 font-black uppercase">Rainfall</span>
                                    <span className="text-sm font-black text-blue-400 italic leading-none">{simulation_params.rainfall_mm}mm</span>
                                </div>
                                <div className="text-right">
                                    <span className="block text-[8px] text-slate-500 font-black uppercase">Decay</span>
                                    <span className="text-sm font-black text-blue-400 italic leading-none">{simulation_params.decay_factor}</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
