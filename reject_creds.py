import subprocess

def reject(protocol, host, username=None):
    input_str = f"protocol={protocol}\nhost={host}\n"
    if username:
        input_str += f"username={username}\n"
    input_str += "\n" # Blank line to signal end of input
    
    try:
        subprocess.run(["git", "credential", "reject"], input=input_str.encode(), check=False)
        print(f"Rejected {protocol}://{host} {username if username else ''}")
    except Exception as e:
        print(f"Error rejecting {protocol}://{host}: {e}")

if __name__ == "__main__":
    reject("https", "github.com")
    reject("https", "api.github.com")
    # Also try without specific host to catch generics if matching logic allows
