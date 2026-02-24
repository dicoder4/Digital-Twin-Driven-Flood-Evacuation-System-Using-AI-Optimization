/**
 * SheltersPanel.jsx
 * ─────────────────
 * "Find Shelters" button above simulation controls.
 * Shows a count summary. List is collapsible (details/summary).
 *
 * Props:
 *   loadedHobli   string        — current hobli
 *   shelters      array|null    — precomputed [{...candidate, safe}] from App
 *   onCandidates  (arr)=>void   — called when raw candidates are fetched
 */
import { useState } from 'react';
import { ShieldCheck, Loader, MapPin, ChevronDown } from 'lucide-react';
import axios from 'axios';
import { API_URL } from '../config';

const TYPE_EMOJI = {
    school: '🏫', hospital: '🏥', community_centre: '🏛',
    townhall: '🏛', police: '👮', fire_station: '🚒', public: '🏢',
};
const TYPE_LABEL = {
    school: 'School', hospital: 'Hospital', community_centre: 'Community Centre',
    townhall: 'Town Hall', police: 'Police', fire_station: 'Fire Station', public: 'Public Bldg',
};

export function SheltersPanel({ loadedHobli, shelters, onCandidates }) {
    const [loading, setLoading] = useState(false);
    const [error, setError]     = useState('');

    const load = async () => {
        if (!loadedHobli) return;
        setLoading(true);
        setError('');
        try {
            const res = await axios.get(`${API_URL}/shelters/${encodeURIComponent(loadedHobli)}`);
            onCandidates(res.data.shelters);          // raw candidates → App
        } catch {
            setError('Could not fetch shelters. Ensure the region is loaded.');
        } finally {
            setLoading(false);
        }
    };

    const safeCount  = shelters?.filter(s => s.safe).length ?? 0;
    const totalCount = shelters?.length ?? 0;
    const hasSynth   = shelters?.some(s => s.synthetic);

    return (
        <section className="panel">
            <h3 className="panel-title"><ShieldCheck size={13} /> Evacuation Shelters</h3>

            <button
                className={`btn-primary${loading ? ' btn-disabled' : ''}`}
                onClick={load}
                disabled={loading}
            >
                {loading
                    ? <><Loader size={12} className="spin" /> Searching OSM…</>
                    : <><MapPin size={12} /> {shelters ? 'Refresh Shelters' : 'Find Shelters'}</>
                }
            </button>

            {error && <p className="pop-hint" style={{ color: '#dc2626' }}>{error}</p>}

            {shelters && (
                <>
                    {/* Summary — always visible */}
                    <div className="shelter-summary">
                        <span className="shelter-safe">{safeCount}</span>
                        <span className="shelter-muted">safe · {totalCount} total</span>
                    </div>

                    {hasSynth && (
                        <p className="pop-hint" style={{ color: '#d97706' }}>
                            ⚠ Approximate locations (no OSM match)
                        </p>
                    )}

                    {/* Collapsible list */}
                    <details className="shelter-details">
                        <summary className="shelter-details-summary">
                            <ChevronDown size={11} /> View shelter list
                        </summary>
                        <ul className="shelter-list">
                            {shelters.map(s => (
                                <li key={s.id}
                                    className={`shelter-item ${s.safe ? 'shelter-item-safe' : 'shelter-item-unsafe'}`}>
                                    <span className="shelter-icon">{TYPE_EMOJI[s.type] ?? '🏠'}</span>
                                    <div className="shelter-info">
                                        <div className="shelter-name">{s.name}</div>
                                        <div className="shelter-meta">
                                            {TYPE_LABEL[s.type] ?? s.type} · {s.capacity.toLocaleString()} cap
                                        </div>
                                    </div>
                                    <span className={`shelter-badge ${s.safe ? 'shelter-badge-safe' : 'shelter-badge-unsafe'}`}>
                                        {s.safe ? '✓ Safe' : '✗ Flooded'}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </details>
                </>
            )}
        </section>
    );
}
