from .base import BaseParser
from typing import Dict, Any
import re

class QifParser(BaseParser):
    """Parser for QIF files to extract material and thickness."""

    def parse(self) -> Dict[str, Any]:
        """Parse all QIF files."""
        qif_files = list(self.data_dir.rglob("*.qif"))
        results = {}
        
        for qif_file in qif_files:
            part_id = qif_file.stem
            print(f"Processing QIF: {qif_file.name}")
            
            try:
                results[part_id] = self._process_single_file(qif_file)
            except Exception as e:
                print(f"Error processing {qif_file.name}: {e}")
                results[part_id] = {"error": str(e)}
                
        return results

    def _process_single_file(self, file_path) -> Dict[str, Any]:
        material = None
        thickness = None
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if material is None:
                    m = re.search(r"<Text>Material:\s*(.*?)</Text>", line, re.IGNORECASE)
                    if m: material = m.group(1).strip()
                
                if thickness is None:
                    t = re.search(r"<Text>Thickness:\s*([\d.,]+\s*mm)", line, re.IGNORECASE)
                    if t: thickness = t.group(1).strip()
                    
                if material and thickness:
                    break
                    
        return {
            "material": material or "N/A",
            "thickness": thickness or "N/A",
            "file_path": str(file_path)
        }
