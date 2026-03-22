import pdfplumber
import pandas as pd
import json
import re
import os
import difflib
import time
from geopy.geocoders import ArcGIS
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# --- Configuration ---
DATA_DIR = os.path.dirname(os.path.abspath(__file__)) 
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(DATA_DIR)))
PDF_PATH = os.path.join(PROJECT_ROOT, "result.pdf") 
KNOWN_LOCATIONS_PATH = os.path.join(DATA_DIR, "known_resource_locations.json")

print("Project Data Directory:", DATA_DIR)
print("PDF Path:", PDF_PATH)

if not os.path.exists(PDF_PATH):
   PDF_PATH = r"c:\Users\Aditr\OneDrive\Desktop\Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization\result.pdf"

OUTPUT_CSV = os.path.join(DATA_DIR, "idrn_resources_scraped.csv")
OUTPUT_LOGISTICS_CSV = os.path.join(DATA_DIR, "logistics_resources.csv")
OUTPUT_TACTICAL_CSV = os.path.join(DATA_DIR, "tactical_resources.csv")

geolocator = ArcGIS(user_agent="urban_flood_evacuation_system_scraper_v8")

RESOURCE_DEFINITIONS_PATH = os.path.join(DATA_DIR, "resource_definitions.json")

# Maps Item Code -> Category ("Logistics" or "Tactical")
ITEM_CODE_MAP = {}

# Default Fallback (Empty, will be populated from JSON)
LOGISTICS_KEYWORDS = set()
TACTICAL_KEYWORDS = set()

def load_resource_definitions():
    """Load resource definitions from JSON and populate keyword sets."""
    global LOGISTICS_KEYWORDS, TACTICAL_KEYWORDS, ITEM_CODE_MAP
    
    if os.path.exists(RESOURCE_DEFINITIONS_PATH):
        try:
            with open(RESOURCE_DEFINITIONS_PATH, 'r') as f:
                data = json.load(f)
                
            # Define mapping logic
            # Tactical Activities
            tactical_activities = [
                "Search And Rescue", "Flood Rescue", 
                "Nuclear Biological And Chemical", "Equipment"
            ]
            
            # Logistics Activities
            logistics_activities = [
                "Health Services", "Shelters", "Transportation", 
                "Tele Communication", "Food", "Medical"
            ]
            
            for activity, categories in data.items():
                target_set = None
                category_type = "Other"
                
                # Check Activity Name against mappings (Case Insensitive Partial Match)
                act_upper = activity.upper()
                
                is_tactical = any(t.upper() in act_upper for t in tactical_activities)
                is_logistics = any(l.upper() in act_upper for l in logistics_activities)
                
                if is_tactical: 
                    target_set = TACTICAL_KEYWORDS
                    category_type = "Tactical"
                elif is_logistics: 
                    target_set = LOGISTICS_KEYWORDS
                    category_type = "Logistics"
                else: 
                    # Default: Assume equipment/rescue tools are tactical by default if ambiguous?
                    # Or keep as 'Other' -> User didn't specify. 
                    # Let's add 'General' things to Logistics if they seem like supplies.
                    pass

                if target_set is not None:
                    for cat_name, items in categories.items():
                        # Add Category Name itself as a keyword
                        # Note: cat_name from JSON is string
                        target_set.add(cat_name.lower())
                        for item in items:
                            # Handle dictionary items with codes
                            if isinstance(item, dict):
                                code = item.get('code')
                                name = item.get('name', '')
                                if code:
                                    ITEM_CODE_MAP[str(code)] = category_type
                                if name:
                                    target_set.add(name.lower())
                            else:
                                target_set.add(item.lower())
                            
            print(f"Loaded Resource Definitions. Tactical Codes: {list(ITEM_CODE_MAP.values()).count('Tactical')}, Logistics Codes: {list(ITEM_CODE_MAP.values()).count('Logistics')}")
            
        except Exception as e:
            print(f"Error loading resource definitions: {e}")

# Load definitions immediately
load_resource_definitions()

def load_known_locations():
    """Load cached coordinates from JSON."""
    data = {}
    
    if os.path.exists(KNOWN_LOCATIONS_PATH):
        try:
            with open(KNOWN_LOCATIONS_PATH, 'r') as f:
                data = json.load(f)
                print(f"Loaded {len(data)} known locations from cache.")
        except Exception as e:
            print(f"Error loading known locations: {e}")
            
    return data

KNOWN_LOCATIONS = load_known_locations()

def clean_text(text):
    if not text: return ""
    return str(text).replace('\n', ' ').strip()

