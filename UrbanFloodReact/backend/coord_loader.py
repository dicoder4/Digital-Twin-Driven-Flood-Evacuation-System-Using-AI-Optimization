"""
coord_loader.py
───────────────
Pure-function module for loading hobli coordinate JSON files.
Each JSON is an array of {hobli_name, latitude, longitude}.
Multiple rows per hobli_name are averaged (centroid).
"""

import json
from collections import defaultdict
from pathlib import Path


def norm_key(name: str) -> str:
    """Normalise a hobli name to a stable lookup key.
    Lowercases and unifies dash / underscore separators.
    e.g. 'Sarjapura-1' and 'Sarjapura_1' both → 'sarjapura-1'
    """
    return name.strip().lower().replace("_", "-")


def load_coords_from_json(path: Path, district: str) -> dict:
    """
    Returns: dict  norm_key → {lat, lon, original_name, district, num_points}
    """
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    buckets: dict[str, list] = defaultdict(list)
    names_map: dict[str, str] = {}

    for r in records:
        raw = r["hobli_name"]
        key = norm_key(raw)
        buckets[key].append((r["latitude"], r["longitude"]))
        names_map[key] = raw  # last write wins for display name

    result = {}
    for key, coords in buckets.items():
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        n = len(coords)
        if n > 1:
            print(f"  [coords] '{names_map[key]}' has {n} points → centroid used")
        result[key] = {
            "lat":           round(sum(lats) / n, 6),
            "lon":           round(sum(lons) / n, 6),
            "original_name": names_map[key],
            "district":      district,
            "num_points":    n,
        }

    return result
