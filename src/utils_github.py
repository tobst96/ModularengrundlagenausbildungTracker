import os
import requests
import logging

logger = logging.getLogger(__name__)

def create_github_issue(title, body):
    """
    Creates a GitHub issue using the REST API.
    Requires GITHUB_TOKEN environment variable.
    """
    token = os.getenv("GITHUB_TOKEN")
    # Repository details from remote or env
    repo = "tobst96/ModularengrundlagenausbildungTracker"
    
    if not token:
        logger.warning("GITHUB_TOKEN not set. Cannot create GitHub issue.")
        return False, "GITHUB_TOKEN not set"

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": title,
        "body": body
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 201:
            issue_url = response.json().get("html_url")
            logger.info(f"GitHub issue created: {issue_url}")
            return True, issue_url
        else:
            error_msg = f"Failed to create issue: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return False, error_msg
    except Exception as e:
        logger.error(f"Exception during issue creation: {e}")
        return False, str(e)
