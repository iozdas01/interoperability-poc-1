from .base import BaseParser
from typing import Dict, Any
from pathlib import Path

class DxfParser(BaseParser):
    """Parser for DXF files to extract internal structure and metadata."""

    def parse(self) -> Dict[str, Any]:
        """Parse all DXF files."""
        dxf_files = list(self.data_dir.rglob("*.dxf"))
        results = {}
        
        for dxf_file in dxf_files:
            part_id = dxf_file.stem
            print(f"Processing DXF: {dxf_file.name}")
            
            try:
                results[part_id] = self._extract_metadata(dxf_file)
            except Exception as e:
                print(f"Error processing {dxf_file.name}: {e}")
                results[part_id] = {"error": str(e)}
                
        return results

    def _extract_metadata(self, dxf_path: Path) -> Dict[str, Any]:
        """Extract metadata looking for specific target fields as RAW BLOCKS."""
        txt = dxf_path.read_text(encoding="utf-8", errors="ignore")
        lines = txt.splitlines()
        
        metadata = {
            "file_name": dxf_path.name,
            "specifics": {
                "user_variables_block": None,
                "end_section_block": None
            },
            "comments": []
        }
        
        i = 0
        user_block_start = -1
        user_block_end = -1
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Check for start of USER variables block
            # Logic: Look for '9' followed by '$USER...'
            if user_block_start == -1 and line == "9" and i + 1 < len(lines):
                var_name = lines[i+1].strip()
                if var_name.startswith("$USER"):
                    user_block_start = i
            
            # If we are inside a potential user block, check if it ends
            if user_block_start != -1:
                # A block ends if we hit a '0' (new section/entity) 
                # OR a '9' followed by something NOT starting with $USER
                if line == "0":
                    user_block_end = i
                elif line == "9" and i + 1 < len(lines):
                     var_name = lines[i+1].strip()
                     if not var_name.startswith("$USER"):
                         user_block_end = i
            
            # If we found an end to the block, save and stop looking for it
            if user_block_start != -1 and user_block_end != -1:
                metadata["specifics"]["user_variables_block"] = "\n".join(lines[user_block_start:user_block_end])
                user_block_start = -1 # Reset so we don't capture again if there are multiple blocks (unlikely)
                user_block_end = -1
            
            # Look for Comments (999) - Keep this existing functionality
            if line == "999" and i + 1 < len(lines):
                block_lines = lines[i:i+2]
                metadata["comments"].append("\n".join(block_lines))
                
            i += 1
            
        # Extract ENDSEC/EOF block (usually at the very end)
        # We look for the sequence: 0 -> ENDSEC -> 0 -> EOF
        # This is typically the last 4 lines of a well-formed DXF
        if len(lines) >= 4:
            last_4 = lines[-4:]
            if (last_4[0].strip() == "0" and 
                last_4[1].strip() == "ENDSEC" and 
                last_4[2].strip() == "0" and 
                last_4[3].strip() == "EOF"):
                metadata["specifics"]["end_section_block"] = "\n".join(last_4)
        
        return metadata
