#!/usr/bin/env python3
"""
Combined LLM Script
===================
This script takes the parsed data from the master parser and uses LLM to:
1. Read existing JSON files containing structured metadata (PDF, QIF, STEP)
2. Read existing TXT files for additional context
3. Validate metadata consistency across QIF and STEP sources
4. Generate unified DXF annotation JSON instructions for each part
5. Output JSON files with annotation instructions (does not modify original DXF files)

It combines the functionality of llm-script.py and llm-pdf-csv.py by using
the already-parsed and organized data from the master parser instead of
re-parsing raw files.
"""

import json
import openai
from pathlib import Path
import sys

# Configuration
PARSED_RESULTS_DIR = Path("execute/parsed-results")
LLM_RESULTS_DIR = Path("execute/Zero-Shot/llm-results-zeroshot")
LLM_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CAM = "CypCut"  # Default CAM software

def get_output_dir(subdirectory: str) -> Path:
    """Get the output directory based on the subdirectory (AutoCAD or Inventor)."""
    # Convert to lowercase to match existing structure
    output_dir = LLM_RESULTS_DIR / subdirectory.lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir

PROMPT_TEMPLATE = """
You are "DXF-Meta-Annotator", a tool that provides a JSON file carrying instructions to insert manufacturing metadata into DXF files compatible with CAM software.

INPUTS YOU RECEIVE
(the following information is contained in one text and one json file per part name):
• QIF metadata
• STEP metadata
• PDF / CSV free text

OBJECTIVE
Extract material type (string), thickness (mm) (numeric), and part-ID (string or numeric), then describe how they must be embedded in the DXF so that any CAM system can read or fall back on them.

MANDATORY STORAGE RULES

1. Header Variables
   • $USERI1 (70, integer): store the numeric portion of the part-ID (extract digits from filename; if none, set 0)
   • $USERR1 (40, real): store thickness in millimetres
   Constraints:
   • Do not use any other $USER* variables (no string header slots exist).

2. Comment Records
   • Use group code 999 for comments
   • Each comment ≤ 256 characters; include full part-ID string, material, thickness_mm
   • Placement keys:
     o "file_start": immediately before first 0 SECTION
     o "file_end": immediately before final 0 EOF
   • Examples:

     // Top-of-file:
     999
     Material: AISI 304, Thickness: 3.0mm, Part ID: ABC-XYZ
     0
     SECTION
     2
     HEADER
     ... rest of HEADER ...

     // Bottom-of-file:
     0
     ENDSEC
     999
     Material: AISI 304, Thickness: 3.0mm, Part ID: ABC-XYZ
     0
     EOF

3. Layer Naming
   • In the TABLES section, locate the first 0 LAYER record (Layer 0)
   • Rename to: MAT_<material>__THK_<thickness_mm>mm__PART_<part_id>
   • Obey char limits (31 for R12, 255 for R13+); avoid `<>/\":;?*|=`
   • Placement key: "inside_LAYER_record_0"

5. Geometry Safety
   • Do not modify geometry or entity tags; only metadata fields

OUTPUT FORMAT (JSON)
Return a single object with keys:

{{
  "header_updates": [
    {{"var": "$USERI1", "gcode": 70, "value": <int>, "placement": "before_endsec"|"update_existing"}},
    {{"var": "$USERR1", "gcode": 40, "value": <float>, "placement": "before_endsec"|"update_existing"}}
  ],
  "layer_renames": [
    {{"index": 0, "new": "MAT_<material>__THK_<thickness_mm>mm__PART_<part_id>", "placement": "inside_LAYER_record_0"}}
  ],
  "add_comments": [
    {{"comment": "Material: <material>, Thickness: <thickness_mm>mm, Part ID: <full_part_id>", "placement": "file_start"|"file_end"}}
  ],
  "xdata_entries": [
    {{"entity_handle": "<handle>", "app_id": "DXFMETA", "entries": [{{"gcode": 1000, "value": "PART_ID=<full_part_id>"}}], "placement": "append_to_entity"}}
  ]
}}

Do not include extra keys, DXF snippets, or prose.

CONTEXT PRIORITY FOR METADATA VALUES
(1) QIF block = most reliable for material + thickness
(2) STEP block = most reliable backup for thickness (derived from 3-D geometry)
(3) PDF / CSV = use only if a value is missing from QIF/STEP; extract
    • Part number (alphanumeric)
    • Material designation (e.g., "AISI 304", "Al 6061")
    • Thickness in mm (numeric value followed by "mm", "millimetre", etc.)

RETURN ONLY THE JSON OBJECT

--- QIF METADATA ---
{qif_metadata}

--- STEP METADATA ---
{step_metadata}

--- PDF/CSV TEXT ---
{pdf_csv_text}

--- TARGET CAM SOFTWARE ---
{cam}
"""

