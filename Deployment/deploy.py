"""
Vital Vortex Deployer
=====================
Pushes updated Index.html and code.js (as code.gs) to your Google Apps Script
project, then creates a new deployment version so your /exec URL stays stable.

Usage:
    python deploy.py

Place this script in the Deployment folder. It reads Index.html and code.js
from the parent folder (C:\\Vital Vortex).

On first run it will walk you through OAuth authentication (opens a browser tab).
After that, auth is cached in token.json and runs are fully automatic.
"""

import sys
import json
from pathlib import Path

# ── dependency check ──────────────────────────────────────────────────────────
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

# ── configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR       = Path(__file__).parent
ROOT_DIR         = SCRIPT_DIR.parent
CONFIG_FILE      = SCRIPT_DIR / "deploy_config.json"
TOKEN_FILE       = SCRIPT_DIR / "token.json"
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"

HTML_FILE = ROOT_DIR / "Index.html"
JS_FILE   = ROOT_DIR / "code.js"

SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
    "https://www.googleapis.com/auth/spreadsheets",
]

# ── helpers ───────────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
        print(f"  Loaded config from {CONFIG_FILE.name}")
        print(f"  Script ID:     {config.get('script_id', '(missing)')}")
        print(f"  Deployment ID: {config.get('deployment_id', '(missing)')}")
        return config

    print("\n── First-time setup ────────────────────────────────────────────")
    print("You need two pieces of information from your Apps Script project.\n")
    print("How to find your Script ID:")
    print("  1. Open your Apps Script project (script.google.com)")
    print("  2. Click the gear icon (Project Settings) on the left sidebar")
    print("  3. Copy the 'Script ID' value\n")
    script_id = input("Paste your Script ID here: ").strip()

    print("\nHow to find your Deployment ID:")
    print("  1. In Apps Script, click 'Deploy' → 'Manage deployments'")
    print("  2. Find your active Web App deployment")
    print("  3. Click the pencil/edit icon and copy the 'Deployment ID'\n")
    deployment_id = input("Paste your Deployment ID here: ").strip()

    config = {"script_id": script_id, "deployment_id": deployment_id}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  ✓ Config saved to {CONFIG_FILE.name}")
    return config


def get_credentials():
    creds = None

    if not CREDENTIALS_FILE.exists():
        print(f"\n[ERROR] credentials.json not found.")
        print(f"  Expected location: {CREDENTIALS_FILE}")
        print("\n  To create it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. APIs & Services → Credentials")
        print("  3. Create Credentials → OAuth client ID → Desktop app")
        print("  4. Download JSON, rename it credentials.json, put it in this folder.")
        input("\nPress Enter to close...")
        sys.exit(1)

    print(f"  Found credentials.json")

    if TOKEN_FILE.exists():
        print(f"  Found existing token.json — attempting to reuse …")
        try:
            with open(TOKEN_FILE) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
            print(f"  Token loaded. Valid: {creds.valid}  Expired: {creds.expired}")
        except Exception as e:
            print(f"  Could not load token: {e}")
            creds = None
    else:
        print("  No token.json found — will open browser for login.")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Refreshing expired token …")
            try:
                creds.refresh(Request())
                print("  Token refreshed successfully.")
            except Exception as e:
                print(f"  Token refresh failed: {e}")
                creds = None

        if not creds or not creds.valid:
            print("  Opening browser for Google login …")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            print("  Login successful.")

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"  Token saved to {TOKEN_FILE.name}")

    return creds


def read_source_files():
    files = {}

    if HTML_FILE.exists():
        content = HTML_FILE.read_text(encoding="utf-8")
        files["Index"] = {"name": "Index", "type": "html", "source": content}
        print(f"  ✓ Index.html  ({len(content):,} chars)  path: {HTML_FILE}")
    else:
        print(f"  ✗ Index.html NOT FOUND at: {HTML_FILE}")

    if JS_FILE.exists():
        content = JS_FILE.read_text(encoding="utf-8")
        files["Code"] = {"name": "Code", "type": "server_js", "source": content}
        print(f"  ✓ code.js  ({len(content):,} chars)  path: {JS_FILE}")
    else:
        print(f"  ✗ code.js NOT FOUND at: {JS_FILE}")

    if not files:
        print("\n[ERROR] No source files found. Cannot continue.")
        input("\nPress Enter to close...")
        sys.exit(1)

    return files


def build_files_payload(new_files: dict, existing_files: list) -> list:
    existing = {f["name"]: f for f in existing_files}
    for name, file_obj in new_files.items():
        existing[name] = file_obj
    return list(existing.values())


