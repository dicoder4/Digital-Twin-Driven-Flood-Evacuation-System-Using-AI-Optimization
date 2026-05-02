import { MapPin, ChevronDown, Loader, CheckCircle, CloudRain, ShieldAlert, Radio } from 'lucide-react';
import axios from 'axios';
import { useState } from 'react';
import { API_URL } from '../config';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';

export function DraSidebar({
    allHoblis,
    selHobli,
    onHobli,
    onLoad,
    loading,
    loaded,
    loadedHobli,
    rainfallMm,
    onRainfallChange,
    onRunEvacuation,
    simulationRunning,
    pinDropMode,
    onTogglePinDrop,
    pinResolvedHobli,
    onRunPinSimulation
}) {
    const { lang } = useLanguage();
    const canLoad = !!selHobli && !loading;
    const [fetchingWeather, setFetchingWeather] = useState(false);
    const [weatherCondition, setWeatherCondition] = useState('');

    const handleFetchWeather = async () => {
        if (!selHobli) return;
        setFetchingWeather(true);
        try {
            const res = await axios.get(`${API_URL}/weather/current`, { params: { hobli: selHobli } });
            if (res.data.error) {
                alert(res.data.error);
            } else {
                onRainfallChange(res.data.rainfall_mm || 0);
                if (res.data.condition) {
                    setWeatherCondition(`${res.data.condition}, ${res.data.temp_c}°C`);
                }
            }
        } catch (err) {
            alert(`Failed to fetch weather: ${err.message}`);
        } finally {
            setFetchingWeather(false);
        }
    };

    return (
        <div className="sidebar-content custom-scrollbar" style={{ paddingTop: '1rem' }}>
            <div className="status-bar" style={{ position: 'relative', marginTop: 0, marginBottom: '1.5rem', backgroundColor: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca', justifyContent: 'center' }}>
                <ShieldAlert size={14} />
                <span style={{ fontWeight: 600 }}>{t('dra_mode', lang)}</span>
            </div>

            <section className="panel">
                <h3 className="panel-title"><MapPin size={13} /> {t('select_target_region', lang)}</h3>
                <label className="field-label">{t('hobli_subdistrict', lang)}</label>
                <div className="select-wrap">
                    <select value={selHobli} onChange={e => onHobli(e.target.value)} className="styled-select">
                        <option value="">{t('select_hobli', lang)}</option>
                        {allHoblis.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                    <ChevronDown size={13} className="select-arrow" />
                </div>

                <button className={`btn-primary ${!canLoad ? 'btn-disabled' : ''}`} onClick={onLoad} disabled={!canLoad} style={{ marginTop: '1rem' }}>
                    {loading
                        ? <><Loader size={13} className="spin" /> {t('loading_network', lang)}</>
                        : loaded && loadedHobli === selHobli
                            ? <><CheckCircle size={13} /> {t('network_ready', lang)}</>
                            : <><MapPin size={13} /> {t('initialise_network', lang)}</>}
                </button>
            </section>

            {(!loaded || loadedHobli !== selHobli) && (
                <section className="panel" style={{ borderLeft: '3px solid #f97316', marginTop: '1rem' }}>
                    <h3 className="panel-title" style={{ color: '#c2410c' }}><MapPin size={13} /> {t('pin_drop_sim', lang)}</h3>
                    <p style={{ fontSize: '11px', color: '#64748b', marginBottom: '10px' }}>
                        {t('pin_drop_desc', lang)}
                    </p>
                    <button
                        className="btn-secondary"
                        onClick={onTogglePinDrop}
                        style={{
                            width: '100%',
                            display: 'flex',
                            justifyContent: 'center',
                            gap: '6px',
                            background: pinDropMode ? '#fff7ed' : '',
                            borderColor: pinDropMode ? '#f97316' : '',
                            color: pinDropMode ? '#c2410c' : ''
                        }}
                    >
                        <MapPin size={13} />
                        {pinDropMode ? t('cancel_pin', lang) : t('drop_pin', lang)}
                    </button>

                    {pinResolvedHobli && (
                        <div style={{ marginTop: '12px', padding: '10px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                            {pinResolvedHobli.loading ? (
                                <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <Loader size={12} className="spin" /> {t('resolving_location', lang)}
                                </div>
                            ) : pinResolvedHobli.error ? (
                                <div style={{ fontSize: '12px', color: '#dc2626' }}>{pinResolvedHobli.error}</div>
                            ) : (
                                <>
                                    <div style={{ fontSize: '10px', textTransform: 'uppercase', color: '#94a3b8', fontWeight: 600, marginBottom: '4px' }}>{t('resolved_location', lang)}</div>
                                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
                                        {pinResolvedHobli.hobli_name}
                                    </div>
                                    <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                                        {pinResolvedHobli.distance_km} {t('km_away', lang)}
                                    </div>
                                    <button
                                        className="btn-primary"
                                        onClick={onRunPinSimulation}
                                        disabled={simulationRunning}
                                        style={{ width: '100%', marginTop: '10px', backgroundColor: '#f97316', borderColor: '#ea580c' }}
                                    >
                                        {simulationRunning ? <><Loader size={13} className="spin" /> {t('initialising', lang)}</> : <><Radio size={13} /> {t('run_here', lang)}</>}
                                    </button>
                                </>
                            )}
                        </div>
                    )}
                </section>
            )}

            {loaded && loadedHobli === selHobli && !pinDropMode && (
                <>
                    <section className="panel">
                        <h3 className="panel-title"><CloudRain size={13} /> {t('rainfall_params', lang)}</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                            <div>
                                <label className="field-label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                                    <span>{t('rainfall_severity', lang)}</span>
                                    <span style={{ fontWeight: 600, color: '#2563eb' }}>{rainfallMm} mm</span>
                                </label>
                                <input
                                    type="range"
                                    min="0"
                                    max="300"
                                    step="5"
                                    value={rainfallMm}
                                    onChange={(e) => {
                                        onRainfallChange(Number(e.target.value));
                                        setWeatherCondition('');
                                    }}
                                    className="styled-slider"
                                />
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
                                    <span>0 mm</span><span>{t('severe_label', lang)}</span>
                                </div>
                            </div>

                            <button
                                className="btn-secondary"
                                onClick={handleFetchWeather}
                                disabled={fetchingWeather}
                                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                            >
                                {fetchingWeather ? <Loader size={13} className="spin" /> : <CloudRain size={13} />}
                                {fetchingWeather ? t('fetching_openmeteo', lang) : t('fetch_weather', lang)}
                            </button>

                            {weatherCondition && (
                                <div style={{ fontSize: '12px', color: '#047857', backgroundColor: '#ecfdf5', padding: '8px', borderRadius: '4px', textAlign: 'center', border: '1px solid #10b981' }}>
                                    ✓ {lang === 'en' ? 'Live Data Applied:' : 'ಲೈವ್ ಡೇಟಾ ಅನ್ವಯಿಸಲಾಗಿದೆ:'} <strong>{weatherCondition}</strong>
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="panel" style={{ borderLeft: '3px solid #16a34a' }}>
                        <h3 className="panel-title"><ShieldAlert size={13} /> {t('exec_commander', lang)}</h3>
                        <div style={{ fontSize: '12px', color: '#475569', marginBottom: '1rem', lineHeight: 1.5 }}>
                            <strong>{t('configured_protocols', lang)}</strong>
                            <ul style={{ paddingLeft: '1.2rem', marginTop: '4px' }}>
                                <li>{t('protocol_algo', lang)}</li>
                                <li>{t('protocol_traffic', lang)}</li>
                                <li>{t('protocol_population', lang)}</li>
                            </ul>
                        </div>

                        <button
                            className="btn-primary"
                            onClick={onRunEvacuation}
                            disabled={simulationRunning}
                            style={{ width: '100%', backgroundColor: '#dc2626', borderColor: '#b91c1c', paddingTop: '10px', paddingBottom: '10px' }}
                        >
                            {simulationRunning ? (
                                <><Loader size={13} className="spin" /> {t('calculating_routes', lang)}</>
                            ) : (
                                <><Radio size={13} /> {t('run_evac_protocol', lang)}</>
                            )}
                        </button>
                    </section>
                </>
            )}
        </div>
    );
}
