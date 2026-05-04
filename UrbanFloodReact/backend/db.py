"""
db.py — MongoDB model and bootstrapping layer
─────────────────────────────────────────────
Handles connections to MongoDB and exposes structured
fetching logic for backend components.

Cache collections (all device-agnostic, no local disk):
  region_cache     — GraphML XML + pickled features per hobli
  shelter_cache    — OSM shelter candidates per hobli
  dem_cache        — SRTM DEM GeoTIFF bytes per bounding-box key
  mcp_state        — Latest MCP simulation state (single document)
"""

import os
import json
import base64
import logging
from pathlib import Path
import pandas as pd
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

# Module-level client and DB
_client = None
_db = None

def _get_db():
    global _client, _db
    if _db is not None:
        return _db
    
    mongo_url = os.getenv("MONGO_URL") or os.getenv("MONGO_URI")
    if not mongo_url:
        logger.error("[MONGO] MONGO_URL / MONGO_URI not set — database unavailable")
        return None

    try:
        _client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        _client.admin.command('ping')
        _db = _client.get_database("flood_evacuation_db")
        logger.info("[MONGO] Connected to flood_evacuation_db")
        return _db
    except Exception as e:
        logger.error("[MONGO] Connection failed: %s", e)
        _client = None
        _db = None
        return None

