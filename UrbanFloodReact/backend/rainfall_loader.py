"""
rainfall_loader.py
──────────────────
Loads May / June / July rainfall Excel files into a shared in-memory store.
Expected columns (case-insensitive):
  Date, District, Taluk, Hobli, 24h_Normal_mm, 24h_Actual_mm, 24h_Dep_Pct
"""

from pathlib import Path
import pandas as pd


# File map — only files that exist will be loaded
RAINFALL_FILES = {
    "May":  "Bengaluru_Rainfall_24Hrs_May.xlsx",
    "June": "Bengaluru_Rainfall_24Hrs_June.xlsx",
    "July": "Bengaluru_Rainfall_24Hrs_July.xlsx",
}


def load_rainfall_excels(data_dir: Path, norm_key_fn, rainfall_store: dict):
    """
    Load all available rainfall Excel files and populate `rainfall_store`.
    rainfall_store: dict  norm_key → list[{date, actual_mm, normal_mm, dep_pct, district, taluk, month}]
    """
    frames = []
    for month, fname in RAINFALL_FILES.items():
        path = data_dir / fname
        if not path.exists():
            print(f"  [rainfall] File not found, skipping: {fname}")
            continue
        try:
            df = pd.read_excel(path)
            df.columns = [c.strip() for c in df.columns]
            df["_month"] = month
            frames.append(df)
            print(f"  [rainfall] Loaded {len(df)} rows from {fname}")
        except Exception as e:
            print(f"  [rainfall] Could not load {fname}: {e}")

    if not frames:
        print("  [rainfall] No Excel files loaded.")
        return

    combined = pd.concat(frames, ignore_index=True)

    # Flexible column detection
    col_map = {}
    for col in combined.columns:
        cl = col.lower().replace(" ", "_").replace("-", "_")
        if cl == "date":                          col_map["date"]      = col
        if cl == "district":                      col_map["district"]  = col
        if cl == "taluk":                         col_map["taluk"]     = col
        if cl == "hobli":                         col_map["hobli"]     = col
        if "normal" in cl and "mm" in cl:         col_map["normal_mm"] = col
        if "actual" in cl and "mm" in cl:         col_map["actual_mm"] = col
        if "dep" in cl and any(x in cl for x in ("pct", "percent", "%")):
            col_map["dep_pct"] = col

    required = {"date", "hobli", "actual_mm"}
    missing  = required - set(col_map.keys())
    if missing:
        print(f"  [rainfall] ERROR — required columns not found: {missing}")
        print(f"             Available: {combined.columns.tolist()}")
        return

    for _, row in combined.iterrows():
        raw_hobli = str(row[col_map["hobli"]]).strip()
        key       = norm_key_fn(raw_hobli)

        raw_date  = str(row[col_map["date"]]).strip()
        try:
            parsed   = pd.to_datetime(raw_date, dayfirst=True)
            date_str = parsed.strftime("%d-%m-%Y")
        except Exception:
            date_str = raw_date

        def _float(field):
            try:    return float(row[col_map[field]]) if field in col_map else None
            except: return None

        def _str(field):
            try:    return str(row[col_map[field]]).strip() if field in col_map else ""
            except: return ""

        entry = {
            "date":       date_str,
            "actual_mm":  _float("actual_mm") or 0.0,
            "normal_mm":  _float("normal_mm"),
            "dep_pct":    _float("dep_pct"),
            "district":   _str("district"),
            "taluk":      _str("taluk"),
            "month":      row.get("_month", ""),
        }
        rainfall_store.setdefault(key, []).append(entry)

    print(f"  [rainfall] Data ready for {len(rainfall_store)} unique hoblis.")
