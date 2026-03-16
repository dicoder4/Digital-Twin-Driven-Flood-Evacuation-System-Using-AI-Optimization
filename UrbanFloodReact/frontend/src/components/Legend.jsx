/**
 * Legend.jsx
 * Floating map legend: road risk + flood depth categories.
 * Shown only when a simulation has data.
 */
export function Legend({ visible, showTraffic }) {
    if (!visible && !showTraffic) return null;

    return (
        <div className="legend">
            {visible && (
                <>
                    <p className="legend-title">Flood Depth</p>

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
