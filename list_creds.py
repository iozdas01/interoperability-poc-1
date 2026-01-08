import subprocess

def list_creds():
    try:
        # Run cmdkey /list and capture output (it might be in a weird encoding, so we handle it)
        result = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True)
        # Fallback for encoding if text=True fails or gives garbage
        if not result.stdout and result.stderr:
            print(f"Error: {result.stderr}")
            return

        lines = result.stdout.splitlines()
        git_targets = []
        for line in lines:
            if "Target:" in line and "git" in line:
                print(line.strip())
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    list_creds()
