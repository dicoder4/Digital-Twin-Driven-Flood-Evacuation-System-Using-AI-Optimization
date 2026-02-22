"""
generate_people.py
──────────────────
Loads BBMP ward-level population data from a CSV and maps it to hoblis.

Matching strategy (two-pass):
  PASS 1 — Direct hobli match:
    Normalize the hobli display name and compare against every ward name
    in the CSV. If a ward name contains the hobli name (or vice versa),
    that ward's population is assigned directly to this hobli.
    e.g. hobli "Marathahalli" → ward "Marathahalli" (row 86)   ✓

  PASS 2 — Taluk aggregation fallback:
    For hoblis that had no direct match, group all wards by their
    Assembly Constituency → derive a taluk bucket → sum populations
    → divide evenly across all hoblis in that taluk that are still unmatched.

Public API:
  load_population(csv_path, regions_tree, norm_key_fn) → populates POPULATION_STORE
  get_population(hobli_key: str) → dict | None
"""

from pathlib import Path
import re
import pandas as pd
from collections import defaultdict

# ── Path constant — imported by main.py ────────────────────────────────────────
POPULATION_CSV = Path(__file__).parent / "data" / "269cdf01-dae5-4736-8f4d-72a8e57fa3a9.csv"

# ── Constituency display name → Taluk name (as it appears in REGIONS_TREE) ──────
# Used only in Pass 2 (fallback for hoblis with no direct ward match).
# Taluk names must match exactly what REGIONS_TREE contains.
CONSTITUENCY_TO_TALUK: dict[str, str] = {
    "YELAHANKA":                "Yelahanka",
    "BYATARAYANAPURA":          "Yelahanka",
    "DASARAHALLI":              "Bengaluru North",
    "RAJARAJESHWARI NAGAR":     "Bengaluru South",
    "HEBBAL":                   "Yelahanka",
    "SARVARGNA NAGAR":          "Bengaluru East",
    "K.R.PURA":                 "Bengaluru East",
    "PULAKESHI NAGAR (SC)":     "Bengaluru East",
    "C.V. RAMAN NAGAR (SC)":    "Bengaluru East",
    "SHIVAJI NAGAR":            "Bengaluru East",
    "SHANTI NAGAR":             "Bengaluru East",
    "MALLESWARAM":              "Bengaluru North",
    "RAJAJI NAGAR":             "Bengaluru North",
    "YESHVANTHAPURA":           "Bengaluru North",
    "GOVINDRAJA NAGAR":         "Bengaluru South",
    "VIJAYA NAGAR":             "Bengaluru South",
    "MAHALAXMI LAYOUT":         "Bengaluru South",
    "CHAMARAJPET":              "Bengaluru South",
    "CHICKPET":                 "Bengaluru South",
    "GANDHI NAGAR":             "Bengaluru South",
    "B.T.M. LAYOUT":            "Bengaluru South",
    "BOMMANAHALLI":             "Bengaluru South",
    "BASAVANAGUDI":             "Bengaluru South",
    "PADMANABA NAGAR":          "Bengaluru South",
    "JAYANAGAR":                "Bengaluru South",
    "MAHADEVAPURA (SC)":        "Bengaluru East",
    "BANGALORE SOUTH":          "Bengaluru South",
    "ANEKAL (SC)":              "Anekal",
}

# ── Module-level store ──────────────────────────────────────────────────────────
# norm_key → {total, male, female, matched_wards, source}
POPULATION_STORE: dict = {}


