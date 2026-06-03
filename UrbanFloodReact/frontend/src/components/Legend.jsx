import { useState, useEffect } from 'react';
import { ChevronDown, ChevronUp, Layers } from 'lucide-react';

/**
 * Legend.jsx
 * Floating map legend: road risk + flood depth categories.
 * Shown only when a simulation has data.
 */
export function Legend({ visible, showTraffic }) {
    // Start collapsed on phone-sized screens
    const [collapsed, setCollapsed] = useState(() => window.innerWidth <= 768);

    useEffect(() => {
        const handleResize = () => {
            if (window.innerWidth <= 768) {
                setCollapsed(true);
            } else {
                setCollapsed(false);
            }
        };
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    if (!visible && !showTraffic) return null;

    return (
        <div className={`legend ${collapsed ? 'legend-collapsed' : ''}`} style={collapsed ? { minWidth: 'auto', padding: '10px 14px' } : {}}>
            <div 
                className="legend-header" 
                onClick={() => setCollapsed(!collapsed)}
                style={{ 
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
                    cursor: 'pointer', marginBottom: collapsed ? 0 : 8, gap: '16px' 
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: 13, color: '#334155' }}>
                    <Layers size={14} style={{ color: '#3b82f6' }} />
                    Legend
                </div>
                {collapsed ? <ChevronUp size={16} color="#64748b" /> : <ChevronDown size={16} color="#64748b" />}
            </div>

            {!collapsed && (
                <div className="legend-content">
                    {visible && (
                        <>
                            <p className="legend-section">ROAD RISK</p>
                            <LegendRow color="#22c55e" label="Low (< 5 cm)" />
                            <LegendRow color="#f59e0b" label="Medium (5–15 cm)" />
                            <LegendRow color="#ef4444" label="High (> 15 cm)" />

                            <p className="legend-section" style={{ marginTop: 8 }}>FLOOD AREA</p>
                            <LegendRow color="rgba(147, 197, 253, 0.45)" label="Shallow (< 5 cm)" box />
                            <LegendRow color="rgba(59, 130, 246, 0.75)" label="Moderate (5–15 cm)" box />
                            <LegendRow color="rgba(3, 23, 174, 0.85)" label="Deep (> 15 cm)" box />
                        </>
                    )}

                    {showTraffic && (
                        <>
                            <p className="legend-section" style={{ marginTop: visible ? 10 : 0 }}>🚦 LIVE TRAFFIC</p>
                            <div className="legend-row"><span>🚦</span><span style={{ color: '#dc2626', fontWeight: 600 }}>Heavy</span><span style={{ color: '#94a3b8' }}>&gt;2× slowdown</span></div>
                            <div className="legend-row"><span>🚦</span><span style={{ color: '#d97706', fontWeight: 600 }}>Moderate</span><span style={{ color: '#94a3b8' }}>1.2–2×</span></div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

function LegendRow({ color, label, box }) {
    return (
        <div className="legend-row">
            {box
                ? <span className="legend-swatch-box" style={{ background: color }} />
                : <span className="legend-swatch-line" style={{ background: color }} />}
            <span>{label}</span>
        </div>
    );
}
