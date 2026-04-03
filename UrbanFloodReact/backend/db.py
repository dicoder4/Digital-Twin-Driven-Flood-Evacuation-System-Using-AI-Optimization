"""
db.py — MongoDB model and bootstrapping layer
─────────────────────────────────────────────
Handles connections to MongoDB and exposes structured
fetching logic for backend components.
"""

import os
import json
import logging
from pathlib import Path
import pandas as pd
from pymongo import MongoClient
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
        return None

    try:
        # Avoid hanging on connection attempts if Mongo is unreachable
        _client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        # Ping to verify connection
        _client.admin.command('ping')
        _db = _client.get_database("flood_evacuation_db")
        return _db
    except Exception as e:
        logger.warning(f"[MONGO DEBUG] Failed to connect to MongoDB: {e}")
        _client = None
        _db = None
        return None

def bootstrap_mongo_data():
    """
    Called on app startup. Reads local resources and writes them to Mongo
    if the collections are currently empty.
    """
    db = _get_db()
    if db is None:
        print("[MONGO DEBUG] Skipping bootstrap: MongoDB is not configured or unreachable.")
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
                    print(f"[MONGO DEBUG] Inserted {len(records)} records into population_data.")

        # 2. Resource Definitions
        res_def_col = db["resource_definitions"]
        if res_def_col.count_documents({}) == 0:
            json_path = data_dir / "resource_definitions.json"
            if json_path.exists():
                with open(json_path, 'r') as f:
                    data = json.load(f)
                    res_def_col.insert_one({"_id": "definitions", "data": data})
                    print("[MONGO DEBUG] Inserted resource_definitions.")

        # 3. Logistics Resources
        log_col = db["logistics_resources"]
        if log_col.count_documents({}) == 0:
            log_path = data_dir / "logistics_resources.csv"
            if log_path.exists():
                df = pd.read_csv(log_path)
                records = df.to_dict(orient="records")
                if records:
                    log_col.insert_many(records)
                    print(f"[MONGO DEBUG] Inserted {len(records)} logistics resources.")

        # 4. Tactical Resources
        tac_col = db["tactical_resources"]
        if tac_col.count_documents({}) == 0:
            tac_path = data_dir / "tactical_resources.csv"
            if tac_path.exists():
                df = pd.read_csv(tac_path)
                records = df.to_dict(orient="records")
                if records:
                    tac_col.insert_many(records)
                    print(f"[MONGO DEBUG] Inserted {len(records)} tactical resources.")

        # 5. IDRN Resources
        idrn_col = db["idrn_resources"]
        if idrn_col.count_documents({}) == 0:
            idrn_path = data_dir / "idrn_resources_scraped.csv"
            if idrn_path.exists():
                df = pd.read_csv(idrn_path)
                records = df.to_dict(orient="records")
                if records:
                    idrn_col.insert_many(records)
                    print(f"[MONGO DEBUG] Inserted {len(records)} IDRN resources.")

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
                    print(f"[MONGO DEBUG] Could not parse rural_hobli.csv: {e}")

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
                print(f"[MONGO DEBUG] Inserted {coords_inserted} hobli coordinates.")

        # 7. Rainfall Data
        rain_col = db["rainfall_data"]
        if rain_col.count_documents({}) == 0:
            rain_inserted = 0
            for month, fname in [("May", "Bengaluru_Rainfall_24Hrs_May.xlsx"), 
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
                print(f"[MONGO DEBUG] Inserted rainfall documents for May, June, July.")

    except Exception as e:
        print(f"[MONGO DEBUG] Error during bootstrap: {e}")


# ── Data Access Methods ───────────────────────────────────────────────────────

def get_population_df() -> pd.DataFrame:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    docs = list(db["population_data"].find({}, {"_id": 0}))
    if not docs:
        raise ValueError("No population data in Mongo")
    
    print("[MONGO DEBUG] Successfully fetched population data from MongoDB")
    return pd.DataFrame(docs)

def get_resource_definitions() -> dict:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    doc = db["resource_definitions"].find_one({"_id": "definitions"})
    if not doc or "data" not in doc:
        raise ValueError("No resource definitions in Mongo")
    
    print("[MONGO DEBUG] Successfully fetched resource definitions from MongoDB")
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
    
    print(f"[MONGO DEBUG] Successfully fetched {col_name} from MongoDB")
    return pd.DataFrame(docs)

def get_hobli_coords_raw(ctype: str) -> list:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    docs = list(db["hobli_coords"].find({"type": ctype}, {"_id": 0}))
    if not docs:
        raise ValueError("No hobli coordinates in Mongo")
    
    print(f"[MONGO DEBUG] Successfully fetched {ctype} hobli coordinates from MongoDB")
    return docs

def get_rainfall_df_for_month(month: str) -> pd.DataFrame:
    db = _get_db()
    if db is None:
        raise ConnectionError("MongoDB not available")
    
    doc = db["rainfall_data"].find_one({"month": month})
    if not doc or "records" not in doc:
        raise ValueError(f"No rainfall records for month {month} in Mongo")
    
    print(f"[MONGO DEBUG] Successfully fetched {month} rainfall from MongoDB")
    return pd.DataFrame(doc["records"])
