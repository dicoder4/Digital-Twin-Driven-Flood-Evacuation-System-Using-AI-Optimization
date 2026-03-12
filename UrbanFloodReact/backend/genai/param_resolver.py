"""
param_resolver.py
─────────────────
Maps a hobli name (as typed by an operator) to:
  1.  Centroid coordinates  (lat, lon) sourced from HOBLI_COORDS
  2.  Valid rainfall range  [min_mm, max_mm] derived from historical IMD records

Design principle: Rainfall values fed into the simulation must always be
bounded by historically observed ranges for that hobli so that the simulation
stays physically realistic and scientifically defensible to authorities.

Usage:
    from genai.param_resolver import resolve_hobli

    info = resolve_hobli("Sarjapura")
    # {
    #   "key":        "sarjapura-1",
    #   "display":    "Sarjapura-1",
    #   "lat":        12.868447,
    #   "lon":        77.796854,
    #   "city_label": "Bengaluru, India",
    #   "rain_min":   35.0,
    #   "rain_max":   220.0,
    #   "rain_mean":  112.5,
    #   "rain_std":   38.2,
    #   "matches":    ["sarjapura-1", "sarjapura-2", "sarjapura-3"],
    # }
"""

from __future__ import annotations

import sys
import os
import statistics
from pathlib import Path
from typing import Optional

# ── Make backend root importable even when called standalone ──────────────────
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from coord_loader import norm_key
from region_manager import HOBLI_COORDS, RAINFALL_DATA


# ── Fallback rainfall bounds (IMD monsoon climatology for Bengaluru region) ───
# Used when historical Excel data has < 3 records for a hobli.
_BENGALURU_FALLBACK = {
    "rain_min":  35.0,
    "rain_max":  220.0,
    "rain_mean": 110.0,
    "rain_std":  42.0,
}

# Absolute safety cap — never pass more than this to the simulator
RAINFALL_HARD_CAP_MM = 300.0


def _compute_rain_stats(records: list[dict]) -> dict:
    """
    Given a list of rainfall records (each has 'actual_mm'), return
    {rain_min, rain_max, rain_mean, rain_std} clamped to [0, HARD_CAP].
    Falls back to Bengaluru climatology if fewer than 3 valid records.
    """
    values = [
        float(r["actual_mm"])
        for r in records
        if r.get("actual_mm") is not None and float(r.get("actual_mm", 0)) > 0
    ]

    if len(values) < 3:
        return dict(_BENGALURU_FALLBACK)

    rain_min  = max(0.0,  min(values))
    rain_max  = min(RAINFALL_HARD_CAP_MM, max(values))
    rain_mean = statistics.mean(values)
    rain_std  = statistics.stdev(values) if len(values) >= 2 else 0.0

    return {
        "rain_min":  round(rain_min,  1),
        "rain_max":  round(rain_max,  1),
        "rain_mean": round(rain_mean, 1),
        "rain_std":  round(rain_std,  1),
    }


def _fuzzy_match(query: str, all_keys: list[str]) -> list[str]:
    """
    Return hobli keys that contain the normalised query as a substring.
    For example: "sarjapura" → ["sarjapura-1", "sarjapura-2", "sarjapura-3"]

    IMPORTANT: numbered variants (e.g. "uttarahalli-1") are ALWAYS preferred
    over the bare key ("uttarahalli") because the bare key is often just a
    coordinate centroid placeholder while the numbered variants are the real
    hoblis with population and rainfall data.
    """
    import re
    q = norm_key(query)

    # Substring / prefix match — always collect ALL variants first
    matches = [k for k in all_keys if q in k or k.startswith(q)]

    if matches:
        # Separate numbered variants from the bare key
        numbered = sorted([k for k in matches if re.search(r'-\d+$', k)])
        bare     = [k for k in matches if not re.search(r'-\d+$', k)]

        # Prefer numbered variants: if any exist, put them first and drop the bare key
        # (the bare key is usually a centroid placeholder, not a real simulation region)
        if numbered:
            return numbered
        return bare  # no numbered variants → return bare key(s)

    # Partial token overlap fallback (e.g. "kr pura" → "k r pura-1")
    tokens = q.split()
    scored = []
    for k in all_keys:
        overlap = sum(1 for t in tokens if t in k)
        if overlap > 0:
            scored.append((overlap, k))
    scored.sort(key=lambda x: -x[0])
    return [k for _, k in scored[:5]]


def resolve_hobli(hobli_name: str) -> Optional[dict]:
    """
    Primary entry-point.  Returns a rich dict with coordinates, rainfall
    stats, and all fuzzy-matched hobli variants — or None if not found.

    Parameters
    ----------
    hobli_name : str
        Free-form hobli name as typed by the operator (e.g. "Sarjapura",
        "KR Pura", "Attibele").

    Returns
    -------
    dict | None
    """
    all_keys = list(HOBLI_COORDS.keys())
    matches  = _fuzzy_match(hobli_name, all_keys)

    if not matches:
        return None

    # Primary match: first (or only) candidate
    primary_key = matches[0]
    coords      = HOBLI_COORDS[primary_key]

    # Aggregate rainfall stats across ALL matched variants for robustness
    all_records: list[dict] = []
    for m in matches:
        all_records.extend(RAINFALL_DATA.get(m, []))

    rain_stats = _compute_rain_stats(all_records)

    # City label used by weather client for Open-Meteo geocoding
    district = coords.get("district", "Bengaluru")
    city_label = f"{coords.get('original_name', primary_key)}, {district}, India"

    return {
        "key":        primary_key,
        "display":    coords.get("original_name", primary_key),
        "lat":        coords["lat"],
        "lon":        coords["lon"],
        "district":   district,
        "city_label": city_label,
        "matches":    matches,
        **rain_stats,
    }


def clamp_rainfall(rainfall_mm: float, hobli_info: dict) -> float:
    """
    Clamp *rainfall_mm* to the physically valid range for this hobli.
    Always returns a value in [rain_min, rain_max].
    """
    lo = hobli_info.get("rain_min", _BENGALURU_FALLBACK["rain_min"])
    hi = hobli_info.get("rain_max", _BENGALURU_FALLBACK["rain_max"])
    return round(max(lo, min(hi, rainfall_mm)), 1)


def sample_historical(hobli_info: dict, rng=None) -> float:
    """
    Draw a rainfall sample from the hobli's historical distribution
    (Gaussian with mean ± std, clamped to valid range).

    Parameters
    ----------
    hobli_info : dict   Output of resolve_hobli()
    rng        : random.Random | None   Optional seeded RNG for reproducibility.
    """
    import random
    _rng = rng or random.Random()

    mean = hobli_info.get("rain_mean", _BENGALURU_FALLBACK["rain_mean"])
    std  = max(1.0, hobli_info.get("rain_std",  _BENGALURU_FALLBACK["rain_std"]))
    sample = _rng.gauss(mean, std)
    return clamp_rainfall(sample, hobli_info)
