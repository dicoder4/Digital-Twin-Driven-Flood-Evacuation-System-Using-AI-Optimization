/**
 * RainfallPanel.jsx
 * Historical (date-picker with RiskBadge) vs Manual (slider) rainfall input.
 */
import { useState, useEffect } from 'react';
import axios from 'axios';
import { CloudRain, Calendar, ChevronDown } from 'lucide-react';
import { RiskBadge } from './RiskBadge';
import { API_URL } from '../config';

export function RainfallPanel({ loadedHobli, rainfallMm, onRainfallChange }) {
    const [mode, setMode] = useState('historical'); // 'historical' | 'manual'
    const [records, setRecords] = useState([]);
    const [selDate, setSelDate] = useState('');
    const [selRec, setSelRec] = useState(null);

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
                    <label className="field-label">Rainfall (mm) — {rainfallMm}</label>
                    <input
                        type="range" min={5} max={500} step={5}
                        value={rainfallMm}
                        onChange={e => onRainfallChange(Number(e.target.value))}
                        className="slider"
                    />
                </>
            )}
        </section>
    );
}
