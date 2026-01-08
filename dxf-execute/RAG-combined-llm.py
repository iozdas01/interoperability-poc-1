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

import json
import openai
from pathlib import Path
import sys
from typing import Union, List, Dict

# Configuration
PARSED_RESULTS_DIR = Path("execute/parsed-results")
LLM_RESULTS_DIR = Path("execute/RAG+Zero-Shot/llm-results-rag")
LLM_INPUTS_RAG_ZS_DIR = Path("execute/RAG+Zero-Shot/llm-inputs-rag-zs")
CAM = "CypCut"  # Default CAM software

PROMPT_TEMPLATE = """
You are a DXF annotation expert. Your job is to add manufacturing metadata to DXF files.

ANALYZE THE DXF STRUCTURE FIRST:
Look at the CURRENT DXF STRUCTURE to see what already exists:
- Does $USERR1 exist? What is its current value?
- Does $USERI1 exist? What is its current value?

IMPORTANT: In the DXF STRUCTURE JSON, look for the "header_variables" section. If you see "$USERR1" and "$USERI1" listed there, they EXIST and you should use "update_existing". If they are NOT listed, use "before_endsec".

EXTRACTION RULES:
1. Extract material, thickness (mm), and part-ID from the metadata
2. Use QIF data first, then STEP, then PDF/CSV as fallback
3. Use the RAG JSON context to enhance material and part information

PLACEMENT RULES:
- If $USERR1 exists: use "update_existing" to replace its value
- If $USERR1 doesn't exist: use "before_endsec" to add it
- If $USERI1 exists: use "update_existing" to replace its value
- If $USERI1 doesn't exist: use "before_endsec" to add it
- Use "entities_end" for comments (inserts at end of ENTITIES section, which is valid DXF structure)

OUTPUT FORMAT:
{{
  "header_updates": [
    {{"var": "$USERR1", "gcode": 40, "value": thickness_value, "placement": "update_existing" or "before_endsec"}},
    {{"var": "$USERI1", "gcode": 70, "value": part_id_numeric, "placement": "update_existing" or "before_endsec"}}
  ],
  "add_comments": [
    {{"comment": "Material: material, Thickness: thickness_mm, Part ID: part_id", "placement": "entities_end"}}
  ]
}}

IMPORTANT: You MUST include BOTH header_updates entries - one for $USERR1 (thickness) and one for $USERI1 (part_id_numeric). Do not skip either one.

IMPORTANT VALUE RULES:
- thickness_value: Must be a number (float) for group code 40
- part_id_numeric: Must be a number (integer) for group code 70. For simple numeric part_ids like "2", "123", "1234", use the full number (e.g., "2" becomes 2, "123" becomes 123). For complex part_ids like "3032-4", extract only the numeric part (becomes 3032). For "404-32", extract only the numeric part (becomes 404).
- material: Use the material name from metadata
- part_id: Use the full part_id string for comments


--- QIF METADATA ---
{qif_metadata}

--- STEP METADATA ---
{step_metadata}

--- PDF/CSV TEXT ---
{pdf_csv_text}

--- CURRENT DXF STRUCTURE (RAG JSON CONTEXT) ---
{rag_json_context}

--- TARGET CAM SOFTWARE ---
{cam}

RETURN ONLY THE JSON OBJECT
"""

def ask_llm(prompt: str) -> dict:
    """Call the LLM API to get DXF annotation instructions."""
    client = openai.OpenAI()
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                { "role": "system", "content": "You are a DXF annotation expert. Your job is to follow the given instructions and return a valid JSON object following the instructions provided." },
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
        
        # Try to find JSON object in the content (look for opening brace to closing brace)
        json_match = re.search(r'(\{.*\})', content, re.DOTALL)
        if json_match:
            json_content = json_match.group(1)
            return json.loads(json_content)
        
        # If no JSON found, try to parse the entire content as JSON
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



def load_dxf_json(part_name: str, subdirectory: str) -> dict:
    """Load the JSON representation of DXF file from parsed results."""
    # For RAG, we need to look in the correct subdirectory that contains the DXF JSON files
    parsed_results_dir = PARSED_RESULTS_DIR / subdirectory
    
    dxf_json_path = parsed_results_dir / f"{part_name}_dxf.json"
    
    if not dxf_json_path.exists():
        print(f"❌ No DXF JSON found for {part_name} at {dxf_json_path}")
        return {"error": f"No DXF JSON found for {part_name}"}
    
    try:
        with open(dxf_json_path, 'r', encoding='utf-8') as f:
            dxf_structure = json.load(f)
        print(f"✅ Loaded DXF JSON for {part_name}")
        return dxf_structure
    except Exception as e:
        print(f"❌ Error loading DXF JSON for {part_name}: {e}")
        return {"error": f"Failed to load DXF JSON: {e}"}

