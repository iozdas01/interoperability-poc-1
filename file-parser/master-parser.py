#!/usr/bin/env python3
"""
Master Parser Script
====================
This script orchestrates all parsers and extractors:
1. Combined Parser (PDF, QIF, STEP)
2. DXF Line Extractor
3. Any other future parsers

It runs all parsers and provides a unified interface.
"""

import subprocess
import sys
from pathlib import Path
import json
import time
import importlib.util

# Configuration
RAW_DATA_DIR = Path("data")
OUTPUT_DIR = Path("execute/parsed-results")
DXF_OUTPUT_DIR = OUTPUT_DIR  # Default, but will be set per run

def run_combined_parser(subdirectory):
    """Run the combined parser for a specific subdirectory."""
    print(f"\n{'='*60}")
    print(f"RUNNING COMBINED PARSER FOR: {subdirectory}")
    print(f"{'='*60}")
    
    try:
        # Import and run the combined parser
        import sys
        import importlib.util
        
        # Add parser-code to path
        parser_code_path = Path("execute/parser-code")
        sys.path.append(str(parser_code_path))
        
        # Import the combined-parser.py file
        spec = importlib.util.spec_from_file_location(
            "combined_parser", 
            parser_code_path / "combined-parser.py"
        )
        combined_parser_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(combined_parser_module)
        
        # Get the CombinedParser class
        CombinedParser = combined_parser_module.CombinedParser
        
        parser = CombinedParser(subdirectory=subdirectory)
        results = parser.parse_all()
        
        print(f"✅ Combined parser completed for {subdirectory}")
        print(f"   Processed {len(results)} parts")
        return True
    except Exception as e:
        print(f"❌ Combined parser failed for {subdirectory}: {e}")
        return False

def run_dxf_extractor(subdirectory):
    """Run the DXF line extractor for a specific subdirectory."""
    print(f"\n{'='*60}")
    print(f"RUNNING DXF EXTRACTOR FOR: {subdirectory}")
    print(f"{'='*60}")
    
    try:
        # Check if there are DXF files in the subdirectory
        dxf_files = list((RAW_DATA_DIR / subdirectory).rglob("*.dxf"))
        if not dxf_files:
            print(f"ℹ️  No DXF files found in {subdirectory}")
            return True
        
        print(f"Found {len(dxf_files)} DXF files to process")
        
        # Create the output directory for this subdirectory
        dxf_output_dir = DXF_OUTPUT_DIR / subdirectory
        dxf_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each DXF file directly
        processed_count = 0
        for dxf_file in dxf_files:
            try:
                print(f"Processing DXF: {dxf_file.name}")
                
                # Extract DXF metadata directly
                metadata = extract_dxf_metadata(dxf_file)
                
                # Save to the correct location with _dxf suffix
                part_name = dxf_file.stem
                output_path = dxf_output_dir / f"{part_name}_dxf.json"
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Processed: {dxf_file.name} -> {output_path.name}")
                processed_count += 1
                
            except Exception as e:
                print(f"❌ Error processing {dxf_file.name}: {e}")
        
        print(f"✅ DXF extractor completed: {processed_count} files processed")
        return True
    except Exception as e:
        print(f"❌ DXF extractor failed for {subdirectory}: {e}")
        return False

def create_summary_report(subdirectory):
    """Create a summary report of all processed files."""
    print(f"\n{'='*60}")
    print(f"CREATING SUMMARY REPORT FOR: {subdirectory}")
    print(f"{'='*60}")
    
    summary = {
        "subdirectory": subdirectory,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "files": {}
    }
    
    # Check combined parser output
    combined_output_dir = OUTPUT_DIR / subdirectory
    if combined_output_dir.exists():
        json_files = list(combined_output_dir.glob("*.json"))
        txt_files = list(combined_output_dir.glob("*.txt"))
        dxf_json_files = list(combined_output_dir.glob("*_dxf.json"))
        
        # Separate regular JSON files from DXF JSON files
        regular_json_files = [f for f in json_files if not f.name.endswith("_dxf.json")]
        
        summary["combined_parser"] = {
            "output_directory": str(combined_output_dir),
            "json_files": len(regular_json_files),
            "txt_files": len(txt_files),
            "parts_processed": len(regular_json_files)
        }
        
        summary["dxf_extractor"] = {
            "output_directory": str(combined_output_dir),
            "dxf_files_processed": len(dxf_json_files)
        }
        
        print(f"✅ Combined parser output: {len(regular_json_files)} parts processed")
        print(f"✅ DXF extractor output: {len(dxf_json_files)} DXF files processed")
    
    # Save summary report
    summary_path = OUTPUT_DIR / f"{subdirectory}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"📊 Summary report saved to: {summary_path}")
    return summary

