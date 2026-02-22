/**
 * PeopleLayer.jsx
 * ───────────────
 * Renders people as small colored dots on road edges using react-map-gl Source/Layer.
 * People are distributed along road edge midpoints (not purely random —
 * seeded by hobli name for determinism). Dot color reflects flood risk as
 * the simulation progresses:
 *   safe      → green  (#22c55e)
 *   at-risk   → orange (#f59e0b)
 *   flooded   → red    (#ef4444)
 *
 * Props:
 *   baseRoadsData    GeoJSON FeatureCollection of road edges
 *   populationCount  number of people to place
 *   riskRoadsData    GeoJSON of flooded risk edges (from simulation)
 *   hobliName        string — used as deterministic seed
 */
import { useMemo, useEffect } from 'react';
import { Source, Layer } from 'react-map-gl/maplibre';

// Simple seeded pseudo-random (mulberry32)
function makeRng(seed) {
    let s = seed | 0;
    return () => {
        s = Math.imul(s ^ (s >>> 15), s | 1);
        s ^= s + Math.imul(s ^ (s >>> 7), s | 61);
        return ((s ^ (s >>> 14)) >>> 0) / 4294967296;
    };
}

// String → integer seed
function strToSeed(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return h >>> 0;
}

// Collect midpoints of all road line segments
function collectMidpoints(geojson) {
    if (!geojson?.features) return [];
    const pts = [];
    for (const feat of geojson.features) {
        const coords = feat.geometry?.coordinates;
        if (!coords || coords.length < 2) continue;
        // Use midpoint of each segment
        for (let i = 0; i < coords.length - 1; i++) {
            const [x1, y1] = coords[i];
            const [x2, y2] = coords[i + 1];
            pts.push([(x1 + x2) / 2, (y1 + y2) / 2]);
        }
    }
    return pts;
}

// Build a Set of flooded edge midpoints for fast lookup (rounded)
function buildFloodedSet(riskData) {
    const s = new Set();
    if (!riskData?.features) return s;
    for (const feat of riskData.features) {
        const coords = feat.geometry?.coordinates;
        if (!coords || coords.length < 2) continue;
        for (let i = 0; i < coords.length - 1; i++) {
            const [x1, y1] = coords[i];
            const [x2, y2] = coords[i + 1];
            const key = `${((x1 + x2) / 2).toFixed(5)},${((y1 + y2) / 2).toFixed(5)}`;
            s.add(key);
        }
    }
    return s;
}

export function PeopleLayer({ baseRoadsData, populationCount, riskRoadsData, hobliName, onUnsafeCount }) {
    const geojson = useMemo(() => {
        if (!baseRoadsData || !populationCount || populationCount <= 0) {
            return { type: 'FeatureCollection', features: [] };
        }

        const midpoints = collectMidpoints(baseRoadsData);
        if (midpoints.length === 0) return { type: 'FeatureCollection', features: [] };

        const floodedSet = buildFloodedSet(riskRoadsData);
        const rng        = makeRng(strToSeed(hobliName || 'default'));

        // Cap at midpoints available (no duplicates if count < midpoints; allow repeats if more)
        const count   = Math.min(populationCount, 50000); // hard cap for performance
        const features = [];

        for (let i = 0; i < count; i++) {
            const idx  = Math.floor(rng() * midpoints.length);
            const [lon, lat] = midpoints[idx];

            // Tiny jitter so stacked dots spread slightly
            const jlon = lon + (rng() - 0.5) * 0.0002;
            const jlat = lat + (rng() - 0.5) * 0.0002;

            const key     = `${lon.toFixed(5)},${lat.toFixed(5)}`;
            const flooded = floodedSet.has(key);

            features.push({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [jlon, jlat] },
                properties: { flooded: flooded ? 1 : 0 },
            });
        }

        return { type: 'FeatureCollection', features };
    }, [baseRoadsData, populationCount, riskRoadsData, hobliName]);

    // Report flooded count to parent whenever it changes
    useEffect(() => {
        if (!onUnsafeCount) return;
        const count = geojson.features.filter(f => f.properties.flooded === 1).length;
        onUnsafeCount(count);
    }, [geojson, onUnsafeCount]);

    if (!populationCount || populationCount === 0) return null;

    const paint = {
        'circle-radius': 3,
        'circle-opacity': 0.75,
        'circle-stroke-width': 0.5,
        'circle-stroke-color': '#ffffff',
        'circle-color': [
            'match', ['get', 'flooded'],
            1, '#ef4444',   // flooded → red
            '#22c55e',      // safe    → green
        ],
    };

    return (
        <Source id="people-layer" type="geojson" data={geojson}>
            <Layer id="people-dots" type="circle" paint={paint} />
        </Source>
    );
}