def parse_pdf_row_data(item_cell, qty_cell, desc_cell, dept_cell):
    item_code = "Unknown"
    item_name = "Unknown"
    clean_item = clean_text(item_cell)
    
    # Try extracting ITEM CODE
    m_code = re.search(r'ITEM CODE\s*:?[\s\n]+([0-9a-zA-Z]+)', clean_item, re.IGNORECASE)
    if m_code:
        item_code = m_code.group(1).strip()
        
    # Extract item name
    raw_name = clean_item
    m_item = re.search(r'ITEM\s*:?[\s\n]+([^\n]+)', clean_item, re.IGNORECASE)
    if m_item:
        raw_name = m_item.group(1)
        raw_name = re.split(r'(LOCATION|SOURCE|ITEM CODE)', raw_name)[0]
    
    # If we parsed a code, sometimes the "ITEM" follows it. Clean further if needed.
    item_name = raw_name.replace(f"ITEM CODE : {item_code}", "").strip()
    item_name = re.sub(r'ITEM CODE\s*:?\s*', '', item_name, flags=re.IGNORECASE).strip()
    
    # Fallback cleanup
    if "ITEM :" in item_name:
        item_name = item_name.split("ITEM :")[-1].strip()

    dept_text = str(dept_cell).replace('\n', '  ')
    dept_name = "N/A"
    dept_addr = "N/A"
    contact = "N/A"
    phone_str = "N/A"
    
    m_dn = re.search(r'DEPT NAME\s*:\s*(.*?)(DEPT ADDR|CONTACT|MOBILE|PHONE|EMAIL|$)', dept_text, re.IGNORECASE)
    if m_dn: dept_name = m_dn.group(1).strip()
    
    m_da = re.search(r'DEPT ADDR\s*:\s*(.*?)(CONTACT|MOBILE|PHONE|EMAIL|$)', dept_text, re.IGNORECASE)
    if m_da: dept_addr = m_da.group(1).strip()
    
    m_cp = re.search(r'CONTACT PERSON\s*:\s*(.*?)(MOBILE|PHONE|EMAIL|$)', dept_text, re.IGNORECASE)
    if m_cp: contact = m_cp.group(1).strip()
    
    m_mob = re.search(r'MOBILE NO\.\s*:\s*(.*?)(PHONE|EMAIL|$)', dept_text, re.IGNORECASE)
    m_ph = re.search(r'PHONE NO\.\s*:\s*(.*?)(EMAIL|$)', dept_text, re.IGNORECASE)
    mob = m_mob.group(1).strip() if m_mob else ""
    ph = m_ph.group(1).strip() if m_ph else ""
    phone_str = f"{mob} / {ph}".strip(" /")
    
    return item_code, item_name, clean_text(qty_cell), dept_name, dept_addr, contact, phone_str

def get_coordinates_arcgis(address_key):
    """
    Look up coordinates using ArcGIS API.
    ArcGIS is more robust with POIs and partial addresses than Nominatim.
    """
    if len(address_key) < 4: return None
    
    # Clean the address key for better matching
    search_query = address_key.replace("KARNATAKA STATE FIRE AND EMERGENCY SERVICES", "").replace("HEALTH AND FAMILY WELFARE SERVICES", "").replace("AROGYA SOUDH", "")
    search_query = search_query.strip(" .,")
    
    parts = search_query.split(',')
    
    attempts = []
    
    # Attempt 1: Full Cleaned Query + Bangalore
    attempts.append(f"{search_query}, Bengaluru")
    
    # Attempt 2: First valid part + Bangalore (often the building name)
    if len(parts) > 0 and len(parts[0].strip()) > 4:
        attempts.append(f"{parts[0].strip()}, Bengaluru")
        
    # Attempt 3: Last part + Bangalore (often the area name for fire stations)
    if len(parts) > 1 and len(parts[-1].strip()) > 3:
         attempts.append(f"{parts[-1].strip()}, Bengaluru")

    for query in attempts:
        try:
            # ArcGIS doesn't require aggressive sleeping, but good to be safe
            time.sleep(0.5) 
            # print(f"  > Trying (ArcGIS): {query}")
            location = geolocator.geocode(query, timeout=10)
            if location:
                # Validate if result is actually near Bangalore (approx 12-14 lat, 77-78 lon)
                if 12.0 < location.latitude < 14.0 and 77.0 < location.longitude < 78.5:
                     return [location.latitude, location.longitude]
        except Exception as e:
            pass # print(f"Error geocoding {query}: {e}")
        
    return None

