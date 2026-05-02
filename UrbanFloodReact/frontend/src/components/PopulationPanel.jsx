/**
 * PopulationPanel.jsx
 * ──────────────────
 * Shows CSV-matched population for the loaded hobli.
 * Always exposes a manual override input — used as fallback
 * when CSV data is not available for a given hobli.
 *
 * Props:
 *   loadedHobli      string          — currently loaded hobli name
 *   onPopulationSet  (count) => void — called when the active population changes
 */
import { useState, useEffect } from 'react';
import { Users, Info, Edit3, CheckCircle, AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { API_URL } from '../config';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';

export function PopulationPanel({ loadedHobli, onPopulationSet }) {
    const { lang } = useLanguage();
    const [popData, setPopData]       = useState(null);   // API response
    const [loading, setLoading]       = useState(false);
    const [override, setOverride]     = useState('');     // manual text value
    const [useOverride, setUseOverride] = useState(false);

    // Fetch population from backend whenever hobli changes
    useEffect(() => {
        if (!loadedHobli) return;
        setLoading(true);
        setPopData(null);
        setUseOverride(false);
        setOverride('');

        axios.get(`${API_URL}/population/${encodeURIComponent(loadedHobli)}`)
            .then(res => {
                setPopData(res.data);
                if (res.data.source === 'csv' && res.data.total_population > 0) {
                    onPopulationSet(res.data.total_population);
                    setUseOverride(false);
                } else {
                    // No match → auto-apply a sensible default of 5000 people
                    setUseOverride(true);
                    setOverride('5000');
                    onPopulationSet(5000);
                }
            })
            .catch(() => {
                setUseOverride(true);
                setOverride('5000');
                onPopulationSet(5000);
            })
            .finally(() => setLoading(false));
    }, [loadedHobli]);

    const applyOverride = () => {
        const n = parseInt(override, 10);
        if (!isNaN(n) && n >= 0) {
            onPopulationSet(n);
            setUseOverride(true);
        }
    };

    const revertToCSV = () => {
        if (popData?.source === 'csv') {
            onPopulationSet(popData.total_population);
            setUseOverride(false);
            setOverride('');
        }
    };

    const activeCount = useOverride
        ? (parseInt(override, 10) || 0)
        : (popData?.total_population || 0);

    const hasCSV = popData?.source === 'csv' && popData.total_population > 0;

    return (
        <section className="panel">
            <h3 className="panel-title">
                <Users size={13} /> {t('population', lang)}
            </h3>

            {loading && <p className="pop-hint">{t('loading_population', lang)}</p>}

            {!loading && popData && (
                <>
                    {hasCSV && !useOverride ? (
                        <div className="pop-source-badge pop-source-csv">
                            <CheckCircle size={11} /> {t('bbmp_census', lang)}
                        </div>
                    ) : (
                        <div className="pop-source-badge pop-source-manual">
                            <AlertTriangle size={11} />
                            {hasCSV ? t('manual_override', lang) : t('no_csv_match', lang)}
                        </div>
                    )}

                    <div className="pop-count-row">
                        <span className="pop-count">{activeCount.toLocaleString()}</span>
                        <span className="pop-count-label">{t('people', lang)}</span>
                    </div>

                    {hasCSV && (
                        <div className="pop-split">
                            <span>♂ {popData.male.toLocaleString()}</span>
                            <span>♀ {popData.female.toLocaleString()}</span>
                        </div>
                    )}

                    {hasCSV && popData.matched_wards?.length > 0 && (
                        <details className="pop-wards">
                            <summary className="pop-wards-summary">
                                <Info size={11} /> {popData.matched_wards.length} {t('source_wards', lang)}
                            </summary>
                            <ul className="pop-wards-list">
                                {popData.matched_wards.slice(0, 8).map((w, i) => (
                                    <li key={i}>{w.name} — {w.population?.toLocaleString()}</li>
                                ))}
                                {popData.matched_wards.length > 8 && (
                                    <li>…{lang === 'en' ? `and ${popData.matched_wards.length - 8} more` : `ಮತ್ತು ${popData.matched_wards.length - 8} ಹೆಚ್ಚು`}</li>
                                )}
                            </ul>
                        </details>
                    )}
                </>
            )}

            {!loading && (
                <div className="pop-override">
                    <label className="field-label">
                        <Edit3 size={11} /> {t('manual_override_label', lang)}
                    </label>
                    <div className="pop-override-row">
                        <input
                            type="number"
                            min="0"
                            className="pop-input"
                            placeholder={t('pop_placeholder', lang)}
                            value={override}
                            onChange={e => setOverride(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && applyOverride()}
                        />
                        <button className="btn-sm" onClick={applyOverride}>{t('set', lang)}</button>
                    </div>
                    {hasCSV && useOverride && (
                        <button className="btn-link" onClick={revertToCSV}>
                            ↩ {t('revert_csv', lang)} ({popData.total_population.toLocaleString()})
                        </button>
                    )}
                </div>
            )}
        </section>
    );
}