def extract_dxf_metadata(dxf_path: Path) -> dict:
    """Extract DXF metadata directly without external script."""
    try:
        # Load DXF lines
        txt = dxf_path.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in txt.splitlines()]
        
        # Extract basic metadata
        metadata = {
            "file_path": str(dxf_path),
            "file_name": dxf_path.name,
            "part_name": dxf_path.stem,
            "total_lines": len(lines),
            "dxf_version": None,
            "layers": [],
            "comments_present": any(l == "999" for l in lines),
            "header_variables": {}
        }
        
        # Extract DXF version and header variables
        for i in range(len(lines) - 1):
            if lines[i] == "9" and i + 1 < len(lines):
                var_name = lines[i + 1]
                if var_name == "$ACADVER" and i + 3 < len(lines):
                    metadata["dxf_version"] = lines[i + 3]
                elif var_name.startswith("$") and i + 3 < len(lines):
                    try:
                        value = float(lines[i + 3])
                        metadata["header_variables"][var_name] = value
                    except ValueError:
                        metadata["header_variables"][var_name] = lines[i + 3]
        
        # Extract layer information
        for i in range(len(lines) - 3):
            if (lines[i] == "0" and lines[i + 1].upper() == "LAYER" and 
                i + 3 < len(lines) and lines[i + 2] == "2"):
                layer_name = lines[i + 3]
                metadata["layers"].append(layer_name)
        
        return metadata
        
    except Exception as e:
        print(f"Error extracting DXF metadata from {dxf_path}: {e}")
        return {
            "file_path": str(dxf_path),
            "file_name": dxf_path.name,
            "part_name": dxf_path.stem,
            "error": str(e)
        }

def main():
    global OUTPUT_DIR, DXF_OUTPUT_DIR  # <-- Fix: declare globals at the top
    print("🚀 MASTER PARSER - Starting all parsers and extractors")
    print("=" * 60)
    
    # Accept both input and output subdirectory names
    if len(sys.argv) > 2:
        input_subdir = sys.argv[1]
        output_subdir = sys.argv[2]
    elif len(sys.argv) > 1:
        input_subdir = output_subdir = sys.argv[1]
    else:
        input_subdir = output_subdir = "Inventor"
    
    print(f"Input subdirectory: {input_subdir}")
    print(f"Output subdirectory: {output_subdir}")
    
    subdirectory_path = RAW_DATA_DIR / input_subdir
    output_path = OUTPUT_DIR / output_subdir
    
    if not subdirectory_path.exists():
        print(f"❌ Error: Subdirectory {subdirectory_path} not found!")
        print(f"Available subdirectories: {[d.name for d in RAW_DATA_DIR.iterdir() if d.is_dir()]}")
        return False
    
    # Create output directories
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Update global output dir for downstream functions
    OUTPUT_DIR = output_path
    DXF_OUTPUT_DIR = output_path
    
    # Track success/failure
    success_count = 0
    total_parsers = 2
    
    # Run combined parser
    if run_combined_parser(input_subdir):
        success_count += 1
    
    # Run DXF extractor
    if run_dxf_extractor(input_subdir):
        success_count += 1
    
    # Create summary report
    summary = create_summary_report(input_subdir)
    
    # Final summary
    print(f"\n{'='*60}")
    print("🎯 MASTER PARSER COMPLETED")
    print(f"{'='*60}")
    print(f"Input subdirectory: {input_subdir}")
    print(f"Output subdirectory: {output_subdir}")
    print(f"Parsers successful: {success_count}/{total_parsers}")
    print(f"Output location: {output_path}")
    
    if success_count == total_parsers:
        print("✅ All parsers completed successfully!")
        return True
    else:
        print("⚠️  Some parsers failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 