def bootstrap_mongo_data():
    """
    Called on app startup. Reads local resources and writes them to Mongo
    if the collections are currently empty.
    """
    import time
    
    db = None
    retries = 3
    for i in range(retries):
        db = _get_db()
        if db is not None:
            break
        logger.warning("[MONGO] Bootstrap attempt %d/%d failed. Retrying in 3s...", i + 1, retries)
        time.sleep(3)

    if db is None:
        logger.error("[MONGO] Bootstrap aborted — could not connect after %d attempts", retries)
        return

    data_dir = Path(__file__).parent / "data"

    try:
        # 1. Population Data
        pop_col = db["population_data"]
        if pop_col.count_documents({}) == 0:
            csv_path = data_dir / "269cdf01-dae5-4736-8f4d-72a8e57fa3a9.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                records = df.to_dict(orient="records")
                if records:
                    pop_col.insert_many(records)
                    logger.info("[MONGO] bootstrap: inserted %d records into population_data", len(records))

        # 2. Resource Definitions
        res_def_col = db["resource_definitions"]
        if res_def_col.count_documents({}) == 0:
            json_path = data_dir / "resource_definitions.json"
            if json_path.exists():
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    res_def_col.insert_one({"_id": "definitions", "data": data})
                    logger.info("[MONGO] bootstrap: inserted resource_definitions")

        # 3. Logistics Resources
        log_col = db["logistics_resources"]
        if log_col.count_documents({}) == 0:
            log_path = data_dir / "logistics_resources.csv"
            if log_path.exists():
                df = pd.read_csv(log_path)
                records = df.to_dict(orient="records")
                if records:
                    log_col.insert_many(records)
                    logger.info("[MONGO] bootstrap: inserted %d logistics resources", len(records))

        # 4. Tactical Resources
        tac_col = db["tactical_resources"]
        if tac_col.count_documents({}) == 0:
            tac_path = data_dir / "tactical_resources.csv"
            if tac_path.exists():
                df = pd.read_csv(tac_path)
                records = df.to_dict(orient="records")
                if records:
                    tac_col.insert_many(records)
                    logger.info("[MONGO] bootstrap: inserted %d tactical resources", len(records))

        # 5. IDRN Resources
        idrn_col = db["idrn_resources"]
        if idrn_col.count_documents({}) == 0:
            idrn_path = data_dir / "idrn_resources_scraped.csv"
            if idrn_path.exists():
                df = pd.read_csv(idrn_path)
                records = df.to_dict(orient="records")
                if records:
                    idrn_col.insert_many(records)
                    logger.info("[MONGO] bootstrap: inserted %d IDRN resources", len(records))

        # 6. Hobli Coordinates
        coords_col = db["hobli_coords"]
        if coords_col.count_documents({}) == 0:
            coords_inserted = 0
            rural_names = set()
            rural_csv = data_dir / "rural_hobli.csv"
            if rural_csv.exists():
                try:
                    df_rural = pd.read_csv(rural_csv)
                    rural_names = {k.strip().lower().replace("_", "-") for k in df_rural["KGISHobliN"].dropna().unique()}
                except Exception as e:
                    logger.warning("[MONGO] bootstrap: could not parse rural_hobli.csv: %s", e)

            for ct, fname in [("urban", "hobli_coordinates_urban.json"), ("rural", "hobli_coordinates_rural.json")]:
                p = data_dir / fname
                if p.exists():
                    with open(p, 'r') as f:
                        data = json.load(f)
                        records = []
                        for r in data:
                            # Override to rural if found in rural_hobli.csv
                            key = r.get("hobli_name", "").strip().lower().replace("_", "-")
                            if key in rural_names:
                                r["type"] = "rural"
                            else:
                                r["type"] = ct
                            records.append(r)
                        if records:
                            coords_col.insert_many(records)
                            coords_inserted += len(records)
            if coords_inserted > 0:
                logger.info("[MONGO] bootstrap: inserted %d hobli coordinates", coords_inserted)

        # 7. Rainfall Data
        rain_col = db["rainfall_data"]
        if rain_col.count_documents({}) == 0:
            rain_inserted = 0
            for month, fname in [("April", "Bengaluru_Rainfall_24Hrs_2026.xlsx"),
                                 ("May", "Bengaluru_Rainfall_24Hrs_May.xlsx"), 
                                 ("June", "Bengaluru_Rainfall_24Hrs_June.xlsx"), 
                                 ("July", "Bengaluru_Rainfall_24Hrs_July.xlsx")]:
                p = data_dir / fname
                if p.exists():
                    df = pd.read_excel(p)
                    # Need to handle dates/NaTs appropriately for Mongo inserting (using strings instead of Timestamps)
                    df = df.astype(str)
                    records = df.to_dict(orient="records")
                    if records:
                        rain_col.insert_one({"month": month, "records": records})
                        rain_inserted += len(records)
            if rain_inserted > 0:
                logger.info("[MONGO] bootstrap: inserted rainfall data (%d rows total)", rain_inserted)

        # 8. Metro Network Data
        metro_net_col = db["metro_network"]
        if metro_net_col.count_documents({}) == 0:
            metro_dir = data_dir / "NammaMetro"
            csv_path = metro_dir / "bengaluru_metro_network.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                records = df.to_dict(orient="records")
                if records:
                    metro_net_col.insert_many(records)
                    logger.info("[MONGO] bootstrap: inserted %d records into metro_network", len(records))

        # 9. Metro Stations Reference
        metro_sta_col = db["metro_stations_ref"]
        if metro_sta_col.count_documents({}) == 0:
            metro_dir = data_dir / "NammaMetro"
            csv_path = metro_dir / "bengaluru_metro_stations.csv"
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                records = df.to_dict(orient="records")
                if records:
                    metro_sta_col.insert_many(records)
                    logger.info("[MONGO] bootstrap: inserted %d records into metro_stations_ref", len(records))

        # 10. Metro Lines GeoJSON
        metro_geo_col = db["metro_lines_geojson"]
        if metro_geo_col.count_documents({}) == 0:
            metro_dir = data_dir / "NammaMetro"
            geo_path = metro_dir / "metro-lines-stations.geojson"
            if geo_path.exists():
                with open(geo_path, 'r') as f:
                    data = json.load(f)
                    # Insert as a single document for the whole feature collection
                    metro_geo_col.insert_one({"_id": "metro_lines", "data": data})
                    logger.info("[MONGO] bootstrap: inserted metro_lines_geojson")

    except Exception as e:
        logger.error("[MONGO] bootstrap error: %s", e, exc_info=True)


# ── Data Access Methods ───────────────────────────────────────────────────────

def get_population_df() -> pd.DataFrame:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    docs = list(db["population_data"].find({}, {"_id": 0}))
    if not docs:
        raise ValueError("No population data in Mongo")
    
    logger.info("[MONGO] population_data: fetched %d records", len(docs))
    return pd.DataFrame(docs)

