"""DXF metadata context extractor."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List
import json
import sys

RAW_DATA_DIR = Path("data")
OUTPUT_DIR = Path("execute/parsed-results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def _load_lines(path: Path) -> List[str]:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return [line.strip() for line in txt.splitlines()]


def extract_context(dxf_path: str | Path) -> Dict[str, object]:
    """Convert entire DXF file to JSON format."""
    path = Path(dxf_path)
    lines = _load_lines(path)
    
    # Convert the entire DXF to a structured format
    dxf_json = {
        "file_info": {
            "filename": path.name,
            "total_lines": len(lines),
            "file_size_bytes": path.stat().st_size
        },
        "raw_lines": lines,  # Include all lines for complete context
        "sections": {},
        "header_variables": {},
        "layers": [],
        "comments": [],
        "entities": [],
        "analysis": {}
    }
    
    # Parse sections and extract structured data
    current_section = None
    in_header = False
    in_tables = False
    in_entities = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Detect section boundaries
        if line_stripped == "0" and i + 1 < len(lines) and lines[i + 1].strip().upper() == "SECTION":
            if i + 3 < len(lines):
                section_name = lines[i + 3].strip().upper()
                if section_name == "HEADER":
                    current_section = "HEADER"
                    in_header = True
                    dxf_json["sections"]["header"] = {"start_line": i, "end_line": None}
                elif section_name == "TABLES":
                    current_section = "TABLES"
                    in_tables = True
                    in_header = False
                    dxf_json["sections"]["tables"] = {"start_line": i, "end_line": None}
                elif section_name == "ENTITIES":
                    current_section = "ENTITIES"
                    in_entities = True
                    in_tables = False
                    dxf_json["sections"]["entities"] = {"start_line": i, "end_line": None}
        
        # Detect section ends
        elif line_stripped == "0" and i + 1 < len(lines) and lines[i + 1].strip().upper() == "ENDSEC":
            if current_section:
                dxf_json["sections"][current_section.lower()]["end_line"] = i
                current_section = None
                in_header = False
                in_tables = False
                in_entities = False
        
        # Extract header variables
        elif in_header and line_stripped == "9" and i + 3 < len(lines):
            var_name = lines[i + 1].strip()
            gcode = lines[i + 2].strip()
            value = lines[i + 3].strip()
            dxf_json["header_variables"][var_name] = {
                "gcode": gcode,
                "value": value,
                "line_number": i + 1
            }
        
        # Extract comments
        elif line_stripped == "999" and i + 1 < len(lines):
            comment = lines[i + 1].strip()
            dxf_json["comments"].append({
                "comment": comment,
                "line_number": i + 1
            })
        
        # Extract layers
        elif in_tables and line_stripped == "0" and i + 1 < len(lines) and lines[i + 1].strip().upper() == "LAYER":
            # Find layer name
            for j in range(i, min(i + 20, len(lines))):
                if lines[j].strip() == "2" and j + 1 < len(lines):
                    layer_name = lines[j + 1].strip()
                    dxf_json["layers"].append({
                        "name": layer_name,
                        "line_number": j + 1,
                        "index": len(dxf_json["layers"])
                    })
                    break
        
        # Extract entities (basic structure)
        elif in_entities and line_stripped == "0" and i + 1 < len(lines):
            entity_type = lines[i + 1].strip().upper()
            dxf_json["entities"].append({
                "type": entity_type,
                "line_number": i + 1
            })
    
    # Add analysis for LLM
    dxf_json["analysis"] = {
        "has_userr1": "$USERR1" in dxf_json["header_variables"],
        "has_useri1": "$USERI1" in dxf_json["header_variables"],
        "userr1_value": dxf_json["header_variables"].get("$USERR1", {}).get("value", "NOT_FOUND"),
        "useri1_value": dxf_json["header_variables"].get("$USERI1", {}).get("value", "NOT_FOUND"),
        "layer_0_name": dxf_json["layers"][0]["name"] if dxf_json["layers"] else "NOT_FOUND",
        "total_comments": len(dxf_json["comments"]),
        "total_entities": len(dxf_json["entities"]),
        "existing_comment_texts": [c["comment"] for c in dxf_json["comments"]]
    }
    
    return dxf_json


def main():
    if len(sys.argv) > 1:
        dxf_path = sys.argv[1]
        process_dxf(dxf_path)
    else:
        if not RAW_DATA_DIR.exists():
            print(f"Error: {RAW_DATA_DIR} directory not found.")
            sys.exit(1)
        for dxf_file in RAW_DATA_DIR.glob("*.dxf"):
            process_dxf(dxf_file)


def process_dxf(dxf_path):
    digest = extract_context(dxf_path)
    out_path = OUTPUT_DIR / Path(dxf_path).with_suffix('.json').name
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(digest, f, indent=2)
    print(f"✅ Wrote JSON to: {out_path}")


if __name__ == "__main__":
    main()