def main():
    print(f"Starting Unified Scraper (Single Pass)... PDF: {PDF_PATH}")
    if not os.path.exists(PDF_PATH):
        print(f"Error: {PDF_PATH} does not exist.")
        return
    
    # Use KNOWN_LOCATIONS (loaded at start) as our cache
    location_cache = KNOWN_LOCATIONS.copy()
    new_locations_found = 0

    extracted_items = []
    
    try:
        with pdfplumber.open(PDF_PATH) as pdf:
            total_pages = len(pdf.pages)
            print(f"Processing {total_pages} pages...")
            
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 6: continue
                        if "S.NO" in str(row[0]).upper(): continue
                        
                        try:
                            # 1. Parse PDF Row
                            item_code, item_name, qty, d_name, d_addr, contact, phone = parse_pdf_row_data(row[2], row[3], row[4], row[5])
                            
                            # 2. Construct Search Key for Geocoding
                            geocode_target = d_addr if len(d_addr) > 5 else d_name 
                            if d_name and d_name not in geocode_target:
                                geocode_target = f"{d_name}, {d_addr}"
                            geocode_target = geocode_target.strip(" ,N/A")
                            geocode_target = re.sub(r'\s+', ' ', geocode_target)
                            
                            # 3. Resolve Coordinates (Cache -> Known DB -> ArcGIS API)
                            lat, lon = None, None
                            
                            # Case-insensitive check
                            target_upper = geocode_target.upper()
                            
                            # A. Check Cache (Exact match)
                            if geocode_target in location_cache:
                                lat, lon = location_cache[geocode_target]
                            
                            # B. Check Cache (Fuzzy/Partial match logic from known DB)
                            if not lat:
                                for k, coords in location_cache.items():
                                    if k.upper() in target_upper or target_upper in k.upper():
                                        lat, lon = coords
                                        # Store specific mapping to avoid re-looping next time
                                        location_cache[geocode_target] = (lat, lon) 
                                        break
                                        
                            # C. Geocode if missing
                            if not lat and len(geocode_target) > 5:
                                print(f"Geocoding new location: {geocode_target}")
                                coords = get_coordinates_arcgis(geocode_target)
                                if coords:
                                    lat, lon = coords
                                    # Update Cache immediately
                                    location_cache[geocode_target] = (lat, lon)
                                    new_locations_found += 1
                                    print(f"  -> Found: {lat}, {lon}")
                                else:
                                    print("  -> Not found.")
                            
                            # 4. Classify Item
                            cat = "Other"
                            
                            # Priority: Check Item Code first
                            if item_code and item_code in ITEM_CODE_MAP:
                                cat = ITEM_CODE_MAP[item_code]
                            else:
                                # Fallback: Keyword search in description
                                full_desc = f"{item_name} {clean_text(row[4])}".lower()
                                if any(k in full_desc for k in LOGISTICS_KEYWORDS): cat = "Logistics"
                                elif any(k in full_desc for k in TACTICAL_KEYWORDS): cat = "Tactical"
                            
                            extracted_items.append({
                                "Sl No": len(extracted_items)+1,
                                "Category": cat,
                                "Item Code": item_code,
                                "Item Name": item_name.title(),
                                "Quantity": qty,
                                "Department": d_name,
                                "Address": d_addr,
                                "Contact Name": contact,
                                "Phone": phone,
                                "Latitude": lat,
                                "Longitude": lon,
                                "District": "Bengaluru"
                            })
                        except Exception as e:
                            pass # print(f"Row Error: {e}")
                
                if (i+1) % 20 == 0:
                    print(f"Scanned {i+1} pages...")
                    
    except Exception as e:
        print(f"PDF Error: {e}")
        return

    # 5. Save Updated Location DB if new locations were found
    if new_locations_found > 0:
        print(f"Saving {new_locations_found} NEW locations to DB...")
        try:
            with open(KNOWN_LOCATIONS_PATH, 'w') as f:
                json.dump(location_cache, f, indent=4)
        except Exception as e:
            print(f"Error saving location DB: {e}")

    # 6. Save Data CSVs
    df = pd.DataFrame(extracted_items)
    print(f"Total Scraped Items: {len(df)}")
    
    # Filter valid coordinates for CSV
    valid_df = df.dropna(subset=['Latitude', 'Longitude'])
    print(f"Items with Valid Coordinates: {len(valid_df)} / {len(df)}")
    
    valid_df.to_csv(OUTPUT_CSV, index=False)
    
    log_df = valid_df[valid_df['Category'] == 'Logistics']
    log_df.to_csv(OUTPUT_LOGISTICS_CSV, index=False)
    
    tac_df = valid_df[valid_df['Category'] == 'Tactical']
    tac_df.to_csv(OUTPUT_TACTICAL_CSV, index=False)
    
    print(f"CSVs saved: \n - {OUTPUT_CSV} \n - {OUTPUT_LOGISTICS_CSV} \n - {OUTPUT_TACTICAL_CSV}")

if __name__ == "__main__":
    main()