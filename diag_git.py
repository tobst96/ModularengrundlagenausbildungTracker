import subprocess
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_current_branch():
    try:
        return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
    except Exception as e:
        return f"Error: {e}"

def diag_git():
    print(f"CWD: {os.getcwd()}")
    print(f"User ID: {os.getuid()}")
    print(f"Current Branch: {get_current_branch()}")
    
    print("\n--- Testing git fetch origin ---")
    res = subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True)
    print(f"Return code: {res.returncode}")
    print(f"STDOUT: {res.stdout}")
    print(f"STDERR: {res.stderr}")
    
    print("\n--- Testing git config -l ---")
    res = subprocess.run(["git", "config", "-l"], capture_output=True, text=True)
    print(res.stdout)

if __name__ == "__main__":
    diag_git()