def deploy(config, creds):
    service       = discovery.build("script", "v1", credentials=creds)
    script_id     = config["script_id"]
    deployment_id = config["deployment_id"]

    # ── 1. Fetch current project ──────────────────────────────────────────────
    print("\n[1/3] Fetching current project from Apps Script …")
    try:
        content = service.projects().getContent(scriptId=script_id).execute()
    except HttpError as e:
        print(f"\n[ERROR] Could not fetch project content.")
        print(f"  HTTP {e.resp.status}: {e.reason}")
        print(f"  Full error: {e.content.decode() if hasattr(e,'content') else e}")
        print("\n  Common causes:")
        print("  - Script ID is wrong (check Project Settings in Apps Script)")
        print("  - Apps Script API not enabled in Google Cloud Console")
        raise

    existing_files = content.get("files", [])
    print(f"  Existing files in project ({len(existing_files)}):")
    for f in existing_files:
        print(f"    - {f.get('name')}  (type: {f.get('type')})")

    # ── 2. Push updated files ─────────────────────────────────────────────────
    print("\n[2/3] Uploading updated files …")
    new_files       = read_source_files()
    updated_payload = build_files_payload(new_files, existing_files)
    print(f"  Sending {len(updated_payload)} file(s) total to Apps Script …")

    try:
        service.projects().updateContent(
            scriptId=script_id,
            body={"files": updated_payload},
        ).execute()
        print(f"  ✓ Files uploaded successfully")
    except HttpError as e:
        print(f"\n[ERROR] Failed to upload files.")
        print(f"  HTTP {e.resp.status}: {e.reason}")
        print(f"  Full error: {e.content.decode() if hasattr(e,'content') else e}")
        raise

    # ── 3. Create new deployment version ─────────────────────────────────────
    print("\n[3/3] Creating new deployment version …")

    print(f"  Fetching existing deployment {deployment_id} …")
    try:
        existing_dep = service.projects().deployments().get(
            scriptId=script_id,
            deploymentId=deployment_id,
        ).execute()
        print(f"  Existing deployment response:")
        print(f"    {json.dumps(existing_dep, indent=4)}")
    except HttpError as e:
        print(f"\n[ERROR] Could not fetch deployment.")
        print(f"  HTTP {e.resp.status}: {e.reason}")
        print(f"  Full error: {e.content.decode() if hasattr(e,'content') else e}")
        print("\n  Common causes:")
        print("  - Deployment ID is wrong (check Deploy → Manage Deployments in Apps Script)")
        raise

    current_description = (
        existing_dep.get("deploymentConfig", {}).get("description", "Deployed via script")
    )
    print(f"  Current description: '{current_description}'")

    # Step 3a: Create a new version snapshot of the current code
    print("  Creating a new version snapshot …")
    try:
        new_version_obj = service.projects().versions().create(
            scriptId=script_id,
            body={"description": current_description},
        ).execute()
        print(f"  New version response: {json.dumps(new_version_obj, indent=4)}")
    except HttpError as e:
        print(f"\n[ERROR] Failed to create new version.")
        print(f"  HTTP {e.resp.status}: {e.reason}")
        print(f"  Full error: {e.content.decode() if hasattr(e,'content') else e}")
        raise

    new_version_number = new_version_obj.get("versionNumber")
    print(f"  ✓ New version number: {new_version_number}")

    # Step 3b: Point the existing deployment at the new version,
    # preserving all existing deploymentConfig fields exactly as-is
    existing_config = existing_dep.get("deploymentConfig", {})
    updated_config  = dict(existing_config)          # copy everything (accessType, executeAs, etc.)
    updated_config["versionNumber"] = new_version_number

    print(f"  Updating deployment to point at v{new_version_number} …")
    print(f"  Sending deploymentConfig: {json.dumps(updated_config, indent=4)}")
    try:
        updated_dep = service.projects().deployments().update(
            scriptId=script_id,
            deploymentId=deployment_id,
            body={"deploymentConfig": updated_config},
        ).execute()
        print(f"  Update response:")
        print(f"    {json.dumps(updated_dep, indent=4)}")
    except HttpError as e:
        print(f"\n[ERROR] Failed to update deployment.")
        print(f"  HTTP {e.resp.status}: {e.reason}")
        print(f"  Full error: {e.content.decode() if hasattr(e,'content') else e}")
        raise

    final_version = updated_dep.get("deploymentConfig", {}).get("versionNumber", "?")
    print(f"\n✅  Done! Web App is now running v{final_version}. Your URL is unchanged.\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("═" * 60)
    print("  Vital Vortex Deployer")
    print("═" * 60)
    print(f"\n  Script dir: {SCRIPT_DIR}")
    print(f"  Root dir:   {ROOT_DIR}")

    try:
        config = load_config()
        print("\nAuthenticating with Google …")
        creds = get_credentials()
        print("✓ Authenticated\n")
        deploy(config, creds)
    except Exception as e:
        print(f"\n[FAILED] {type(e).__name__}: {e}")

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
