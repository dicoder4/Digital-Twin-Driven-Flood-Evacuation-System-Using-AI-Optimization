/**
 * RegionSelector.jsx
 * Cascading District → Taluk → Hobli dropdowns + Load Region button.
 */
import { MapPin, ChevronDown, Loader, CheckCircle } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import { t } from '../translations';

const toDisplayName = (str) =>
    str.replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

export function RegionSelector({
    districts, taluks, hoblis,
    selDistrict, selTaluk, selHobli,
    onDistrict, onTaluk, onHobli,
    onLoad, loading, loaded, loadedHobli,
}) {
    const { lang } = useLanguage();
    const canLoad = !!selHobli && !loading;

    return (
        <section className="panel">
            <h3 className="panel-title"><MapPin size={13} /> {t('select_region', lang)}</h3>

            <label className="field-label">{t('district', lang)}</label>
            <div className="select-wrap">
                <select value={selDistrict} onChange={e => onDistrict(e.target.value)} className="styled-select">
                    <option value="">{t('district_placeholder', lang)}</option>
                    {districts.map(d => <option key={d} value={d}>{toDisplayName(d)}</option>)}
                </select>
                <ChevronDown size={13} className="select-arrow" />
            </div>

            <label className="field-label">{t('taluk', lang)}</label>
            <div className="select-wrap">
                <select value={selTaluk} onChange={e => onTaluk(e.target.value)} disabled={!selDistrict} className="styled-select">
                    <option value="">{t('taluk_placeholder', lang)}</option>
                    {taluks.map(tk => <option key={tk} value={tk}>{toDisplayName(tk)}</option>)}
                </select>
                <ChevronDown size={13} className="select-arrow" />
            </div>

            <label className="field-label">{t('hobli', lang)}</label>
            <div className="select-wrap">
                <select value={selHobli} onChange={e => onHobli(e.target.value)} disabled={!selTaluk} className="styled-select">
                    <option value="">{t('hobli_placeholder', lang)}</option>
                    {hoblis.map(h => <option key={h} value={h}>{toDisplayName(h)}</option>)}
                </select>
                <ChevronDown size={13} className="select-arrow" />
            </div>

            <button className={`btn-primary ${!canLoad ? 'btn-disabled' : ''}`} onClick={onLoad} disabled={!canLoad}>
                {loading
                    ? <><Loader size={13} className="spin" /> {t('loading', lang)}</>
                    : loaded && loadedHobli === selHobli
                        ? <><CheckCircle size={13} /> {t('reload_region', lang)}</>
                        : <><MapPin size={13} /> {t('load_region', lang)}</>}
            </button>

            {loaded && (
                <p className="loaded-badge"><CheckCircle size={11} /> {loadedHobli}</p>
            )}
        </section>
    );
}
