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
        # No need for separate user_block_end variable, we handle extraction immediately upon finding end
        
        # Iterate by pairs (Code, Value)
        # We check i < len(lines) - 1 to ensure a pair exists
        while i < len(lines) - 1:
            code = lines[i].strip()
            value = lines[i+1].strip()
            
            # Check for start of USER variables block
            if user_block_start == -1:
                # Look for '9' followed by '$USER...'
                if code == "9" and value.startswith("$USER"):
                    user_block_start = i
            
            # Check for end of USER variables block if we are in one
            elif user_block_start != -1:
                # A block ends if we hit a '0' (structure) 
                # OR a '9' followed by something NOT starting with $USER
                if code == "0":
                    # End of block found (exclusive of current line i)
                    metadata["specifics"]["user_variables_block"] = "\n".join(lines[user_block_start:i])
                    user_block_start = -1
                elif code == "9" and not value.startswith("$USER"):
                    # End of block found (exclusive of current line i)
                    metadata["specifics"]["user_variables_block"] = "\n".join(lines[user_block_start:i])
                    user_block_start = -1
            
            # Look for Comments (999)
            if code == "999":
                block_lines = lines[i:i+2]
                metadata["comments"].append("\n".join(block_lines))
                
            i += 2
        
        # If we reached the end and still have an open block (rare/malformed but possible)
        if user_block_start != -1:
             metadata["specifics"]["user_variables_block"] = "\n".join(lines[user_block_start:])

        # Extract ENDSEC/EOF block (usually at the very end)
        if len(lines) >= 4:
            last_4 = lines[-4:]
            if (last_4[0].strip() == "0" and 
                last_4[1].strip() == "ENDSEC" and 
                last_4[2].strip() == "0" and 
                last_4[3].strip() == "EOF"):
                metadata["specifics"]["end_section_block"] = "\n".join(last_4)
        
        return metadata
