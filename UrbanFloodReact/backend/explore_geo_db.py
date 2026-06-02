"""
Quick exploration of the Geo cluster to understand the schema.

Prefers MONGO_URI2 and falls back to MONGO_URI / MONGO_URL.
Adds authSource=admin when the URI does not already specify one.
"""
import os
import pprint
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError


def _build_mongo_uri() -> str | None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path, override=True)
    uri = os.getenv("MONGO_URI2")
    if not uri:
        return None

    if "authSource=" not in uri:
        uri = uri + ("&" if "?" in uri else "?") + "authSource=admin"

    return uri


mongo_uri = _build_mongo_uri()
if not mongo_uri:
    raise SystemExit("No Mongo URI found. Set MONGO_URI2, MONGO_URI, or MONGO_URL in .env")

client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)

print("=" * 60)
print("DATABASES")
print("=" * 60)

try:
    client.admin.command("ping")
    dbs = client.list_database_names()
    print(dbs)
except OperationFailure as exc:
    raise SystemExit(
        f"Mongo auth failed: {exc}\n"
        "Check that the Atlas user/password are correct and that the user has access to the geo cluster.\n"
        "If needed, try adding authSource=admin or recreating the Atlas user for this project."
    ) from exc
except PyMongoError as exc:
    raise SystemExit(f"Mongo connection failed: {exc}") from exc

for db_name in dbs:
    if db_name in ("admin", "local", "config"):
        continue
    db = client[db_name]
    collections = db.list_collection_names()
    print(f"\n{'='*60}")
    print(f"DATABASE: {db_name}")
    print(f"Collections: {collections}")

    for col_name in collections:
        col = db[col_name]
        count = col.estimated_document_count()
        print(f"\n  --- Collection: {col_name} ({count:,} docs) ---")

        # Sample 1 document
        sample = col.find_one()
        if sample:
            sample.pop("_id", None)
            print("  Sample document keys:", list(sample.keys()))
            print("  Sample document:")
            pprint.pprint(sample, indent=4, depth=3)

        # Check indexes
        indexes = list(col.list_indexes())
        print(f"  Indexes ({len(indexes)}):")
        for idx in indexes:
            print(f"    {idx['name']}: {idx['key']}")

        # If it looks like an edge collection, show a few more samples
        if sample and any(k in sample for k in ["u", "v", "geometry", "length", "highway"]):
            print("  --> Looks like EDGES collection")
            print("  Edge field types:")
            for k, v in sample.items():
                print(f"    {k}: {type(v).__name__} = {repr(v)[:80]}")

        if sample and any(k in sample for k in ["lat", "lon", "osmid", "elevation"]):
            print("  --> Looks like NODES collection")
            print("  Node field types:")
            for k, v in sample.items():
                print(f"    {k}: {type(v).__name__} = {repr(v)[:80]}")

        if sample and any(k in sample for k in ["WardName", "ward", "boundary", "rainfall"]):
            print("  --> Looks like WARDS collection")

        if sample and any(k in sample for k in ["name", "amenity", "capacity", "shelter"]):
            print("  --> Looks like SHELTERS collection")

print("\n" + "="*60)
print("DONE")
print("="*60)
client.close()
