import { MapPin, ChevronDown, Loader, CheckCircle, CloudRain, ShieldAlert, Radio } from 'lucide-react';
import axios from 'axios';
import { useState } from 'react';
import { API_URL } from '../config';

export function DraSidebar({
    allHoblis,
    selHobli,
    onHobli,
    onLoad,
    loading,
    loaded,
    loadedHobli,
    rainfallMm,
    onRainfallChange,
    onRunEvacuation,
    simulationRunning
}) {
    const canLoad = !!selHobli && !loading;
    const [fetchingWeather, setFetchingWeather] = useState(false);
    const [weatherCondition, setWeatherCondition] = useState('');

    const handleFetchWeather = async () => {
        if (!selHobli) return;
        setFetchingWeather(true);
        try {
            const res = await axios.get(`${API_URL}/weather/current`, { params: { hobli: selHobli } });
            if (res.data.error) {
                alert(res.data.error);
            } else {
                onRainfallChange(res.data.rainfall_mm || 0);
                if (res.data.condition) {
                    setWeatherCondition(`${res.data.condition}, ${res.data.temp_c}°C`);
                }
            }
        } catch (err) {
            alert(`Failed to fetch weather: ${err.message}`);
        } finally {
            setFetchingWeather(false);
        }
    };

    return (
        <div className="sidebar-content custom-scrollbar" style={{ paddingTop: '1rem' }}>
            <div className="status-bar" style={{ position: 'relative', marginTop: 0, marginBottom: '1.5rem', backgroundColor: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca', justifyContent: 'center' }}>
                <ShieldAlert size={14} />
                <span style={{ fontWeight: 600 }}>Disaster Response Authority Mode</span>
            </div>

            <section className="panel">
                <h3 className="panel-title"><MapPin size={13} /> Select Target Region</h3>
                <label className="field-label">Hobli (Sub-district)</label>
                <div className="select-wrap">
                    <select value={selHobli} onChange={e => onHobli(e.target.value)} className="styled-select">
                        <option value="">— Select Hobli —</option>
                        {allHoblis.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                    <ChevronDown size={13} className="select-arrow" />
                </div>

                <button className={`btn-primary ${!canLoad ? 'btn-disabled' : ''}`} onClick={onLoad} disabled={!canLoad} style={{ marginTop: '1rem' }}>
                    {loading
                        ? <><Loader size={13} className="spin" /> Loading Network…</>
                        : loaded && loadedHobli === selHobli
                            ? <><CheckCircle size={13} /> Network Ready</>
                            : <><MapPin size={13} /> Initialise Network</>}
                </button>
            </section>

            {loaded && loadedHobli === selHobli && (
                <>
                    <section className="panel">
                        <h3 className="panel-title"><CloudRain size={13} /> Rainfall Parameters</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            <div>
                                <label className="field-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span>Rainfall Severity (mm)</span>
                                    <span style={{ fontWeight: 600, color: '#2563eb' }}>{rainfallMm} mm</span>
                                </label>
                                <input
                                    type="range"
                                    min="0"
                                    max="300"
                                    step="5"
                                    value={rainfallMm}
                                    onChange={(e) => {
                                        onRainfallChange(Number(e.target.value));
                                        setWeatherCondition(''); // Clear weather condition if manual override
                                    }}
                                    className="styled-slider"
                                />
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                                    <span>0 mm</span><span>300 mm (Severe)</span>
                                </div>
                            </div>

                            <button
                                className="btn-secondary"
                                onClick={handleFetchWeather}
                                disabled={fetchingWeather}
                                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                            >
                                {fetchingWeather ? <Loader size={13} className="spin" /> : <CloudRain size={13} />}
                                {fetchingWeather ? 'Fetching Open-Meteo...' : 'Fetch Real-Time Weather Data'}
                            </button>
                            
                            {weatherCondition && (
                                <div style={{ fontSize: '12px', color: '#047857', backgroundColor: '#ecfdf5', padding: '8px', borderRadius: '4px', textAlign: 'center', border: '1px solid #10b981' }}>
                                    ✓ Live Data Applied: <strong>{weatherCondition}</strong>
                                </div>
                            )}
                        </div>
                    </section>
                    
                    <section className="panel" style={{ borderLeft: '3px solid #16a34a' }}>
                        <h3 className="panel-title"><ShieldAlert size={13} /> Execution Commander</h3>
                        <div style={{ fontSize: '12px', color: '#475569', marginBottom: '1rem', lineHeight: 1.5 }}>
                            <strong>Configured Protocols:</strong>
                            <ul style={{ paddingLeft: '1.2rem', marginTop: '4px' }}>
                                <li>Algorithm: <strong>Ant Colony Optimisation (ACO)</strong></li>
                                <li>Traffic Overlay: <strong>Enabled (TomTom Live)</strong></li>
                                <li>Population Sourcing: <strong>Full Registry</strong></li>
                            </ul>
                        </div>
                        
                        <button
                            className="btn-primary"
                            onClick={onRunEvacuation}
                            disabled={simulationRunning}
                            style={{ width: '100%', backgroundColor: '#dc2626', borderColor: '#b91c1c', paddingTop: '10px', paddingBottom: '10px' }}
                        >
                            {simulationRunning ? (
                                <><Loader size={13} className="spin" /> Calculating Routes...</>
                            ) : (
                                <><Radio size={13} /> Run Evacuation Protocol</>
                            )}
                        </button>
                    </section>
                </>
            )}
        </div>
    );
}
