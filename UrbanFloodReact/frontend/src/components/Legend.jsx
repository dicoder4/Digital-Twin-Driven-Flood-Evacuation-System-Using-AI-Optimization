/**
 * Legend.jsx
 * Floating map legend: road risk + flood depth categories.
 * Shown only when a simulation has data.
 */
export function Legend({ visible }) {
    if (!visible) return null;

    return (
        <div className="legend">
            <p className="legend-title">Flood Depth</p>

            <p className="legend-section">ROAD RISK</p>
            <LegendRow color="#22c55e" label="Low (< 5 cm)" />
            <LegendRow color="#f59e0b" label="Medium (5–15 cm)" />
            <LegendRow color="#ef4444" label="High (> 15 cm)" />

            <p className="legend-section" style={{ marginTop: 8 }}>FLOOD AREA</p>
            <LegendRow color="rgba(56,189,248,0.4)" label="Shallow (< 5 cm)" box />
            <LegendRow color="rgba(14,165,233,0.6)" label="Moderate (5–15 cm)" box />
            <LegendRow color="rgba(2,132,199,0.8)" label="Deep (> 15 cm)" box />
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