def load_rag_json_context(part_name: str, subdirectory: str) -> dict:
    """Load the JSON context from the llm-inputs-rag-zs directory in respective subdirectories."""
    # Look in the specific subdirectory (AutoCAD or Inventor)
    subdir_path = LLM_INPUTS_RAG_ZS_DIR / subdirectory
    
    if not subdir_path.exists():
        print(f"❌ Subdirectory {subdirectory} not found in {LLM_INPUTS_RAG_ZS_DIR}")
        return {"error": f"Subdirectory {subdirectory} not found"}
    
    # Look for files that match the part_name pattern with _material_traces.json suffix
    rag_files = list(subdir_path.glob(f"*{part_name}*_material_traces.json"))
    
    if not rag_files:
        # Try alternative patterns
        rag_files = list(subdir_path.glob(f"*{part_name}*.json"))
    
    if not rag_files:
        print(f"❌ No RAG JSON context found for {part_name} in {subdir_path}")
        return {"error": f"No RAG JSON context found for {part_name} in {subdirectory}"}
    
    # Use the first matching file
    rag_json_path = rag_files[0]
    
    try:
        with open(rag_json_path, 'r', encoding='utf-8') as f:
            rag_context = json.load(f)
        print(f"✅ Loaded RAG JSON context for {part_name} from {rag_json_path.name}")
        return rag_context
    except Exception as e:
        print(f"❌ Error loading RAG JSON context for {part_name}: {e}")
        return {"error": f"Failed to load RAG JSON context: {e}"}

def process_part(part_name: str, part_data: dict, txt_data: dict, subdirectory: str) -> dict:
    """Process a single part and generate LLM response."""
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
    
    # Load DXF JSON from parsed results for RAG context
    dxf_structure = load_dxf_json(part_name, subdirectory)
    
    if "error" in dxf_structure:
        print(f"❌ Error loading DXF JSON: {dxf_structure['error']}")
        return {"error": dxf_structure["error"]}
    
    print(f"✅ Loaded DXF JSON structure for RAG context")
    
    # Load RAG JSON context (optional)
    rag_context = load_rag_json_context(part_name, subdirectory)
    
    if "error" in rag_context:
        print(f"⚠️  Warning: RAG JSON context not available: {rag_context['error']}")
        # Continue without RAG context - use empty dict
        rag_context = {"note": "No RAG context available"}
    else:
        print(f"✅ Loaded RAG JSON context")
    
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
    dxf_json = json.dumps(dxf_structure, indent=2)
    rag_json_context = json.dumps(rag_context, indent=2)
    
    # Create prompt
    prompt = PROMPT_TEMPLATE.format(
        qif_metadata=unified_json,
        step_metadata=unified_json,
        pdf_csv_text=pdf_csv_text if pdf_csv_text else "No PDF/CSV text available",
        rag_json_context=rag_json_context,  # This now represents the DXF structure in the prompt
        cam=CAM
    )
    
    # Call LLM
    try:
        result = ask_llm(prompt)
        return result
    except Exception as e:
        print(f"❌ Error processing {part_name}: {e}")
        return {
            "error": str(e)
        }

def main():
    """Main function to process all parts."""
    print("🚀 COMBINED LLM RAG - Processing all parsed data")
    print("=" * 60)
    
    # Get subdirectory from command line or use default
    if len(sys.argv) > 1:
        subdirectory = sys.argv[1]
    else:
        subdirectory = "Inventor"  # Default to Inventor
    
    print(f"Processing subdirectory: {subdirectory}")
    
    # Create output directory for this subdirectory
    output_dir = LLM_RESULTS_DIR / subdirectory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load all parsed data
    print(f"\nLoading parsed data from: {PARSED_RESULTS_DIR / subdirectory}")
    parsed_data = load_parsed_data(subdirectory)
    
    if not parsed_data:
        print("❌ No parsed data found!")
        return False
    
    # Load TXT data
    print(f"\nLoading TXT data...")
    txt_data = load_txt_data(subdirectory)
    
    # Process each part
    print(f"\nProcessing {len(parsed_data)} parts...")
    results = {}
    
    for part_name, part_data in parsed_data.items():
        try:
            result = process_part(part_name, part_data, txt_data, subdirectory)
            results[part_name] = result
            
            # Save individual result
            output_path = output_dir / f"{part_name}_llm_response.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved LLM response: {output_path.name}")
            
        except Exception as e:
            print(f"❌ Error processing {part_name}: {e}")
            results[part_name] = {"error": str(e)}
    
    # Save combined results
    combined_output_path = output_dir / f"{subdirectory}_all_llm_responses.json"
    with open(combined_output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Print summary
    success_count = sum(1 for r in results.values() if "error" not in r)
    error_count = len(results) - success_count
    
    print(f"\n{'='*60}")
    print("🎯 COMBINED LLM RAG COMPLETED")
    print(f"{'='*60}")
    print(f"Subdirectory: {subdirectory}")
    print(f"Parts processed: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Output location: {output_dir}")
    print(f"Combined results: {combined_output_path.name}")
    
    return error_count == 0



if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 