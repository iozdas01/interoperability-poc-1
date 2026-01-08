"""Apply LLM-generated patches to DXF files."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Union
import json
import ezdxf
import sys


def _load_lines(path: Union[str, Path]) -> List[str]:
    """Load DXF file as list of lines."""
    if isinstance(path, str):
        path = Path(path)
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def _section(lines: List[str], name: str) -> tuple[int, int]:
    """Find start and end indices of a DXF section."""
    name = name.upper()
    start = -1
    end = -1
    
    print(f"\nSearching for {name} section...")
    for i in range(len(lines) - 3):
        # Strip spaces from group codes
        if (
            lines[i].strip() == "0"
            and lines[i + 1].strip().upper() == "SECTION"
            and lines[i + 2].strip() == "2"
            and lines[i + 3].strip().upper() == name
        ):
            start = i + 4
            print(f"Found {name} section start at {start}")
            for j in range(start, len(lines) - 1):
                if lines[j].strip() == "0" and lines[j + 1].strip().upper() == "ENDSEC":
                    end = j
                    print(f"Found {name} section end at {end}")
                    return start, end
            break
    
    if start == -1:
        print(f"WARNING: Could not find {name} section!")
        print("First few lines of file:")
        for i in range(min(10, len(lines))):
            print(f"{i}: {lines[i]}")
    
    return start, end


def _find_header_var(lines: List[str], var_name: str) -> int:
    """Find the index of a header variable, or -1 if not found."""
    for i in range(len(lines) - 3):
        if (
            lines[i].strip() == "9"
            and lines[i + 1].strip() == var_name
            and i + 3 < len(lines)
        ):
            print(f"Found header var {var_name} at index {i}")
            return i
    print(f"Header var {var_name} not found")
    return -1


def _find_layer_by_index(lines: List[str], index: int) -> tuple[int, int]:
    """Find the start and end indices of a layer by its position in the LAYER table.
    
    Returns:
        tuple of (start_index, name_index) where:
        - start_index is the start of the LAYER record (0\nLAYER)
        - name_index is the position of the layer name (2\nNAME)
    """
    current_index = -1
    for i in range(len(lines) - 1):
        if lines[i] == "0" and lines[i + 1].upper() == "LAYER":
            current_index += 1
            if current_index == index:
                # Found the layer, now find its name
                for j in range(i, min(i + 20, len(lines) - 1)):
                    if lines[j] == "2":  # Group code for layer name
                        return i, j
    return -1, -1


def apply_patch(dxf_path: Union[str, Path], patch: Dict) -> List[str]:
    """Apply LLM patch to DXF file.
    
    Args:
        dxf_path: Path to DXF file or list of lines
        patch: Dictionary with header_updates, layer_renames, add_comments
        
    Returns:
        Modified DXF as list of lines
    """
    # Load DXF
    lines = _load_lines(dxf_path)
    print(f"\nLoaded DXF file with {len(lines)} lines")
    modified = lines.copy()
    
    # 1. Apply header updates
    if "header_updates" in patch:
        header_start, header_end = _section(modified, "HEADER")
        if header_start >= 0 and header_end >= 0:
            for update in patch["header_updates"]:
                var_name = update["var"]
                gcode = update["gcode"]
                value = update["value"]
                placement = update.get("placement", "before_endsec")
                
                print(f"Processing header update: {var_name} = {value} (placement: {placement})")
                
                # Only allow $USERI1-5 (int, 70) and $USERR1-5 (float, 40)
                if not (var_name.startswith("$USERI") or var_name.startswith("$USERR")):
                    print(f"  Skipping {var_name} - not a valid user variable")
                    continue
                if gcode not in (40, 70):
                    print(f"  Skipping {var_name} - invalid group code {gcode}")
                    continue
                
                # Search for the variable
                var_idx = _find_header_var(modified[header_start:header_end], var_name)
                
                if placement == "before_endsec":
                    # Always add new variable before ENDSEC, regardless of whether it exists
                    print(f"  Adding new variable {var_name} = {value} before ENDSEC")
                    print(f"  Header section: {header_start} to {header_end}")
                    
                    # Find ENDSEC line in header section
                    endsec_idx = -1
                    for i in range(header_start, header_end + 1):
                        if modified[i].strip() == "0" and modified[i + 1].strip().upper() == "ENDSEC":
                            endsec_idx = i + 1  # Point to the ENDSEC line itself
                            print(f"  Found ENDSEC at index {i + 1}")
                            break
                    
                    if endsec_idx >= 0:
                        # Insert new variable before ENDSEC
                        # Format group codes with proper padding (right-aligned)
                        modified.insert(endsec_idx, str(value))  # Value
                        modified.insert(endsec_idx, f" {gcode:>3}")   # Group code (right-aligned, 3 chars wide)
                        modified.insert(endsec_idx, var_name)     # Variable name
                        modified.insert(endsec_idx, "  9")          # Group code for variable (padded)
                        print(f"  Inserted {var_name} at index {endsec_idx}")
                    else:
                        print(f"  Warning: Could not find ENDSEC in header section")
                        print(f"  Header section lines:")
                        for i in range(header_start, min(header_start + 10, header_end)):
                            print(f"    {i}: {modified[i]}")
                        if header_end - header_start > 10:
                            print(f"    ... and {header_end - header_start - 10} more lines")
                        
                elif placement == "update_existing":
                    # Only update if variable exists, otherwise skip
                    if var_idx >= 0:
                        var_idx += header_start
                        print(f"  Updating existing variable {var_name} at index {var_idx + 3}")
                        # Format the value properly based on group code
                        if gcode == 70:  # Integer
                            modified[var_idx + 3] = f"{int(value):>6}"  # Right-aligned, 6 chars wide
                        elif gcode == 40:  # Float
                            modified[var_idx + 3] = str(value)  # Keep as is for floats
                        else:
                            modified[var_idx + 3] = str(value)  # Default
                    else:
                        print(f"  Variable {var_name} not found, skipping (update_existing mode)")
                else:
                    print(f"  Unknown placement: {placement}, skipping")
    # 2. Apply layer renames
    if "layer_renames" in patch:
        tables_start, tables_end = _section(modified, "TABLES")
        if tables_start >= 0 and tables_end >= 0:
            for rename in patch["layer_renames"]:
                layer_index = rename["index"]
                new_name = rename["new"]
                placement = rename.get("placement", "update_specific_layer")
                
                print(f"Processing layer rename: index {layer_index} -> {new_name} (placement: {placement})")
                
                # Enforce length/character rules
                new_name = new_name[:255]
                for c in '<>/\\":;?*|=':
                    new_name = new_name.replace(c, "_")
                
                if placement == "update_layer_0":
                    # Update Layer 0 (first layer)
                    layer_start, name_idx = _find_layer_by_index(modified[tables_start:tables_end], 0)
                    if layer_start >= 0 and name_idx >= 0:
                        print(f"  Updating Layer 0 name at index {tables_start + name_idx + 1}")
                        modified[tables_start + name_idx + 1] = new_name
                    else:
                        print(f"  Warning: Could not find Layer 0")
                elif placement == "update_specific_layer":
                    # Update specific layer by index
                    layer_start, name_idx = _find_layer_by_index(modified[tables_start:tables_end], layer_index)
                    if layer_start >= 0 and name_idx >= 0:
                        print(f"  Updating layer {layer_index} name at index {tables_start + name_idx + 1}")
                        modified[tables_start + name_idx + 1] = new_name
                    else:
                        print(f"  Warning: Could not find layer at index {layer_index}")
                else:
                    print(f"  Unknown placement: {placement}, using update_specific_layer")
                    layer_start, name_idx = _find_layer_by_index(modified[tables_start:tables_end], layer_index)
                    if layer_start >= 0 and name_idx >= 0:
                        modified[tables_start + name_idx + 1] = new_name
    # 3. Add comments with placement options
    if "add_comments" in patch:
        for comment_data in patch["add_comments"]:
            comment = comment_data["comment"] if isinstance(comment_data, dict) else comment_data
            placement = comment_data.get("placement", "entities_end")
            
            print(f"Adding comment: {comment[:50]}... (placement: {placement})")
            
            if placement == "file_start":
                # Insert at beginning of file
                insert_pos = 0
                for line in [comment[i:i+256] for i in range(0, len(comment), 256)]:
                    modified.insert(insert_pos, "999")
                    modified.insert(insert_pos + 1, line.strip())  # Remove any newlines
                    insert_pos += 2
            elif placement == "file_end":
                # Insert before the "  0" line that precedes EOF
                insert_pos = len(modified) - 2  # Position before the "  0" line
                for line in [comment[i:i+256] for i in range(0, len(comment), 256)]:
                    modified.insert(insert_pos, "999")
                    modified.insert(insert_pos + 1, line.strip())  # Remove any newlines
                    insert_pos += 2
            elif placement == "entities_end":
                # Insert at end of ENTITIES section
                entities_start, entities_end = _section(modified, "ENTITIES")
                insert_pos = entities_end if entities_end >= 0 else len(modified)
                for line in [comment[i:i+256] for i in range(0, len(comment), 256)]:
                    modified.insert(insert_pos, "999")
                    modified.insert(insert_pos + 1, line.strip())  # Remove any newlines
                    insert_pos += 2
            else:
                print(f"  Unknown placement: {placement}, using entities_end")
                entities_start, entities_end = _section(modified, "ENTITIES")
                insert_pos = entities_end if entities_end >= 0 else len(modified)
                for line in [comment[i:i+256] for i in range(0, len(comment), 256)]:
                    modified.insert(insert_pos, "999")
                    modified.insert(insert_pos + 1, line.strip())  # Remove any newlines
                    insert_pos += 2

    return modified


# Metadata extraction and comparison functions moved to dxf-metadata.py


def main():
    """Process LLM response JSON files and apply their annotation instructions to DXF files."""
    # Setup directories for both AutoCAD and Inventor
    base_results_dir = Path("execute/Zero-Shot/llm-results-zeroshot")
    raw_data_dir = Path("raw_data")
    
    if not base_results_dir.exists():
        print(f"Error: Results directory not found at {base_results_dir}")
        return
    
    # Process both AutoCAD and Inventor
    subdirectories = ["autocad", "inventor"]
    
    for subdirectory in subdirectories:
        print(f"\n{'='*50}")
        print(f"Processing {subdirectory.upper()} files...")
        print(f"{'='*50}")
        
        results_dir = base_results_dir / subdirectory
        raw_subdir = raw_data_dir / subdirectory.capitalize()
        
        if not results_dir.exists():
            print(f"Warning: Results directory not found at {results_dir}, skipping...")
            continue
            
        if not raw_subdir.exists():
            print(f"Warning: Raw data directory not found at {raw_subdir}, skipping...")
            continue

        # Process each LLM response JSON file
        json_files = list(results_dir.glob("*_llm_response.json"))
        print(f"Found {len(json_files)} LLM response files in {subdirectory}")
        
        for json_path in json_files:
            # Get part_id from filename (remove _llm_response.json)
            part_id = json_path.stem.replace("_llm_response", "")
            
            # Find corresponding DXF file in raw_data
            dxf_path = None
            
            # Try exact match first
            candidate = raw_subdir / f"{part_id}.dxf"
            if candidate.exists():
                dxf_path = candidate
            else:
                # Try double extension (.dxf.dxf) which exists in AutoCAD directory
                candidate = raw_subdir / f"{part_id}.dxf.dxf"
                if candidate.exists():
                    dxf_path = candidate
                    print(f"Found DXF file for {part_id} as {part_id}.dxf.dxf")
                else:
                    # Try removing _2d suffix if present
                    if part_id.endswith("_2d"):
                        base_part_id = part_id[:-3]  # Remove "_2d"
                        candidate = raw_subdir / f"{base_part_id}.dxf"
                        if candidate.exists():
                            dxf_path = candidate
                            print(f"Found DXF file for {part_id} as {base_part_id}.dxf")
                        else:
                            # Try double extension with base part ID
                            candidate = raw_subdir / f"{base_part_id}.dxf.dxf"
                            if candidate.exists():
                                dxf_path = candidate
                                print(f"Found DXF file for {part_id} as {base_part_id}.dxf.dxf")
            
            if not dxf_path:
                print(f"Warning: No DXF file found for {part_id}, skipping...")
                continue

            print(f"\nProcessing {part_id}...")
            
            try:
                # Load LLM response which contains the annotation instructions
                with open(json_path, 'r', encoding='utf-8') as f:
                    patch = json.load(f)
                
                # Apply these instructions to the DXF
                modified = apply_patch(dxf_path, patch)
                
                # Save annotated DXF in the same folder as the LLM response
                output_path = results_dir / f"{part_id}_annotated.dxf"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(modified) + '\n')  # Add newline at end
                print(f"✅ Wrote annotated DXF to: {output_path}")
                
            except Exception as e:
                print(f"Error processing {part_id}: {str(e)}")
                continue
        
        print(f"\nCompleted processing {subdirectory} files")


if __name__ == "__main__":
    # Process both AutoCAD and Inventor folders
    base_results_dir = Path("execute/Zero-Shot/llm-results-zeroshot")
    raw_data_dir = Path("raw_data")
    
    if not base_results_dir.exists():
        print(f"Error: Results directory not found at {base_results_dir}")
        sys.exit(1)
    
    # Process both AutoCAD and Inventor
    subdirectories = ["autocad", "inventor"]
    
    for subdirectory in subdirectories:
        print(f"\n{'='*50}")
        print(f"Processing {subdirectory.upper()} files...")
        print(f"{'='*50}")
        
        results_dir = base_results_dir / subdirectory
        raw_subdir = raw_data_dir / subdirectory.capitalize()
        
        if not results_dir.exists():
            print(f"Warning: Results directory not found at {results_dir}, skipping...")
            continue
            
        if not raw_subdir.exists():
            print(f"Warning: Raw data directory not found at {raw_subdir}, skipping...")
            continue

        # Process each LLM response JSON file
        json_files = list(results_dir.glob("*_llm_response.json"))
        print(f"Found {len(json_files)} LLM response files in {subdirectory}")
        
        for json_path in json_files:
            # Get part_id from filename (remove _llm_response.json)
            part_id = json_path.stem.replace("_llm_response", "")
            
            # Find corresponding DXF file in raw_data
            dxf_path = None
            
            # Try exact match first
            candidate = raw_subdir / f"{part_id}.dxf"
            if candidate.exists():
                dxf_path = candidate
            else:
                # Try double extension (.dxf.dxf) which exists in AutoCAD directory
                candidate = raw_subdir / f"{part_id}.dxf.dxf"
                if candidate.exists():
                    dxf_path = candidate
                    print(f"Found DXF file for {part_id} as {part_id}.dxf.dxf")
                else:
                    # Try removing _2d suffix if present
                    if part_id.endswith("_2d"):
                        base_part_id = part_id[:-3]  # Remove "_2d"
                        candidate = raw_subdir / f"{base_part_id}.dxf"
                        if candidate.exists():
                            dxf_path = candidate
                            print(f"Found DXF file for {part_id} as {base_part_id}.dxf")
                        else:
                            # Try double extension with base part ID
                            candidate = raw_subdir / f"{base_part_id}.dxf.dxf"
                            if candidate.exists():
                                dxf_path = candidate
                                print(f"Found DXF file for {part_id} as {base_part_id}.dxf.dxf")
            
            if not dxf_path:
                print(f"Warning: No DXF file found for {part_id}, skipping...")
                continue

            print(f"\nProcessing {part_id}...")
            
            try:
                # Load LLM response which contains the annotation instructions
                with open(json_path, 'r', encoding='utf-8') as f:
                    patch = json.load(f)
                
                # Apply these instructions to the DXF
                modified = apply_patch(dxf_path, patch)
                
                # Save annotated DXF in the same folder as the LLM response
                output_path = results_dir / f"{part_id}_annotated.dxf"
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(modified) + '\n')  # Add newline at end
                print(f"✅ Wrote annotated DXF to: {output_path}")
                
            except Exception as e:
                print(f"Error processing {part_id}: {str(e)}")
                continue
        
        print(f"\nCompleted processing {subdirectory} files")