def get_resource_definitions() -> dict:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    doc = db["resource_definitions"].find_one({"_id": "definitions"})
    if not doc or "data" not in doc:
        raise ValueError("No resource definitions in Mongo")
    
    logger.info("[MONGO] resource_definitions: fetched")
    return doc["data"]

def get_logistics_df() -> pd.DataFrame:
    return _get_resource_collection_df("logistics_resources")

def get_tactical_df() -> pd.DataFrame:
    return _get_resource_collection_df("tactical_resources")

def get_idrn_df() -> pd.DataFrame:
    return _get_resource_collection_df("idrn_resources")

def _get_resource_collection_df(col_name: str) -> pd.DataFrame:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    docs = list(db[col_name].find({}, {"_id": 0}))
    if not docs:
        raise ValueError(f"No {col_name} records in Mongo")
    
    logger.info("[MONGO] %s: fetched %d records", col_name, len(docs))
    return pd.DataFrame(docs)

def get_hobli_coords_raw(ctype: str) -> list:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    docs = list(db["hobli_coords"].find({"type": ctype}, {"_id": 0}))
    if not docs:
        raise ValueError("No hobli coordinates in Mongo")
    
    logger.info("[MONGO] hobli_coords (%s): fetched %d records", ctype, len(docs))
    return docs

def get_rainfall_df_for_month(month: str) -> pd.DataFrame:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    doc = db["rainfall_data"].find_one({"month": month})
    if not doc or "records" not in doc:
        raise ValueError(f"No rainfall records for month {month} in Mongo")
    
    logger.info("[MONGO] rainfall_data (%s): fetched %d rows", month, len(doc["records"]))
    return pd.DataFrame(doc["records"])

def get_metro_network_df() -> pd.DataFrame:
    return _get_resource_collection_df("metro_network")

def get_metro_stations_ref_df() -> pd.DataFrame:
    return _get_resource_collection_df("metro_stations_ref")

def get_metro_lines_geojson() -> dict:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")

    doc = db["metro_lines_geojson"].find_one({"_id": "metro_lines"})
    if not doc or "data" not in doc:
        raise ValueError("No metro lines GeoJSON in Mongo")

    logger.info("[MONGO] metro_lines_geojson: fetched")
    return doc["data"]


# ── Region Cache (graph GraphML + features pickle) ────────────────────────────

def get_region_cache(hobli_key: str) -> dict | None:
    """
    Returns {"graphml_b64": str, "features_b64": str} or None if not cached.
    Callers decode with base64.b64decode and reconstruct objects themselves.
    """
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] region_cache: DB unavailable — cache miss for '%s'", hobli_key)
        return None
    doc = db["region_cache"].find_one({"_id": hobli_key}, {"_id": 0})
    if doc:
        logger.info("[MONGO] region_cache HIT  — '%s' loaded from MongoDB", hobli_key)
    else:
        logger.info("[MONGO] region_cache MISS — '%s' not in MongoDB, will download from OSMnx", hobli_key)
    return doc if doc else None


def set_region_cache(hobli_key: str, graphml_b64: str, features_b64: str) -> None:
    """Upsert the GraphML + features blobs for a hobli into MongoDB."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] region_cache: DB unavailable — cannot save '%s'", hobli_key)
        return
    db["region_cache"].update_one(
        {"_id": hobli_key},
        {"$set": {"graphml_b64": graphml_b64, "features_b64": features_b64}},
        upsert=True,
    )
    logger.info("[MONGO] region_cache WRITE — '%s' graph + features saved to MongoDB", hobli_key)


def update_region_features(hobli_key: str, features_b64: str) -> None:
    """Update only the features blob (e.g. after metro extraction)."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] region_cache: DB unavailable — cannot update features for '%s'", hobli_key)
        return
    db["region_cache"].update_one(
        {"_id": hobli_key},
        {"$set": {"features_b64": features_b64}},
        upsert=True,
    )
    logger.info("[MONGO] region_cache UPDATE — '%s' features (metro/drains/lakes) updated in MongoDB", hobli_key)


