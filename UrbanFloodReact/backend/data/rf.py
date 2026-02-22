import requests
import pdfplumber
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
import os

# --- CONFIGURATION ---
BASE_URL = "https://www.ksndmc.org/en/Root/DownloadFile"
PATH_TEMPLATE = r"\\192.168.2.21\e$\KSNDMC REPORTS\Daily Reports\Rainfall Pattern\2025\DTRP_{date}.pdf"
FILENAME_TEMPLATE = "Rainfall Pattern_{date}.pdf"

# Set your date range here
START_DATE = datetime(2025, 7, 1)
END_DATE = datetime(2025, 7, 31)
RAW_FILE = "Raw_Data_Dump.xlsx"
CLEAN_FILE = "Bengaluru_Rainfall_24Hrs_June.xlsx"

def generate_dates(start, end):
    curr = start
    while curr <= end:
        yield curr.strftime("%d-%m-%Y")
        curr += timedelta(days=1)

def download_pdf(date_str):
    params = {"path": PATH_TEMPLATE.format(date=date_str), "fileName": FILENAME_TEMPLATE.format(date=date_str)}
    print(f"\n[DEBUG] Downloading: {date_str}")
    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        if response.status_code == 200 and len(response.content) > 5000:
            return BytesIO(response.content)
        return None
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        return None

def extract_raw_rows(pdf_stream):
    rows = []
    found_start = False
    try:
        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                text = (page.extract_text() or "").upper().replace("-", "")
                if "HOBLIWISE RAINFALL PATTERN" in text:
                    found_start = True
                if found_start:
                    # Using lattice strategy to keep the column structure rigid
                    table = page.extract_table({"vertical_strategy": "lines", "horizontal_strategy": "lines"})
                    if table: rows.extend(table)
    except Exception as e:
        print(f"[ERROR] PDF Parse error: {e}")
    return rows

def clean_and_filter_data(raw_excel_path, output_path):
    print(f"\n[DEBUG] Starting Clean-up Process...")
    all_dates_data = []
    
    # Load all sheets
    raw_data_dict = pd.read_excel(raw_excel_path, sheet_name=None, header=None)
    
    for sheet_name, df in raw_data_dict.items():
        # Find the header row by searching for 'DISTRICT' and 'HOBLI'
        header_idx = None
        for i, row in df.iterrows():
            row_str = " ".join(map(str, row.values)).upper()
            if "DISTRICT" in row_str and "HOBLI" in row_str:
                header_idx = i
                break
        
        if header_idx is None:
            continue

        # Slice from the data rows (usually 2-3 rows below the header title due to nested headers)
        # We look for the first row that starts with a number (Sl.No)
        data_start_idx = header_idx
        for i in range(header_idx, len(df)):
            if str(df.iloc[i, 0]).strip().isdigit():
                data_start_idx = i
                break

        df_clean = df.iloc[data_start_idx:].reset_index(drop=True)
        
        # 1. Fill down District (Col 1) and Taluk (Col 2) to handle merged cells
        df_clean.iloc[:, [1, 2]] = df_clean.iloc[:, [1, 2]].ffill()
        
        # 2. Filter for Bengaluru
        df_clean[1] = df_clean[1].astype(str).str.upper().str.strip()
        mask = df_clean[1].str.contains("BENGALURU URBAN|BENGALURU RURAL", na=False)
        filtered_df = df_clean[mask].copy()
        
        if not filtered_df.empty:
            # 3. SELECTING COLUMNS BASED ON YOUR REFERENCE FILE:
            # Col 1: District, Col 2: Taluk, Col 3: Hobli
            # Col 7: 24h Normal, Col 8: 24h Actual, Col 9: 24h %Dep
            final_cols = filtered_df.iloc[:, [1, 2, 3, 7, 8, 9]].copy()
            final_cols.columns = ['District', 'Taluk', 'Hobli', '24h_Normal_mm', '24h_Actual_mm', '24h_Dep_Pct']
            
            # Clean numeric values (remove newlines or extra dots common in OCR/PDFs)
            for col in ['24h_Normal_mm', '24h_Actual_mm', '24h_Dep_Pct']:
                final_cols[col] = final_cols[col].astype(str).str.replace(r'\n', '', regex=True).str.strip()

            # Add Date
            date_val = sheet_name.replace("RF_", "")
            final_cols.insert(0, 'Date', date_val)
            all_dates_data.append(final_cols)
            print(f"      - [SUCCESS] Extracted {len(final_cols)} Bengaluru rows for {date_val}")

    if all_dates_data:
        final_output = pd.concat(all_dates_data, ignore_index=True)
        final_output.to_excel(output_path, index=False)
        print(f"\n[FINISHED] Process Complete. Saved to: {output_path}")
    else:
        print("\n[WARNING] No Bengaluru data found. Check if the column indices (7, 8, 9) shifted.")

# --- EXECUTION ---
with pd.ExcelWriter(RAW_FILE, engine='openpyxl') as writer:
    for date_str in generate_dates(START_DATE, END_DATE):
        pdf_stream = download_pdf(date_str)
        if pdf_stream:
            raw_rows = extract_raw_rows(pdf_stream)
            if raw_rows:
                pd.DataFrame(raw_rows).to_excel(writer, sheet_name=f"RF_{date_str.replace('-','')}", index=False, header=False)

clean_and_filter_data(RAW_FILE, CLEAN_FILE)
