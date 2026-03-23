import pdfplumber
import json
import re
import os

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PDF_PATH = os.path.join(PROJECT_ROOT, "Data_collection_format_for_Districts.pdf")
OUTPUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resource_definitions.json")

def clean_text(text):
    if not text: return ""
    return str(text).replace('\n', ' ').strip()

def extract_resources_from_pdf():
    print(f"Extracting resource definitions from: {PDF_PATH}")
    
    if not os.path.exists(PDF_PATH):
        print(f"Error: {PDF_PATH} not found.")
        return

    resource_data = {}  # Format: { "Activity Name": { "Category Name": [Item List] } }
    
    current_activity = "Unknown Activity"
    current_category = "General"
    
    with pdfplumber.open(PDF_PATH) as pdf:
        # User specified pages 3 to 15 (index 2 to 14)
        # We'll go a bit safer and check content to decide end, but 2-14 is the instruction.
        for page_idx in range(2, 15): 
            if page_idx >= len(pdf.pages): break
            
            page = pdf.pages[page_idx]
            tables = page.extract_tables()
            
            for table in tables:
                for row in table:
                    # Clean row data
                    col0 = clean_text(row[0])
                    
                    # 1. Detect Activity Header
                    # e.g. "ACTIVITY NAME------SEARCH AND RESCUE"
                    if "ACTIVITY NAME" in col0.upper():
                        # Extract activity name
                        parts = re.split(r'[-–]+', col0)
                        if len(parts) > 1:
                            act_name = parts[-1].strip()
                            current_activity = act_name.title()
                            if current_activity not in resource_data:
                                resource_data[current_activity] = {}
                            # Reset category on new activity? Usually yes
                            current_category = "General"
                        continue

                    # 2. Detect Category Header
                    # e.g. "Category Name - Cutters"
                    if "CATEGORY NAME" in col0.upper():
                        parts = re.split(r'[-–]+', col0)
                        if len(parts) > 1:
                            cat_name = parts[-1].strip()
                            current_category = cat_name.title()
                            if current_activity not in resource_data:
                                resource_data[current_activity] = {}
                            if current_category not in resource_data[current_activity]:
                                resource_data[current_activity][current_category] = []
                        continue
                        
                    # 3. Detect Item Row
                    # Looks like: ['1.', '101', 'Gas Cutters', '']
                    # Criteria: Col 0 is number/dot, Col 1 is number/code, Col 2 has text
                    if len(row) > 2:
                        # Check header row
                        if "ITEM NAME" in str(row[2]).upper(): continue
                        
                        # Likely an item
                        item_name = clean_text(row[2])
                        item_code = clean_text(row[1])

                        # Make sure it looks valid (Code is typically numeric, but sometimes alphanumeric)
                        # Name must be significant
                        if item_name and len(item_name) > 2 and item_code:
                            
                            # Ensure struct exists
                            if current_activity not in resource_data:
                                resource_data[current_activity] = {}
                            if current_category not in resource_data[current_activity]:
                                resource_data[current_activity][current_category] = []
                            
                            # Create entry object
                            entry = {
                                "code": item_code,
                                "name": item_name
                            }

                            # Add unique
                            exists = False
                            for existing in resource_data[current_activity][current_category]:
                                if isinstance(existing, dict) and existing.get('code') == item_code:
                                    exists = True
                                    break
                                elif isinstance(existing, str) and existing == item_name:
                                    exists = True 
                                    break
                            
                            if not exists:
                                resource_data[current_activity][current_category].append(entry)

    # Save to JSON
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(resource_data, f, indent=4)
        
    print(f"Extraction complete. Saved {len(resource_data)} activities to {OUTPUT_JSON}")
    
    # Flatten strictly for "Logistics" vs "Tactical" classification later if needed
    # (Just printing stats for now)
    count = 0
    for act in resource_data:
        for cat in resource_data[act]:
            count += len(resource_data[act][cat])
    print(f"Total Unique Items Identified: {count}")

if __name__ == "__main__":
    extract_resources_from_pdf()