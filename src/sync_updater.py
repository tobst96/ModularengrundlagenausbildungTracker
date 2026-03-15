import subprocess
import os
import sys
import logging

logger = logging.getLogger(__name__)

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
        res = subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"Git fetch failed: {res.stderr}")
            return "Unknown"
            
        branch = get_current_branch()
        # Try main first, then fallback to current branch
        for b in ["main", branch]:
            res = subprocess.run(["git", "rev-parse", "--short", f"origin/{b}"], capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip()
                
        logger.error(f"Git rev-parse failed for main and {branch}")
        return "Unknown"
    except Exception as e:
        logger.error(f"Unexpected error in get_remote_commit: {e}")
        return "Unknown"

def is_update_available():
    local = get_local_commit()
    remote = get_remote_commit()
    if local == "Unknown" or remote == "Unknown":
        return False
    return local != remote

def run_git_pull():
    try:
        # Stash local changes to avoid merge conflicts
        subprocess.run(["git", "stash"], capture_output=True, text=True)
        
        result = subprocess.run(["git", "pull", "origin", get_current_branch()], capture_output=True, text=True, check=True)
        
        # Optional: Try to pop stash if we want to preserve local tweaks
        # subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
        
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        # If pull fails, we still try to pop stash to restore local state
        subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
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
    # Check if we are in a git repository
    if not os.path.exists(".git"):
        logger.error("Auto-update failed: Not a git repository (.git folder missing).")
        return False, "This installation is not a git repository. Auto-updates require a git-based installation."

    ok_pull, msg_pull = run_git_pull()
    if not ok_pull:
        return False, f"Git Pull failed: {msg_pull}"
    
    ok_pip, msg_pip = update_dependencies()
    if not ok_pip:
        return False, f"Pip install failed: {msg_pip}"
    
    
    logger.info("Restarting server after successful update...")
    
    # Prepare restart command
    # Using sys.executable -m streamlit run ensures we use the correct environment
    script_path = os.path.abspath("1_🏠_Startseite.py")
    
    # We try to preserve original arguments if possible
    # In Streamlit, sys.argv usually contains [script_name, arg1, arg2, ...]
    args = [sys.executable, "-m", "streamlit", "run", script_path] + sys.argv[1:]
    
    # Re-run with the same arguments if we're in a terminal or docker
    # We use os.execv to replace the current process
    try:
        os.execv(sys.executable, args)
    except Exception as e:
        logger.error(f"Failed to execv: {e}")
        # Fallback to exit(0) for Docker to handle if execv fails
        os._exit(0)
    
    return True, "Update initiated"
