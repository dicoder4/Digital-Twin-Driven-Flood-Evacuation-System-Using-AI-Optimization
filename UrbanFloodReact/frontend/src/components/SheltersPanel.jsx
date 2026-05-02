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
import { useState, useEffect } from 'react';
import { ShieldCheck, Loader, MapPin, ChevronDown } from 'lucide-react';
import axios from 'axios';
import { API_URL } from '../config';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';

const TYPE_EMOJI = {
    school: '🏫', hospital: '🏥', community_centre: '🏛',
    townhall: '🏛', police: '👮', fire_station: '🚒', public: '🏢',
};
const TYPE_LABEL = {
    school: 'School', hospital: 'Hospital', community_centre: 'Community Centre',
    townhall: 'Town Hall', police: 'Police', fire_station: 'Fire Station', public: 'Public Bldg',
};

export function SheltersPanel({ loadedHobli, shelters, onCandidates }) {
    const { lang } = useLanguage();
    const [loading, setLoading] = useState(false);
    const [error, setError]     = useState('');

    const load = async () => {
        if (!loadedHobli) return;
        setLoading(true);
        setError('');
        try {
            const res = await axios.get(`${API_URL}/shelters/${encodeURIComponent(loadedHobli)}`);
            onCandidates(res.data.shelters);
        } catch {
            setError(t('shelters_error', lang));
        } finally {
            setLoading(false);
        }
    };

    // Auto-fetch shelters when the region changes
    useEffect(() => {
        if (loadedHobli) {
            load();
        } else {
            onCandidates([]);
        }
    }, [loadedHobli]);

    const safeCount  = shelters?.filter(s => s.safe).length ?? 0;
    const totalCount = shelters?.length ?? 0;
    const hasSynth   = shelters?.some(s => s.synthetic);

    return (
        <section className="panel">
            <h3 className="panel-title"><ShieldCheck size={13} /> {t('evac_shelters', lang)}</h3>

            <button
                className={`btn-primary${loading ? ' btn-disabled' : ''}`}
                onClick={load}
                disabled={loading}
            >
                {loading
                    ? <><Loader size={12} className="spin" /> {t('searching_osm', lang)}</>
                    : <><MapPin size={12} /> {shelters ? t('refresh_shelters', lang) : t('find_shelters', lang)}</>
                }
            </button>

            {error && <p className="pop-hint" style={{ color: '#dc2626' }}>{error}</p>}

            {shelters && (
                <>
                    <div className="shelter-summary">
                        <span className="shelter-safe">{safeCount}</span>
                        <span className="shelter-muted">{t('shelter_safe', lang).replace('✓ ', '')} · {totalCount} {lang === 'en' ? 'total' : 'ಒಟ್ಟು'}</span>
                    </div>

                    {hasSynth && (
                        <p className="pop-hint" style={{ color: '#d97706' }}>
                            {t('approx_locations', lang)}
                        </p>
                    )}

                    <details className="shelter-details">
                        <summary className="shelter-details-summary">
                            <ChevronDown size={11} /> {t('view_shelter_list', lang)}
                        </summary>
                        <ul className="shelter-list">
                            {shelters.map(s => (
                                <li key={s.id}
                                    className={`shelter-item ${s.safe ? 'shelter-item-safe' : 'shelter-item-unsafe'}`}>
                                    <span className="shelter-icon">{TYPE_EMOJI[s.type] ?? '🏠'}</span>
                                    <div className="shelter-info">
                                        <div className="shelter-name">{s.name}</div>
                                        <div className="shelter-meta">
                                            {TYPE_LABEL[s.type] ?? s.type} · {s.capacity.toLocaleString()} {t('cap', lang)}
                                        </div>
                                    </div>
                                    <span className={`shelter-badge ${s.safe ? 'shelter-badge-safe' : 'shelter-badge-unsafe'}`}>
                                        {s.safe ? t('shelter_safe', lang) : t('shelter_flooded', lang)}
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
