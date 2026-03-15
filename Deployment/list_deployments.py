"""
list_deployments.py — Show all deployments for this Apps Script project
========================================================================
Run this to find the correct Deployment ID to put in deploy_config.json.
You want the one that says "Web app" and is NOT "@HEAD".
"""

import sys
import json
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    import googleapiclient.discovery as discovery
    from googleapiclient.errors import HttpError
except ImportError:
    print("\n[ERROR] Required packages not installed.")
    print("Run:  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\n")
    input("Press Enter to close...")
    sys.exit(1)

SCRIPT_DIR       = Path(__file__).parent
CONFIG_FILE      = SCRIPT_DIR / "deploy_config.json"
TOKEN_FILE       = SCRIPT_DIR / "token.json"
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
]

def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
    return creds

def main():
    print("═" * 60)
    print("  Vital Vortex — List Deployments")
    print("═" * 60)

    with open(CONFIG_FILE) as f:
        config = json.load(f)
    script_id = config["script_id"]
    print(f"\nScript ID: {script_id}")
    print(f"Current deploy_config.json Deployment ID: {config.get('deployment_id')}\n")

    creds   = get_credentials()
    service = discovery.build("script", "v1", credentials=creds)

    try:
        result      = service.projects().deployments().list(scriptId=script_id).execute()
        deployments = result.get("deployments", [])
    except HttpError as e:
        print(f"[ERROR] {e.resp.status}: {e.reason}")
        print(e.content.decode() if hasattr(e, "content") else e)
        input("\nPress Enter to close...")
        sys.exit(1)

    print(f"Found {len(deployments)} deployment(s):\n")
    print("─" * 60)

    for d in deployments:
        dep_id      = d.get("deploymentId", "(none)")
        dep_config  = d.get("deploymentConfig", {})
        description = dep_config.get("description", "(no description)")
        version     = dep_config.get("versionNumber", "(none)")
        entry_points= d.get("entryPoints", [])

        print(f"  Deployment ID : {dep_id}")
        print(f"  Description   : {description}")
        print(f"  Version       : {version}")

        for ep in entry_points:
            ep_type = ep.get("entryPointType", "")
            if ep_type == "WEB_APP":
                wa = ep.get("webApp", {})
                print(f"  Type          : Web App")
                print(f"  Access        : {wa.get('access', '?')}")
                print(f"  Execute As    : {wa.get('executeAs', '?')}")
            elif ep_type == "EXECUTION_API":
                print(f"  Type          : Execution API")
            else:
                print(f"  Type          : {ep_type}")

        if dep_id == config.get("deployment_id"):
            print(f"  *** This is the ID currently in deploy_config.json ***")

        print("─" * 60)

    print("\nThe ID you want in deploy_config.json is the Web App deployment")
    print("that is NOT @HEAD and has a real version number.")
    print("\nIf you need to update deploy_config.json, just tell your assistant")
    print("which Deployment ID to use and it will update the file for you.")

    input("\nPress Enter to close...")

if __name__ == "__main__":
    main()
