/**
 * RainfallPanel.jsx
 * Historical (date-picker with RiskBadge) vs Manual (slider) rainfall input.
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import { CloudRain, Calendar, ChevronDown, Loader } from 'lucide-react';
import { RiskBadge } from './RiskBadge';
import { API_URL } from '../config';

export function RainfallPanel({ loadedHobli, rainfallMm, onRainfallChange }) {
    const [mode, setMode] = useState('historical'); // 'historical' | 'manual'
    const [records, setRecords] = useState([]);
    const [selDate, setSelDate] = useState('');
    const [selRec, setSelRec] = useState(null);
    const [fetchingWeather, setFetchingWeather] = useState(false);
    const [weatherStatus, setWeatherStatus] = useState('');

    const handleFetchWeather = async () => {
        if (!loadedHobli) return;
        setFetchingWeather(true);
        try {
            const res = await axios.get(`${API_URL}/weather/current`, { params: { hobli: loadedHobli } });
            if (res.data.error) {
                alert(res.data.error);
            } else {
                onRainfallChange(res.data.rainfall_mm || 0);
                setWeatherStatus(`${res.data.condition} (${res.data.rainfall_mm}mm)`);
            }
        } catch (err) {
            alert("Failed to fetch weather data.");
        } finally {
            setFetchingWeather(false);
        }
    };

    // Re-fetch whenever a new hobli is loaded
    useEffect(() => {
        if (!loadedHobli) return;
        setRecords([]); setSelDate(''); setSelRec(null);
        axios.get(`${API_URL}/rainfall-data/${encodeURIComponent(loadedHobli)}`)
            .then(res => setRecords(res.data.records || []))
            .catch(() => setRecords([]));
    }, [loadedHobli]);

    const handleDateSelect = (date) => {
        setSelDate(date);
        const rec = records.find(r => r.date === date) || null;
        setSelRec(rec);
        if (rec) onRainfallChange(Math.max(1, rec.actual_mm));
    };

    return (
        <section className="panel">
            <h3 className="panel-title"><CloudRain size={13} /> Rainfall Input</h3>

            <div className="mode-toggle">
                <button className={`toggle-btn ${mode === 'historical' ? 'active' : ''}`} onClick={() => setMode('historical')}>Historical</button>
                <button className={`toggle-btn ${mode === 'manual' ? 'active' : ''}`} onClick={() => setMode('manual')}>Manual</button>
            </div>

            {mode === 'historical' ? (
                records.length > 0 ? (
                    <>
                        <label className="field-label"><Calendar size={11} /> Select Date</label>
                        <div className="select-wrap">
                            <select value={selDate} onChange={e => handleDateSelect(e.target.value)} className="styled-select">
                                <option value="">— Pick a date —</option>
                                {records.map(r => (
                                    <option key={r.date} value={r.date}>
                                        {r.date} — {r.actual_mm} mm
                                    </option>
                                ))}
                            </select>
                            <ChevronDown size={13} className="select-arrow" />
                        </div>

                        {selRec && (
                            <div className="rainfall-card">
                                <div className="rf-row"><span>Actual</span><strong>{selRec.actual_mm} mm</strong></div>
                                {selRec.normal_mm != null && <div className="rf-row"><span>Normal</span><strong>{selRec.normal_mm} mm</strong></div>}
                                {selRec.dep_pct != null && (
                                    <div className="rf-row"><span>Risk</span><RiskBadge depPct={selRec.dep_pct} /></div>
                                )}
                                <div className="rf-row"><span>→ Using</span><strong>{rainfallMm} mm</strong></div>
                            </div>
                        )}
                    </>
                ) : (
                    <p className="hint-text">No historical data for this hobli.</p>
                )
            ) : (
                <>
                    <label className="field-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>Rainfall (mm)</span>
                        <span style={{ fontWeight: 600, color: '#2563eb' }}>{rainfallMm} mm</span>
                    </label>
                    <input
                        type="range" min={0} max={500} step={5}
                        value={rainfallMm}
                        onChange={e => {
                            onRainfallChange(Number(e.target.value));
                            setWeatherStatus('');
                        }}
                        className="slider"
                    />
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>
                        <span>0 mm</span><span>500 mm</span>
                    </div>

                    <button
                        className="btn-secondary"
                        onClick={handleFetchWeather}
                        disabled={fetchingWeather || !loadedHobli}
                        style={{
                            marginTop: '1rem',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '8px',
                            width: '100%',
                            fontSize: '12px',
                            padding: '8px'
                        }}
                    >
                        {fetchingWeather ? <Loader size={13} className="spin" /> : <CloudRain size={13} />}
                        {fetchingWeather ? 'Fetching Weather...' : 'Fetch Weather Data'}
                    </button>

                    {weatherStatus && (
                        <div style={{
                            marginTop: '8px',
                            fontSize: '11px',
                            color: '#059669',
                            backgroundColor: '#ecfdf5',
                            padding: '6px',
                            borderRadius: '4px',
                            textAlign: 'center',
                            border: '1px solid #10b981'
                        }}>
                            ✓ {weatherStatus}
                        </div>
                    )}
                </>
            )}
        </section>
    );
}
