import subprocess
import os

def get_current_branch():
    try:
        return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode().strip()
    except:
        return "Unknown"

def get_local_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except:
        return "Unknown"

def get_remote_commit():
    try:
        subprocess.run(["git", "fetch", "origin"], check=True, capture_output=True)
        return subprocess.check_output(["git", "rev-parse", "--short", "origin/main"]).decode().strip()
    except:
        try:
            # Fallback to current branch if main fails
            branch = get_current_branch()
            return subprocess.check_output(["git", "rev-parse", "--short", f"origin/{branch}"]).decode().strip()
        except:
            return "Unknown"

def is_update_available():
    local = get_local_commit()
    remote = get_remote_commit()
    if local == "Unknown" or remote == "Unknown":
        return False
    return local != remote

def run_git_pull():
    try:
        result = subprocess.run(["git", "pull", "origin", get_current_branch()], capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except Exception as e:
        return False, str(e)

def update_dependencies():
    try:
        result = subprocess.run(["pip", "install", "-r", "requirements.txt"], capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except Exception as e:
        return False, str(e)
