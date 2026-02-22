/**
 * RiskBadge.jsx
 * Shows a coloured badge based on 24h_Dep_Pct departure percentage.
 */
export function RiskBadge({ depPct }) {
    if (depPct === null || depPct === undefined) return null;
    const val = Number(depPct);
    if (val > 100) return <span className="badge badge-extreme">⚠ Extreme Excess (+{val.toFixed(0)}%)</span>;
    if (val > 0) return <span className="badge badge-high">↑ Above Normal (+{val.toFixed(0)}%)</span>;
    if (val > -30) return <span className="badge badge-normal">✓ Near Normal ({val.toFixed(0)}%)</span>;
    return <span className="badge badge-low">↓ Deficit ({val.toFixed(0)}%)</span>;
}