def ask_llm(prompt: str) -> dict:
    """Call the LLM API to get DXF annotation instructions."""
    client = openai.OpenAI()
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                { "role": "system", "content": "You are a DXF annotation expert." },
                { "role": "user", "content": prompt }
            ],
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        print(f"LLM Response: {content[:200]}...")  # Show first 200 chars
        
        if not content:
            raise ValueError("LLM returned empty response")
        
        # Try to extract JSON from markdown code blocks if present
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            json_content = json_match.group(1)
            return json.loads(json_content)
        
        # If no code block, try to parse the entire content as JSON
        return json.loads(content)
        
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        print(f"Full LLM response: {content}")
        raise
    except Exception as e:
        print(f"LLM API Error: {e}")
        raise

def load_parsed_data(subdirectory: str) -> dict:
    """Load all parsed data for a subdirectory."""
    data_dir = PARSED_RESULTS_DIR / subdirectory
    
    if not data_dir.exists():
        print(f"❌ Parsed results directory not found: {data_dir}")
        return {}
    
    all_data = {}
    
    # Load all JSON files (excluding DXF and summary files)
    for json_file in data_dir.glob("*.json"):
        part_name = json_file.stem
        
        # Skip summary and DXF files (we'll handle DXF separately)
        if part_name.endswith("_summary") or part_name.endswith("_dxf"):
            continue
            
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_data[part_name] = data
                print(f"✅ Loaded JSON data for {part_name}")
        except Exception as e:
            print(f"❌ Error loading {json_file}: {e}")
    
    return all_data

def load_txt_data(subdirectory: str) -> dict:
    """Load TXT files for additional context."""
    data_dir = PARSED_RESULTS_DIR / subdirectory
    txt_data = {}
    
    # Load TXT files
    for txt_file in data_dir.glob("*.txt"):
        part_name = txt_file.stem
        
        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                content = f.read()
                txt_data[part_name] = content
                print(f"✅ Loaded TXT data for {part_name}")
        except Exception as e:
            print(f"❌ Error loading TXT {txt_file}: {e}")
    
    return txt_data

