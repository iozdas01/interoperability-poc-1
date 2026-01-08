from pathlib import Path

def find_user_vars():
    path = Path(r"c:\Users\izgin.ozdas\OneDrive - Accenture\Documents\Thesis\interoperability-poc1\data\teknocer\P12-D013-01.DXF")
    txt = path.read_text(encoding="utf-8", errors="ignore")
    lines = txt.splitlines()
    
    print(f"Total lines: {len(lines)}")
    
    found_any = False
    for i, line in enumerate(lines):
        if "$USER" in line:
            print(f"Line {i+1}: {line}")
            found_any = True
            # Print context lines
            start = max(0, i-5)
            end = min(len(lines), i+10)
            # print("\n".join(lines[start:end]))
            # print("-" * 20)
            
    if not found_any:
        print("No lines containing '$USER' found.")

if __name__ == "__main__":
    find_user_vars()
