import pandas as pd
import shapely.wkb as wkb
from pyproj import Transformer
import ast
import json

# ---------- CONFIG ----------
INPUT_FILE = "rural_hobli.csv"
OUTPUT_FILE = "hobli_coordinates_rural.json"
SOURCE_CRS = "EPSG:32643"   # UTM Zone 43N (Bengaluru)
TARGET_CRS = "EPSG:4326"    # WGS84 (Lat/Lon)
# ----------------------------

def extract_hobli_coordinates(input_file, output_file):
    # Load dataset
    df = pd.read_csv(input_file)

    # Coordinate transformer
    transformer = Transformer.from_crs(
        SOURCE_CRS,
        TARGET_CRS,
        always_xy=True
    )

    hobli_data = []

    for _, row in df.iterrows():
        try:
            # Convert string representation of bytes to actual bytes
            geom_bytes = ast.literal_eval(row["geometry"])

            # Load WKB geometry
            geom = wkb.loads(geom_bytes)

            # Get centroid of polygon
            centroid = geom.centroid
            x, y = centroid.x, centroid.y

            # Convert to lat/lon
            lon, lat = transformer.transform(x, y)

            hobli_data.append({
                "hobli_name": row["KGISHobliN"],
                "latitude": round(lat, 6),
                "longitude": round(lon, 6)
            })

        except Exception as e:
            print(f"Skipping row due to error: {e}")
            continue

    # Write to JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(hobli_data, f, indent=4)

    print(f"\n✅ Successfully exported {len(hobli_data)} hoblis to {output_file}")


if __name__ == "__main__":
    extract_hobli_coordinates(INPUT_FILE, OUTPUT_FILE)
