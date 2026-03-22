import os
import json
import re
from pypdf import PdfReader
import google.generativeai as genai

# --- Simple .env loader ---
def load_env(env_path):
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip('"').strip("'")

def extract_text_from_pdf(pdf_path):
    """Extracts text from the PDF file."""
    print(f"Reading PDF from: {pdf_path}")
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"
    return full_text

def parse_with_llm(text):
    """Parses the text using Google Gemini Flash."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY not found. Skipping LLM extraction.")
        return None

    print(f"Calling Gemini Flash with text length: {len(text)} chars...")
    try:
        genai.configure(api_key=api_key)
        # Use a stable model version
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        prompt = """
        You are a Disaster Relief Operations Specialist. Extract comprehensive operational and relief guidelines from the provided text.
        
        The goal is to drive an AI Agent that role-plays 'Logistics Chief' and 'Tactical Commander'.
        
        Return ONLY a raw JSON object with this key-value structure:
        
        {
            "source_document": "Guidelines on Relief during disaster.pdf",
            "logistics_standards": {
                "water_requirements": {
                    "drinking_liters_person_day": <number>,
                    "hygiene_liters_person_day": <number>,
                    "notes": <string>
                },
                "food_nutrition": {
                    "components": [<list>],
                    "calories_per_person": <number or "As per ICDS">,
                    "special_groups": <string description of needs for kids/mothers>
                },
                "shelter_specs": {
                    "area_sqm_person": <number>,
                    "infrastructure": [<list of requirements e.g. lighting, ventilation>],
                    "site_selection_criteria": [<list>]
                },
                "sanitation_hygiene": {
                    "toilets_per_person_ratio": "1:<number>",
                    "distance_rules": <string>,
                    "waste_management": <string>
                },
                "medical_supplies": {
                    "essential_kits": [<list>],
                    "ambulance_deployment": <string rule>
                }
            },
            "tactical_protocols": {
                "rescue_operations": {
                    "priority_groups": [<list>],
                    "team_composition": <string>
                },
                "camp_management": {
                    "registration_process": <string>,
                    "security_protocols": [<list>]
                },
                "transport_logistics": {
                    "vehicle_types": [<list if mentioned>],
                    "access_rules": <string>
                }
            },
            "allocations_heuristic": {
                 "description": "Simplified math for AI calculation",
                 "food_unit_name": "Packet", 
                 "food_per_person": 1,
                 "water_liters_per_person": <total water>,
                 "people_per_toilet": <number>
            }
        }
        
        Capture ALL quantitative values (liters, sq.meters, ratios) and qualitative operational rules.
        If a specific value is missing, infer a standard humanitarian norm (Sphere standards) but mark it as "(Inferred)".
        Text Context:
        """
        
        # Truncate text if too long (Gemini Flash has ~1M context but good practice)
        response = model.generate_content(prompt + text)
        
        # Clean response
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(cleaned_text)
        print("✅ LLM Extraction Successful.")
        return data

    except Exception as e:
        print(f"❌ LLM Parsing Failed: {e}")
        # Build logic to fallback through list if needed, or just fail
        return None

def parse_guidelines_regex(text):
    """Parses the text to find key resource standards using specific regex patterns."""
    print("Parsing text with Regex fallback...")
    
    standards = {
        "shelter": {"area_per_person_sqm": 3.5}, # Default fallback
        "food": {},
        "water": {"drinking_liters_per_person_day": 3.0, "hygiene_liters_per_person_day": 15.0}, # Defaults
        "sanitation": {"persons_per_toilet": 30}, # Default
        "medical": {}
    }

    # --- Regex Extraction Logic ---
    
    # 1. Water Standards
    # Searching for patterns like "3 liters per person"
    water_match = re.search(r"(\d+(\.\d+)?)\s*liters?\s*per\s*person.*drinking", text, re.IGNORECASE)
    if water_match:
        standards["water"]["drinking_liters_per_person_day"] = float(water_match.group(1))

    # 2. Shelter Standards
    # Searching for "3.5 sq.m"
    shelter_match = re.search(r"(\d+(\.\d+)?)\s*sq\.?m\.?.*covered\s*area", text, re.IGNORECASE)
    if shelter_match:
        standards["shelter"]["area_per_person_sqm"] = float(shelter_match.group(1))

    # 3. Sanitation Standards
    # Searching for "One toilet for 30 persons"
    sanitation_match = re.search(r"One\s*toilet\s*for\s*(\d+)\s*persons", text, re.IGNORECASE)
    if sanitation_match:
        standards["sanitation"]["persons_per_toilet"] = int(sanitation_match.group(1))

    # --- Populating Detailed Structure ---
    
    final_output = {
        "source_document": "Regex Extraction (Guidelines on Relief during disaster.pdf)",
        "standards": {
            "shelter": {
                "area_per_person_sqm": standards["shelter"]["area_per_person_sqm"],
                "requirements": ["Basic lighting", "Ventilation", "Separate rooms for vulnerable groups"]
            },
            "food": {
                "description": "Nutritionally adequate cooked food compatible with local habits.",
                "components": ["Cereals", "Pulses", "Egg", "Fat/Oil"],
                "specific_needs": "ICDS norms for children and lactating mothers",
                "safety": ["Disposable plates/glasses preferred", "Date of expiry check", "Hygiene at kitchens"]
            },
            "water": {
                "drinking_liters_per_person_day": standards["water"]["drinking_liters_per_person_day"],
                "hygiene_liters_per_person_day": 17.5, # Often derived or listed separately
                "total_liters_per_person_day": standards["water"]["drinking_liters_per_person_day"] + 17.5,
                "quality_control": ["Chlorination", "Daily sample testing", "RO plant where possible"]
            },
            "sanitation": {
                "persons_per_toilet": standards["sanitation"]["persons_per_toilet"],
                "distance_from_camp_meters": {"min": 10, "max": 50},
                "requirements": ["Separate toilets for men/women", "Proper illumination", "Disinfectants"]
            },
            "medical": {
                "staffing": "Mobile medical team with doctors/paramedics (24x7)",
                "equipment": ["Ambulance stationed at camp", "Adequate inventory of medicines"],
                "protocols": ["Rapid health assessment", "Triaging in mass casualty", "Psychosocial counselling"]
            }
        },
        "allocations": {
            "food_packets": {
                "unit": "Packet",
                "per_person_per_day": 1,
                "note": "Assumed 1 packet = Daily ration including cereals/pulses as per guidelines"
            },
            "water": {
                "unit": "Liters",
                "per_person_per_day": standards["water"]["drinking_liters_per_person_day"],
                "note": "Drinking water only. Gross water need is ~20L/person"
            },
            "medical_kits": {
                "unit": "Kit",
                "per_x_people": 50,
                "note": "Derived heuristic for 'Adequate inventory'"
            },
            "toilets": {
                "unit": "Unit",
                "per_x_people": standards["sanitation"]["persons_per_toilet"],
                "note": "Explicit guideline"
            }
        }
    }
    return final_output

def main():
    # Setup Paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(base_dir, "..", "..", "..")) # Digital.../
    
    # Load .env
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        print(f"Loading environment from {env_path}")
        load_env(env_path)
    
    pdf_path = os.path.join(project_root, "Guidelines on Relief during disaster.pdf")

    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found at {pdf_path}")
        return

    # Extract & Parse
    # try:
    raw_text = extract_text_from_pdf(pdf_path)
    
    # Try LLM First
    data = parse_with_llm(raw_text)
    
    if not data:
        print("❌ LLM Extraction failed and Fallback is disabled. Exiting.")
        return

    # Save JSON
    output_path = os.path.join(base_dir, "resource_guidelines.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"Successfully updated resource guidelines at: {output_path}")
        
    # except Exception as e:
    #     print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