def load_population(csv_path: Path, regions_tree: dict, norm_key_fn) -> None:
    """
    Parse the BBMP ward CSV, do a two-pass match, populate POPULATION_STORE.
    """
    POPULATION_STORE.clear()

    if not csv_path.exists():
        print(f"  [population] CSV not found: {csv_path}")
        return

    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip() for c in df.columns]
        print(f"  [population] Loaded {len(df)} wards from {csv_path.name}")
    except Exception as e:
        print(f"  [population] ERROR reading CSV: {e}")
        return

    # Identify columns
    col_ward = next((c for c in df.columns if "ward" in c.lower() and "name" in c.lower()), None)
    col_pop  = next((c for c in df.columns if c.strip().lower() == "population"), None)
    col_male = next((c for c in df.columns if c.strip().lower() == "male"), None)
    col_fem  = next((c for c in df.columns if c.strip().lower() == "female"), None)
    col_cons = next((c for c in df.columns if "assembly" in c.lower() or "constituency" in c.lower()), None)

    if not all([col_ward, col_pop]):
        print(f"  [population] ERROR — required columns missing. Got: {list(df.columns)}")
        return

    # Pre-build normalised ward lookup: norm_ward_name → row dict
    ward_rows = []
    for _, row in df.iterrows():
        ward_name = str(row[col_ward]).strip()
        ward_rows.append({
            "name":   ward_name,
            "norm":   _norm_name(ward_name),
            "total":  _safe_int(row.get(col_pop, 0)),
            "male":   _safe_int(row.get(col_male, 0)) if col_male else 0,
            "female": _safe_int(row.get(col_fem,  0)) if col_fem  else 0,
            "cons":   str(row.get(col_cons, "")).strip() if col_cons else "",
        })

    # Collect all hobli display names from the tree
    all_hoblis: list[tuple[str, str, str]] = []   # (display, norm_key, taluk)
    for district_data in regions_tree.values():
        for taluk, hobli_list in district_data.items():
            for h in hobli_list:
                all_hoblis.append((h, norm_key_fn(h), taluk))

    # ── PASS 1: Direct hobli name → ward name match ───────────────────────────
    matched_directly = 0
    unmatched_hoblis = []

    for (display, key, taluk) in all_hoblis:
        hobli_norm = _norm_name(display)
        best = _find_best_ward_match(hobli_norm, ward_rows)
        if best:
            POPULATION_STORE[key] = {
                "total":         best["total"],
                "male":          best["male"],
                "female":        best["female"],
                "matched_wards": [{"name": best["name"], "population": best["total"]}],
                "taluk":         taluk,
                "hobli":         display,
                "source":        "direct",
            }
            matched_directly += 1
        else:
            unmatched_hoblis.append((display, key, taluk))

    print(f"  [population] Pass 1: {matched_directly} hoblis matched directly")

    # ── PASS 2: Taluk aggregation for unmatched hoblis ─────────────────────────
    if not unmatched_hoblis:
        print(f"  [population] Pass 2: all hoblis matched in Pass 1, skipping")
        return

    # Build taluk buckets from CSV
    taluk_buckets: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "male": 0, "female": 0, "wards": []
    })
    for wr in ward_rows:
        raw_cons  = wr["cons"]
        cons_name = raw_cons.split("-", 1)[-1].strip() if "-" in raw_cons else raw_cons
        taluk     = _find_taluk(cons_name)
        if not taluk:
            continue
        taluk_buckets[taluk]["total"]  += wr["total"]
        taluk_buckets[taluk]["male"]   += wr["male"]
        taluk_buckets[taluk]["female"] += wr["female"]
        taluk_buckets[taluk]["wards"].append({"name": wr["name"], "population": wr["total"]})

    # Count how many unmatched hoblis are in each taluk
    taluk_unmatched_count: dict[str, int] = defaultdict(int)
    for (_, _, taluk) in unmatched_hoblis:
        taluk_unmatched_count[taluk] += 1

    matched_fallback = 0
    for (display, key, taluk) in unmatched_hoblis:
        bucket = taluk_buckets.get(taluk)
        if not bucket:
            continue  # No CSV data for this taluk either
        n = max(taluk_unmatched_count[taluk], 1)
        POPULATION_STORE[key] = {
            "total":         bucket["total"] // n,
            "male":          bucket["male"]  // n,
            "female":        bucket["female"] // n,
            "matched_wards": bucket["wards"],
            "taluk":         taluk,
            "hobli":         display,
            "source":        "taluk_fallback",
        }
        matched_fallback += 1

    print(f"  [population] Pass 2: {matched_fallback} hoblis matched via taluk fallback")
    print(f"  [population] Total: {len(POPULATION_STORE)} / {len(all_hoblis)} hoblis populated")


def get_population(hobli_key: str) -> dict | None:
    """Return population dict or None if no mapping was found."""
    return POPULATION_STORE.get(hobli_key)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    """Lowercase, remove punctuation, collapse spaces for fuzzy comparison."""
    n = name.lower().strip()
    n = re.sub(r"[^a-z0-9\s]", " ", n)   # drop punctuation
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _find_best_ward_match(hobli_norm: str, ward_rows: list) -> dict | None:
    """
    Return the best matching ward row for this hobli norm name, or None.
    Match rules (in priority):
      1. Exact normalised match
      2. Hobli norm is contained in ward norm (e.g. "marathahalli" in "marathahalli")
      3. Ward norm is contained in hobli norm
    """
    for ward in ward_rows:
        wn = ward["norm"]
        if hobli_norm == wn:
            return ward
    for ward in ward_rows:
        wn = ward["norm"]
        if hobli_norm in wn or wn in hobli_norm:
            # Avoid very short accidental matches (minimum 5 chars)
            overlap = min(len(hobli_norm), len(wn))
            if overlap >= 5:
                return ward
    return None


def _find_taluk(cons_name: str) -> str | None:
    """Case-insensitive lookup of constituency → taluk (Pass 2 fallback)."""
    upper = cons_name.upper().strip()
    for key, taluk in CONSTITUENCY_TO_TALUK.items():
        if key.upper() == upper:
            return taluk
    for key, taluk in CONSTITUENCY_TO_TALUK.items():
        if key.upper() in upper or upper in key.upper():
            return taluk
    return None


def _safe_int(val) -> int:
    try:
        return int(float(str(val).replace(",", "").strip()))
    except Exception:
        return 0
