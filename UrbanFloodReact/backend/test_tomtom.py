import os
from dotenv import load_dotenv
from traffic_data.tomtom import get_bulk_traffic_data

load_dotenv()
api_key = os.getenv('TOMTOM_API_KEY')
print(f"API Key loaded: {api_key is not None}")

coords = [(12.9716, 77.5946)]
print(f"Fetching traffic for coords: {coords}")

results = get_bulk_traffic_data(api_key, coords)
print(f"Results: {results}")
