/**
 * geoUtils.js — Frontend geometry helpers
 * ────────────────────────────────────────
 * Point-in-polygon check (ray casting) for shelter flood safety.
 * No external dependency needed — works with raw GeoJSON coordinates.
 */

/** Ray casting point-in-polygon for a single ring [[[lon,lat],...]] */
function pointInRing(px, py, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const xi = ring[i][0], yi = ring[i][1];
        const xj = ring[j][0], yj = ring[j][1];
        if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi))
            inside = !inside;
    }
    return inside;
}

/** Check if [lon, lat] is inside any flood polygon in a GeoJSON FeatureCollection. */
export function isPointFlooded(lon, lat, floodGeoJSON) {
    if (!floodGeoJSON?.features?.length) return false;
    for (const feat of floodGeoJSON.features) {
        const { type, coordinates } = feat.geometry ?? {};
        if (!coordinates) continue;
        if (type === 'Polygon') {
            if (pointInRing(lon, lat, coordinates[0])) return true;
        } else if (type === 'MultiPolygon') {
            for (const poly of coordinates)
                if (pointInRing(lon, lat, poly[0])) return true;
        }
    }
    return false;
}

/**
 * Given raw candidates and current floodData GeoJSON,
 * return a new array with a `safe` boolean added to each.
 */
export function computeShelterSafety(candidates, floodGeoJSON) {
    if (!candidates?.length) return [];
    return candidates.map(s => ({
        ...s,
        safe: !isPointFlooded(s.lon, s.lat, floodGeoJSON),
    }));
}
