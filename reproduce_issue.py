from parsers.dxf_parser import DxfParser
from pathlib import Path
import json

def reproduce():
    # Setup paths
    base_dir = Path(r"c:\Users\izgin.ozdas\OneDrive - Accenture\Documents\Thesis\interoperability-poc1")
    dxf_file = base_dir / "data/teknocer/P12-D013-01.DXF"
    
    if not dxf_file.exists():
        print(f"File not found: {dxf_file}")
        return

    # Use the parser logic directly or via the class
    # The class requires a data_dir, but we can just use the internal method if we instantiate it
    parser = DxfParser(base_dir) # base_dir as dummy data_dir
    
    print(f"Parsing {dxf_file}...")
    metadata = parser._extract_metadata(dxf_file)
    
    print(json.dumps(metadata, indent=2))

if __name__ == "__main__":
    reproduce()
