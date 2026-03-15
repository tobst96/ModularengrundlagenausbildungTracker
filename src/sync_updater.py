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

def check_for_updates():
    """Checks for updates and updates the database status."""
    import src.db_base as storage
    import datetime
    
    remote = get_remote_commit()
    available = is_update_available()
    
    storage.save_auto_update_config({
        "last_check_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "update_available": 1 if available else 0,
        "remote_commit": remote
    })
    return available

def perform_auto_update():
    """Executes the full update process and restarts the server."""
    ok_pull, msg_pull = run_git_pull()
    if not ok_pull:
        return False, f"Git Pull failed: {msg_pull}"
    
    ok_pip, msg_pip = update_dependencies()
    if not ok_pip:
        return False, f"Pip install failed: {msg_pip}"
    
    # Trigger server restart (Docker will restart the container if exit code is 0 and restart policy is set)
    import os
    import sys
    os._exit(0)
    return True, "Update initiated"
