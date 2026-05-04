# Cache Architecture Summary

## What Gets Cached

### ✅ **Persisted to MongoDB** (Survives restart, shared across devices)

| Type | Location | Trigger | Flow |
|------|----------|---------|------|
| **Region Graphs** | `region_cache` collection | First load of hobli | Download from OSMnx → Store as base64 GraphML |
| **Shelter Candidates** | `shelter_cache` collection | First load of hobli | Query OSM → Store as JSON array |
| **DEM (Elevation)** | `dem_cache` collection | First graph enrichment | Download from OpenTopography → Store as base64 GeoTIFF |
| **MCP State** | `mcp_state` collection | After evacuation simulation | Save summary + plan + hobli |
| **Population Data** | `population_data` collection | Bootstrap | CSV → MongoDB (one-time) |
| **Logistics Resources** | `logistics_resources` collection | Bootstrap | CSV → MongoDB (one-time) |
| **Tactical Resources** | `tactical_resources` collection | Bootstrap | CSV → MongoDB (one-time) |
| **IDRN Resources** | `idrn_resources` collection | Bootstrap | CSV → MongoDB (one-time) |
| **Rainfall Data** | `rainfall_data` collection | Bootstrap | Excel → MongoDB (one-time) |
| **Hobli Coordinates** | `hobli_coords` collection | Bootstrap | JSON → MongoDB (one-time) |

### ⚠️ **Temporary Local Files** (Automatically cleaned up)

| Type | Location | Size | Lifetime |
|------|----------|------|----------|
| **GraphML Temp** | `/tmp/*.graphml` | ~50-200 KB | During `ox.load_graphml()` call (milliseconds) |
| **GeoTIFF Temp** | `/tmp/*.tif` | ~1-5 MB | During `rasterio.open()` call (seconds) |

These are **in-memory only** — deleted with `os.unlink()` after use.

### ❌ **NO Persistent Local Files**

- ❌ No `CACHE_DIR` disk cache
- ❌ No pickle files
- ❌ No local JSON state files
- ❌ No GraphML files on disk
- ❌ No DEM GeoTIFF files on disk
- ❌ No CSV fallbacks

## Behavior by Scenario

### **Scenario 1: First Device, First Region Load**
```
Request: POST /load-region hobli=sarjapura-1
├─ get_region_cache('sarjapura-1') → MISS (not in MongoDB)
├─ Download from OSMnx (fresh network data)
├─ Extract drains, lakes, metro stations
├─ Enrich with elevation from OpenTopography
├─ set_region_cache() → Save GraphML + features to MongoDB
├─ Return region data
└─ Log: [MONGO] region_cache MISS, region_cache WRITE
```

**Storage**: Data now persisted in MongoDB  
**Local**: Only temp files (cleaned up)

### **Scenario 2: Same Device, Second Region Load**
```
Request: POST /load-region hobli=sarjapura-1 (again)
├─ get_region_cache('sarjapura-1') → HIT! (in MongoDB)
├─ Deserialize from base64
├─ Enrich with elevation (in-memory)
├─ Return region data
└─ Log: [MONGO] region_cache HIT
```

**Speed**: ~100ms (no network calls)  
**Local**: No files created

### **Scenario 3: Different Device, Same Region**
```
Request: POST /load-region hobli=sarjapura-1 (new device)
├─ get_region_cache('sarjapura-1') → HIT! (in MongoDB, shared)
├─ Deserialize from base64
├─ Enrich with elevation (in-memory)
├─ Return region data
└─ Log: [MONGO] region_cache HIT
```

**Speed**: ~100ms (no OSMnx/OpenTopography downloads needed)  
**Storage**: Reuses MongoDB cache from first device  
**Local**: No files created

## Multi-Device Behavior

```
Device A (First to load sarjapura-1)
├─ OSMnx download
├─ OpenTopography DEM download
└─ Store both to MongoDB

Device B (Loads sarjapura-1 later)
├─ Check MongoDB → HIT
└─ Load directly (no downloads needed)

Device C (Loads sarjapura-1 later)
├─ Check MongoDB → HIT
└─ Load directly (no downloads needed)
```

**Result**: First device pays the download cost (~30s), subsequent devices instant (~100ms)

## No Disk Space Concerns

- ✅ No `CACHE_DIR` consuming GB
- ✅ No old pickle files accumulating
- ✅ Temp files cleaned up immediately
- ✅ All persistent data in MongoDB (managed by MongoDB)

## Logging Shows It All

```bash
# Cold start (first region)
[MONGO] region_cache MISS — will download from OSMnx
[MONGO] region_cache WRITE — graph + features saved to MongoDB

# Warm start (cached region)
[MONGO] region_cache HIT — loaded from MongoDB

# DEM caching
[MONGO] dem_cache MISS — will download from OpenTopography
[MONGO] dem_cache WRITE — 342 KB DEM saved

# State persistence
[MONGO] mcp_state WRITE — simulation state saved
[MONGO] mcp_state READ — loaded state
```

---

**Bottom Line**: Everything that needs to persist lives in MongoDB. Only temporary working files exist locally (and are immediately deleted).
