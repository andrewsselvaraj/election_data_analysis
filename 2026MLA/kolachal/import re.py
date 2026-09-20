import re
import pandas as pd
import os

def parse_polling_stations(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"OCR text file not found at: {file_path}")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split content by lines
    lines = content.split('\n')
    
    records = []
    current_record = None
    
    # Pattern to match the start of a row, e.g., "1 1" or "10 10 Govt. Middle School..."
    # A line must start with two identical numbers.
    row_start_pat = re.compile(r'^\s*(\d+)\s+(\d+)(?:\s+(.*))?$')
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # Check if this line starts a new row
        m = row_start_pat.match(line_stripped)
        if m and m.group(1) == m.group(2):
            # If we had a previous record, process and save it
            if current_record:
                records.append(process_record(current_record))
            
            part_no = m.group(1)
            ps_no = m.group(2)
            extra_text = m.group(3) or ""
            
            current_record = {
                'part_no': part_no,
                'ps_no': ps_no,
                'lines': [extra_text] if extra_text else []
            }
        else:
            if current_record is not None:
                current_record['lines'].append(line_stripped)
                
    # Add the last record
    if current_record:
        records.append(process_record(current_record))
        
    return records

def process_record(rec):
    part_no = rec['part_no']
    ps_no = rec['ps_no']
    lines = rec['lines']
    
    # Find where the Polling Area (Column 4) starts.
    # The first line of Polling Area always starts with or contains a region qualifier like (R.V), (T.P), etc.
    col4_start_idx = -1
    region_pat = re.compile(r'\b(?:R\.V|T\.P|P|r\.v|R\. V|T\. P|R\.,V|R\.V\.)\b')
    
    for idx, line in enumerate(lines):
        if region_pat.search(line):
            col4_start_idx = idx
            break
            
    if col4_start_idx != -1:
        col3_lines = lines[:col4_start_idx]
        col4_lines = lines[col4_start_idx:]
    else:
        # Fallback if no region qualifier is found
        col3_lines = lines
        col4_lines = []
        
    col3_text = " ".join(col3_lines).strip()
    col4_text = " ".join(col4_lines).strip()
    
    # Remove "All Voters" (Column 5) from the end of col4_text if present
    all_voters_pat = re.compile(r'\s*,?\s*All\s+Voters\b.*$', re.IGNORECASE)
    col4_text = all_voters_pat.sub('', col4_text).strip()
    
    # Clean up multiple whitespaces
    col3_text = re.sub(r'\s+', ' ', col3_text)
    col4_text = re.sub(r'\s+', ' ', col4_text)
    
    return {
        'Part No.': int(part_no),
        'PS No.': int(ps_no),
        'Location and Name of the building': col3_text,
        'Polling Area': col4_text,
        'Polling Station Type': 'All Voters'
    }

def main():
    input_file = "polling_ocr.txt"
    output_file = "polling_stations.xlsx"
    
    print(f"Parsing polling stations from '{input_file}'...")
    try:
        records = parse_polling_stations(input_file)
        df = pd.DataFrame(records)
        
        # Reorder columns to match the original document
        columns_order = [
            'Part No.', 
            'PS No.', 
            'Location and Name of the building', 
            'Polling Area', 
            'Polling Station Type'
        ]
        df = df[columns_order]
        
        # Export to Excel
        df.to_excel(output_file, index=False)
        print(f"Successfully converted {len(df)} records!")
        print(f"Saved to Excel file: '{output_file}'")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
 