def validate_metadata_consistency(part_name: str, part_data: dict) -> tuple[bool, dict, str]:
    """
    Validate that metadata is consistent across all sources.
    Returns: (is_consistent, unified_metadata, error_message)
    """
    sources = {}
    errors = []
    
    # Extract metadata from different sources using the parsed data
    if "pdf_data" in part_data:
        # For PDF data, we'll use the content for LLM but not extract metadata here
        # since the master parser already extracted the text
        sources["PDF/CSV"] = {"content": part_data["pdf_data"]}
    
    if "qif_data" in part_data:
        sources["QIF"] = {
            "material": part_data["qif_data"].get("material"),
            "thickness": part_data["qif_data"].get("thickness"),
            "part_id": part_data["qif_data"].get("part_id")
        }
    
    if "step_data" in part_data:
        sources["STEP"] = {
            "material": None,  # STEP doesn't provide material
            "thickness": part_data["step_data"].get("thickness"),
            "part_id": part_data["step_data"].get("part_id")
        }
    
    # Check if we have any metadata
    if not sources:
        return False, {}, "No metadata found in any source"
    
    # Extract unique values for each field
    materials = set()
    thicknesses = set()
    part_ids = set()
    
    def normalize_thickness(thickness_value):
        """Normalize thickness to numeric value for comparison."""
        if not thickness_value or thickness_value == "N/A":
            return None
        
        # Convert to string and extract numeric value
        thickness_str = str(thickness_value).lower()
        
        # Remove common units and extract number
        import re
        # Match numbers with optional decimal places, followed by optional units
        match = re.search(r'(\d+\.?\d*)', thickness_str)
        if match:
            return float(match.group(1))
        return None
    
    for source_name, metadata in sources.items():
        if source_name == "PDF/CSV":
            # Skip PDF/CSV for metadata validation since it's raw text
            continue
        if metadata.get("material") and metadata["material"] != "N/A":
            materials.add(metadata["material"])
        if metadata.get("thickness") and metadata["thickness"] != "N/A":
            normalized_thickness = normalize_thickness(metadata["thickness"])
            if normalized_thickness is not None:
                thicknesses.add(normalized_thickness)
        if metadata.get("part_id") and metadata["part_id"] != "N/A":
            part_ids.add(str(metadata["part_id"]))
    
    # Check for inconsistencies
    if len(materials) > 1:
        errors.append(f"Material mismatch: {materials}")
    
    if len(thicknesses) > 1:
        errors.append(f"Thickness mismatch: {thicknesses}")
    
    if len(part_ids) > 1:
        errors.append(f"Part ID mismatch: {part_ids}")
    
    # Create unified metadata (use the first non-N/A value for each field)
    unified_metadata = {}
    
    # Get material (prioritize QIF over PDF/CSV)
    if "QIF" in sources and sources["QIF"].get("material") and sources["QIF"]["material"] != "N/A":
        unified_metadata["material"] = sources["QIF"]["material"]
    else:
        unified_metadata["material"] = "N/A"
    
    # Get thickness (prioritize STEP over QIF)
    if "STEP" in sources and sources["STEP"].get("thickness") and sources["STEP"]["thickness"] != "N/A":
        unified_metadata["thickness"] = sources["STEP"]["thickness"]
    elif "QIF" in sources and sources["QIF"].get("thickness") and sources["QIF"]["thickness"] != "N/A":
        unified_metadata["thickness"] = sources["QIF"]["thickness"]
    else:
        unified_metadata["thickness"] = "N/A"
    
    # Get part ID (use any source)
    if "QIF" in sources and sources["QIF"].get("part_id") and sources["QIF"]["part_id"] != "N/A":
        unified_metadata["part_id"] = sources["QIF"]["part_id"]
    elif "STEP" in sources and sources["STEP"].get("part_id") and sources["STEP"]["part_id"] != "N/A":
        unified_metadata["part_id"] = sources["STEP"]["part_id"]
    else:
        unified_metadata["part_id"] = part_name  # Use filename as fallback
    
    # Add source information
    unified_metadata["sources"] = sources
    unified_metadata["validation_errors"] = errors
    
    is_consistent = len(errors) == 0
    error_message = "; ".join(errors) if errors else ""
    
    return is_consistent, unified_metadata, error_message