# ── Shelter Cache ─────────────────────────────────────────────────────────────

def get_shelter_cache(hobli_key: str) -> list | None:
    """Returns list of shelter dicts or None if not cached."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] shelter_cache: DB unavailable — cache miss for '%s'", hobli_key)
        return None
    doc = db["shelter_cache"].find_one({"_id": hobli_key})
    if doc and "candidates" in doc:
        logger.info("[MONGO] shelter_cache HIT  — %d shelters loaded from MongoDB for '%s'",
                    len(doc["candidates"]), hobli_key)
        return doc["candidates"]
    logger.info("[MONGO] shelter_cache MISS — '%s' not in MongoDB, will query OSM", hobli_key)
    return None


def set_shelter_cache(hobli_key: str, candidates: list) -> None:
    """Upsert shelter candidates list for a hobli."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] shelter_cache: DB unavailable — cannot save '%s'", hobli_key)
        return
    db["shelter_cache"].update_one(
        {"_id": hobli_key},
        {"$set": {"candidates": candidates}},
        upsert=True,
    )
    logger.info("[MONGO] shelter_cache WRITE — %d candidates saved for '%s'", len(candidates), hobli_key)


# ── DEM Cache (SRTM GeoTIFF bytes stored as base64) ──────────────────────────

def get_dem_cache(dem_key: str) -> bytes | None:
    """Returns raw GeoTIFF bytes or None if not cached."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] dem_cache: DB unavailable — cache miss for '%s'", dem_key)
        return None
    doc = db["dem_cache"].find_one({"_id": dem_key})
    if doc and "data_b64" in doc:
        raw = base64.b64decode(doc["data_b64"])
        logger.info("[MONGO] dem_cache HIT  — %d KB DEM loaded from MongoDB for '%s'",
                    len(raw) // 1024, dem_key)
        return raw
    logger.info("[MONGO] dem_cache MISS — '%s' not in MongoDB, will download from OpenTopography", dem_key)
    return None


def set_dem_cache(dem_key: str, tif_bytes: bytes) -> None:
    """Store raw GeoTIFF bytes (base64-encoded) for a bounding-box key."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] dem_cache: DB unavailable — cannot save '%s'", dem_key)
        return
    db["dem_cache"].update_one(
        {"_id": dem_key},
        {"$set": {"data_b64": base64.b64encode(tif_bytes).decode("ascii")}},
        upsert=True,
    )
    logger.info("[MONGO] dem_cache WRITE — %d KB DEM saved for '%s'", len(tif_bytes) // 1024, dem_key)


# ── MCP State (single shared document) ───────────────────────────────────────

def get_mcp_state() -> dict:
    """Returns the latest simulation state dict, or an empty-state dict if none."""
    db = _get_db()
    empty = {"summary_data": None, "evacuation_plan": None, "hobli": None, "algorithm_analysis": None}
    if db is None:
        logger.warning("[MONGO] mcp_state: DB unavailable — returning empty state")
        return empty
    doc = db["mcp_state"].find_one({"_id": "current"})
    if not doc:
        logger.info("[MONGO] mcp_state: No simulation state stored yet — returning empty state")
        return empty
    doc.pop("_id", None)
    hobli = doc.get("hobli") or "unknown"
    logger.info("[MONGO] mcp_state READ — loaded state for hobli '%s'", hobli)
    return doc


def set_mcp_state(summary_data: dict, evacuation_plan: list = None,
                  hobli: str = None, algorithm_analysis: dict = None) -> None:
    """Upsert the MCP simulation state into MongoDB."""
    db = _get_db()
    if db is None:
        logger.warning("[MONGO] mcp_state: DB unavailable — state NOT saved for hobli '%s'", hobli)
        return
    db["mcp_state"].update_one(
        {"_id": "current"},
        {"$set": {
            "summary_data": summary_data,
            "evacuation_plan": evacuation_plan or [],
            "hobli": hobli or "",
            "algorithm_analysis": algorithm_analysis,
        }},
        upsert=True,
    )
    logger.info("[MONGO] mcp_state WRITE — simulation state saved for hobli '%s'", hobli or "unknown")
