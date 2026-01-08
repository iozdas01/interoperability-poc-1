import os
import re
import pandas as pd

# Define which metadata fields to search for
METADATA_FIELDS = [
    'WERKSTOFF',
    'PTC_MATERIAL_NAME',
    'TYP',
    'SET_MASSE_KG',
    'SMT_DFLT_BEND_ANGLE'
]

def extract_metadata_lines(lines, field):
    # Returns all lines containing the field in a DESCRIPTIVE_REPRESENTATION_ITEM
    pattern = rf"DESCRIPTIVE_REPRESENTATION_ITEM\('{field}','(.*?)'\)"
    return [line.strip() for line in lines if re.search(pattern, line)]

def is_assembly(lines):
    # Heuristic: more than one PRODUCT_DEFINITION or line with 'ASSEMBLY'
    prod_defs = sum(1 for line in lines if 'PRODUCT_DEFINITION' in line)
    if prod_defs > 1:
        return True
    if any('ASSEMBLY' in line.upper() for line in lines):
        return True
    return False

def analyze_step_files(folder_path):
    records = []
    for filename in os.listdir(folder_path):
        if not filename.lower().endswith(('.stp', '.step')):
            continue
        file_path = os.path.join(folder_path, filename)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        row = {'STEP File': filename}
        row['Is Assembly'] = is_assembly(lines)
        for field in METADATA_FIELDS:
            matches = extract_metadata_lines(lines, field)
            row[field] = "\n".join(matches) if matches else ""
        records.append(row)
    return records

def main():
    folder = r'exploring-files/Raw-Data-UW'  # Updated to your folder
    results = analyze_step_files(folder)
    df = pd.DataFrame(results)
    df.to_excel('exploring-files/step_metadata_report.xlsx', index=False)
    print("Excel file 'exploring-files/step_metadata_report.xlsx' created.")

if __name__ == "__main__":
    main()
