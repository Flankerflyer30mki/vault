import subprocess

try:
    result = subprocess.run(
        ["python", "evil.py"],
        timeout=3,
        capture_output=True,
        text=True
    )
    print("Finished normally:", result.stdout)
except subprocess.TimeoutExpired:
    print("Killed after timeout — sandbox worked!")