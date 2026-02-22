/**
 * RegionSelector.jsx
 * Cascading District → Taluk → Hobli dropdowns + Load Region button.
 */
import { MapPin, ChevronDown, Loader, CheckCircle } from 'lucide-react';

export function RegionSelector({
    districts, taluks, hoblis,
    selDistrict, selTaluk, selHobli,
    onDistrict, onTaluk, onHobli,
    onLoad, loading, loaded, loadedHobli,
}) {
    const canLoad = !!selHobli && !loading;

    return (
        <section className="panel">
            <h3 className="panel-title"><MapPin size={13} /> Select Region</h3>

            <label className="field-label">District</label>
            <div className="select-wrap">
                <select value={selDistrict} onChange={e => onDistrict(e.target.value)} className="styled-select">
                    <option value="">— District —</option>
                    {districts.map(d => <option key={d} value={d}>{d}</option>)}
                </select>
                <ChevronDown size={13} className="select-arrow" />
            </div>

            <label className="field-label">Taluk</label>
            <div className="select-wrap">
                <select value={selTaluk} onChange={e => onTaluk(e.target.value)} disabled={!selDistrict} className="styled-select">
                    <option value="">— Taluk —</option>
                    {taluks.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <ChevronDown size={13} className="select-arrow" />
            </div>

            <label className="field-label">Hobli</label>
            <div className="select-wrap">
                <select value={selHobli} onChange={e => onHobli(e.target.value)} disabled={!selTaluk} className="styled-select">
                    <option value="">— Hobli —</option>
                    {hoblis.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
                <ChevronDown size={13} className="select-arrow" />
            </div>

            <button className={`btn-primary ${!canLoad ? 'btn-disabled' : ''}`} onClick={onLoad} disabled={!canLoad}>
                {loading
                    ? <><Loader size={13} className="spin" /> Loading…</>
                    : loaded && loadedHobli === selHobli
                        ? <><CheckCircle size={13} /> Reload Region</>
                        : <><MapPin size={13} /> Load Region</>}
            </button>

            {loaded && (
                <p className="loaded-badge"><CheckCircle size={11} /> {loadedHobli}</p>
            )}
        </section>
    );
}