def process_part(part_name: str, part_data: dict, txt_data: dict) -> dict:
    """Process a single part and generate LLM response with DXF structure."""
    print(f"\nProcessing part: {part_name}")
    
    # Validate metadata consistency
    is_consistent, unified_metadata, error_message = validate_metadata_consistency(part_name, part_data)
    
    if not is_consistent:
        error_result = {
            "error": f"Metadata inconsistency: {error_message}",
            "part_name": part_name,
            "unified_metadata": unified_metadata,
            "validation_errors": unified_metadata.get("validation_errors", [])
        }
        print(f"❌ Metadata inconsistency for {part_name}: {error_message}")
        return error_result
    
    # Extract data from different sources
    pdf_csv_text = ""
    
    # Get PDF/CSV text from the parsed data
    if "pdf_data" in part_data:
        for file_type, data in part_data["pdf_data"].items():
            if "content" in data:
                pdf_csv_text += f"--- {file_type.upper()} CONTENT ---\n"
                pdf_csv_text += data["content"] + "\n\n"
    
    # Get TXT content for additional context
    if part_name in txt_data:
        pdf_csv_text += f"--- TXT CONTENT ---\n"
        pdf_csv_text += txt_data[part_name] + "\n\n"
    
    # Prepare data for LLM
    unified_json = json.dumps(unified_metadata, indent=2)
    
    # Create prompt for DXF annotation
    prompt = PROMPT_TEMPLATE.format(
        qif_metadata=unified_json,
        step_metadata=unified_json,
        pdf_csv_text=pdf_csv_text if pdf_csv_text else "No PDF/CSV text available",
        cam=CAM
    )
    
    # Call LLM to get annotation instructions
    try:
        annotation_instructions = ask_llm(prompt)
        
        # Add metadata to result
        result = {
            "part_name": part_name,
            "unified_metadata": unified_metadata,
            "validation_status": "consistent",
            "annotation_instructions": annotation_instructions
        }
        
        return result
    except Exception as e:
        print(f"❌ Error processing {part_name}: {e}")
        return {
            "error": str(e),
            "part_name": part_name,
            "unified_metadata": unified_metadata,
            "validation_status": "consistent" if is_consistent else "inconsistent"
        }

def main():
    """Main function to process all parts."""
    print("🚀 COMBINED LLM - Processing all parsed data")
    print("=" * 60)
    
    # Process both AutoCAD and Inventor subdirectories
    subdirectories = ["AutoCAD", "Inventor"]
    
    all_success = True
    
    for subdirectory in subdirectories:
        print(f"\n{'='*40}")
        print(f"Processing subdirectory: {subdirectory}")
        print(f"{'='*40}")
        
        # Load all parsed data
        print(f"\nLoading parsed data from: {PARSED_RESULTS_DIR / subdirectory}")
        parsed_data = load_parsed_data(subdirectory)
        
        if not parsed_data:
            print(f"❌ No parsed data found for {subdirectory}!")
            all_success = False
            continue
        
        # Load TXT data
        print(f"\nLoading TXT data for {subdirectory}...")
        txt_data = load_txt_data(subdirectory)
        
        # Process each part
        print(f"\nProcessing {len(parsed_data)} parts for {subdirectory}...")
        results = {}
        
        for part_name, part_data in parsed_data.items():
            try:
                result = process_part(part_name, part_data, txt_data)
                results[part_name] = result
                
                # Save individual result
                output_path = LLM_RESULTS_DIR / subdirectory.lower() / f"{part_name}_llm_response.json"
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"✅ Saved LLM response: {output_path.name}")
                
            except Exception as e:
                print(f"❌ Error processing {part_name}: {e}")
                results[part_name] = {"error": str(e)}
        
        # Save combined results for this subdirectory
        combined_output_path = LLM_RESULTS_DIR / subdirectory.lower() / f"{subdirectory.lower()}_all_llm_responses.json"
        combined_output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(combined_output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Print summary for this subdirectory
        success_count = sum(1 for r in results.values() if "error" not in r)
        error_count = len(results) - success_count
        
        print(f"\n{'='*40}")
        print(f"🎯 {subdirectory.upper()} COMPLETED")
        print(f"{'='*40}")
        print(f"Parts processed: {len(results)}")
        print(f"Successful: {success_count}")
        print(f"Errors: {error_count}")
        print(f"Output location: {LLM_RESULTS_DIR / subdirectory.lower()}")
        print(f"Combined results: {combined_output_path.name}")
        
        if error_count > 0:
            all_success = False
    
    # Print overall summary
    print(f"\n{'='*60}")
    print("🎯 OVERALL COMBINED LLM COMPLETED")
    print(f"{'='*60}")
    print(f"Subdirectories processed: {', '.join(subdirectories)}")
    print(f"Output location: {LLM_RESULTS_DIR}")
    
    return all_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 