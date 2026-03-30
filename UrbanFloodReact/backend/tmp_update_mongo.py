import os
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Norm key function as defined in coord_loader.py
def norm_key(name: str) -> str:
    return name.strip().lower().replace("_", "-")

if __name__ == "__main__":
    load_dotenv(r"c:\College\major project\Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization\UrbanFloodReact\.env")
    mongo_url = os.getenv("MONGO_URL")
    if not mongo_url:
        print("MONGO_URL not found!")
        exit(1)

    print(f"Connecting to MongoDB...")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = client["flood_evacuation_db"]
    coords_col = db["hobli_coords"]

    # Load the rural hoblis
    csv_path = r"c:\College\major project\Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization\UrbanFloodReact\backend\data\rural_hobli.csv"
    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)
    rural_names = df["KGISHobliN"].dropna().unique().tolist()
    
    rural_keys = {norm_key(n) for n in rural_names}
    print(f"Found {len(rural_keys)} unique normalized rural hobli keys in CSV: {rural_keys}")

    # Query all coords
    docs = list(coords_col.find({}))
    print(f"Found {len(docs)} documents in hobli_coords.")
    
    updated_count = 0
    for doc in docs:
        hobli_name = doc.get("hobli_name")
        if not hobli_name:
            continue
        key = norm_key(hobli_name)
        
        if key in rural_keys:
            if doc.get("type") != "rural":
                print(f"  Updating {hobli_name} to type='rural'")
                coords_col.update_one({"_id": doc["_id"]}, {"$set": {"type": "rural"}})
                updated_count += 1
                
    print(f"\nDone! Updated {updated_count} documents to type='rural'.")
