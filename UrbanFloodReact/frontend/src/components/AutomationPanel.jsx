import { useState, useEffect } from 'react';
import { Power, CloudRain, Settings } from 'lucide-react';
import { API_URL } from '../config';

export function AutomationPanel({ onTriggerSimulation }) {
    const [status, setStatus] = useState({ active: false, hobli: 'Uttarahalli-1', threshold_mm: 10.0, logs: [] });
    const [hobliInput, setHobliInput] = useState('Uttarahalli-1');
    const [thresholdInput, setThresholdInput] = useState(10.0);

    useEffect(() => {
        const interval = setInterval(() => {
            fetch(`${API_URL}/automation/status`)
                .then(res => res.json())
                .then(data => {
                    setStatus(data);
                    if (data.trigger_simulation) {
                        onTriggerSimulation(data.hobli, data.threshold_mm);
                    }
                })
                .catch(console.error);
        }, 3000);
        return () => clearInterval(interval);
    }, [onTriggerSimulation]);

    const handleSave = () => {
        const payload = { active: status.active, hobli: hobliInput, threshold_mm: parseFloat(thresholdInput) || 0 };
        fetch(`${API_URL}/automation/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(() => fetchStatus());
    };

    const togglePower = () => {
        const payload = { active: !status.active, hobli: hobliInput, threshold_mm: parseFloat(thresholdInput) || 0 };
        fetch(`${API_URL}/automation/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(() => fetchStatus());
    };

    const fetchStatus = () => fetch(`${API_URL}/automation/status`).then(res => res.json()).then(setStatus);

    return (
        <section className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <h3 className="panel-title" style={{ color: '#0ea5e9', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <CloudRain size={16} /> Auto-Sentinel Pipeline
            </h3>
            <p style={{ fontSize: '0.8rem', color: '#9ca3af', marginBottom: '1.5rem', lineHeight: '1.4' }}>
                Autonomous Digital Twin trigger. Continuously polls live Open-Meteo feeds and initiates evacuation protocols natively when danger bounds are breached.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'min-content 1fr', gap: '1rem', marginBottom: '2rem', alignItems: 'center' }}>
                <button
                    onClick={togglePower}
                    style={{
                        background: status.active ? '#10b981' : '#374151',
                        color: '#fff', border: 'none', borderRadius: '50%', width: '48px', height: '48px',
                        display: 'flex', justifyContent: 'center', alignItems: 'center', cursor: 'pointer',
                        boxShadow: status.active ? '0 0 15px rgba(16,185,129,0.5)' : 'none', transition: 'all 0.3s'
                    }}
                >
                    <Power size={24} />
                </button>
                <div>
                    <div style={{ fontSize: '0.9rem', fontWeight: 600, color: status.active ? '#10b981' : '#9ca3af' }}>
                        {status.active ? 'SENTINEL ARMED' : 'SENTINEL OFFLINE'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '4px' }}>Querying live weather arrays...</div>
                </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
                <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', color: '#9ca3af', marginBottom: '0.4rem' }}>Target Hobli Partition</label>
                    <select
                        value={hobliInput}
                        onChange={e => setHobliInput(e.target.value)}
                        className="control-select"
                        style={{ width: '100%', padding: '0.5rem', borderRadius: '4px' }}
                    >
                        <option value="Uttarahalli-1">Uttarahalli (Default)</option>
                        <option value="Begur">Begur</option>
                        <option value="Kengeri">Kengeri</option>
                        <option value="Varthur">Varthur</option>
                        <option value="Yeshwanthpura">Yeshwanthpura</option>
                    </select>
                </div>
                <div>
                    <label style={{ display: 'block', fontSize: '0.75rem', color: '#9ca3af', marginBottom: '0.4rem' }}>Warning Threshold [mm/h]</label>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                            type="number"
                            step="0.1"
                            value={thresholdInput}
                            onChange={e => setThresholdInput(e.target.value)}
                            className="control-input"
                            style={{ flex: 1, padding: '0.5rem', borderRadius: '4px' }}
                        />
                        <button className="btn" onClick={handleSave} style={{ flexShrink: 0, padding: '0.5rem 1rem' }}>
                            <Settings size={14} style={{ marginRight: '6px' }} /> Sync
                        </button>
                    </div>
                </div>
            </div>

            <div style={{ flex: 1, background: '#111827', borderRadius: '6px', padding: '1rem', overflowY: 'auto', border: '1px solid #374151' }}>
                <h4 style={{ fontSize: '0.75rem', color: '#6b7280', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sentinel Subroutine Log</h4>
                <div style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#10b981', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {status.logs.length === 0 ? <span style={{ color: '#4b5563' }}>&gt; Waiting for initialization...</span> : null}
                    {status.logs.map((L, i) => (
                        <div key={i} style={{ wordBreak: 'break-all' }}>{L}</div>
                    ))}
                </div>
            </div>
        </section>
    );
}
