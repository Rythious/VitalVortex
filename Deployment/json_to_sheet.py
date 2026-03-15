"""
json_to_sheet.py — Push local data into the Google Sheet
=========================================================
Reads vitalvortex_data.json from the Vital Vortex folder and writes all of
its data into the connected Google Sheet:

  • foods  →  "Menu" sheet
  • plan   →  "Plan" sheet
  • log    →  "Daily Log" sheet

Usage:
    python json_to_sheet.py
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

# ── paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR       = Path(__file__).parent
ROOT_DIR         = SCRIPT_DIR.parent
CONFIG_FILE      = SCRIPT_DIR / "deploy_config.json"
TOKEN_FILE       = SCRIPT_DIR / "token.json"
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"
DATA_FILE        = ROOT_DIR / "vitalvortex_data.json"

SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
    "https://www.googleapis.com/auth/spreadsheets",
]

# ── auth ──────────────────────────────────────────────────────────────────────

def get_credentials():
    creds = None

    if not CREDENTIALS_FILE.exists():
        print(f"\n[ERROR] credentials.json not found at: {CREDENTIALS_FILE}")
        input("Press Enter to close...")
        sys.exit(1)

    print(f"  Found credentials.json")

    if TOKEN_FILE.exists():
        print(f"  Found existing token.json — attempting to reuse …")
        try:
            with open(TOKEN_FILE) as f:
                creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
            print(f"  Token loaded. Valid: {creds.valid}  Expired: {creds.expired}")
            print(f"  Token scopes: {list(creds.scopes) if creds.scopes else '(none recorded)'}")
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


def load_config():
    if not CONFIG_FILE.exists():
        print(f"\n[ERROR] deploy_config.json not found at: {CONFIG_FILE}")
        input("Press Enter to close...")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    print(f"  Script ID:  {config.get('script_id', '(missing)')}")
    return config


def get_spreadsheet_id(script_service, script_id):
    print(f"  Looking up spreadsheet bound to script {script_id} …")
    try:
        project = script_service.projects().get(scriptId=script_id).execute()
    except HttpError as e:
        print(f"\n[ERROR] Could not fetch Apps Script project.")
        print(f"  HTTP {e.resp.status}: {e.reason}")
        print(f"  Full error: {e.content.decode() if hasattr(e,'content') else e}")
        print("\n  Make sure:")
        print("  - The Apps Script API is enabled in Google Cloud Console")
        print("  - The Script ID in deploy_config.json is correct")
        raise

    print(f"  Project response: {json.dumps(project, indent=4)}")

    parent_id = project.get("parentId")
    if not parent_id:
        print("\n[ERROR] No parentId found in project response.")
        print("  This means the Apps Script is a standalone script, not bound to a Sheet.")
        print("  The script must be created from *inside* a Google Sheet")
        print("  (Extensions → Apps Script) to have a parent spreadsheet.")
        input("\nPress Enter to close...")
        sys.exit(1)

    print(f"  ✓ Spreadsheet ID: {parent_id}")
    return parent_id


def ensure_sheet(sheets_service, spreadsheet_id, sheet_name):
    meta = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_names = [s["properties"]["title"] for s in meta.get("sheets", [])]
    print(f"  Sheets in spreadsheet: {existing_names}")

    if sheet_name in existing_names:
        print(f"  Sheet '{sheet_name}' already exists.")
        return

    print(f"  Creating sheet '{sheet_name}' …")
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()
    print(f"  ✓ Sheet '{sheet_name}' created.")


def clear_and_write(sheets_service, spreadsheet_id, sheet_name, rows):
    print(f"  Clearing '{sheet_name}' …")
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'",
    ).execute()
    print(f"  Cleared.")

    if rows:
        print(f"  Writing {len(rows)} row(s) to '{sheet_name}' …")
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
        print(f"  Write result: updatedRows={result.get('updatedRows')}, updatedCells={result.get('updatedCells')}")
    else:
        print(f"  No rows to write for '{sheet_name}' — left empty.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("═" * 60)
    print("  Vital Vortex — JSON → Google Sheet")
    print("═" * 60)
    print(f"\n  Script dir: {SCRIPT_DIR}")
    print(f"  Root dir:   {ROOT_DIR}")
    print(f"  Data file:  {DATA_FILE}")

    try:
        # Load local data
        if not DATA_FILE.exists():
            print(f"\n[ERROR] Data file not found: {DATA_FILE}")
            input("\nPress Enter to close...")
            sys.exit(1)

        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)

        foods = data.get("foods", [])
        plan  = data.get("plan", "")
        log   = data.get("log", {})
        print(f"\n  Loaded from JSON: {len(foods)} foods, {len(log)} log entries")

        # Auth + services
        print("\nAuthenticating with Google …")
        creds = get_credentials()
        print("✓ Authenticated\n")

        config         = load_config()
        script_service = discovery.build("script", "v1", credentials=creds)
        sheets_service = discovery.build("sheets", "v4", credentials=creds)

        spreadsheet_id = get_spreadsheet_id(script_service, config["script_id"])

        # ── Menu sheet ────────────────────────────────────────────────────────
        print("\n[1/3] Writing Menu sheet (foods) …")
        ensure_sheet(sheets_service, spreadsheet_id, "Menu")
        food_headers = ["id", "name", "portion", "cal", "fat", "carb", "sugar", "fiber", "protein"]
        food_rows = [food_headers] + [
            [f.get("id",""), f.get("name",""), f.get("portion",""),
             f.get("cal",0), f.get("fat",0), f.get("carb",0),
             f.get("sugar",0), f.get("fiber",0), f.get("protein",0)]
            for f in foods
        ]
        clear_and_write(sheets_service, spreadsheet_id, "Menu", food_rows)
        print(f"  ✓ {len(foods)} foods written to Menu sheet")

        # ── Plan sheet ────────────────────────────────────────────────────────
        print("\n[2/3] Writing Plan sheet …")
        ensure_sheet(sheets_service, spreadsheet_id, "Plan")
        clear_and_write(sheets_service, spreadsheet_id, "Plan", [[plan]] if plan else [])
        print("  ✓ Plan written")

        # ── Daily Log sheet ───────────────────────────────────────────────────
        print("\n[3/3] Writing Daily Log sheet …")
        ensure_sheet(sheets_service, spreadsheet_id, "Daily Log")
        log_headers = ["date", "cal", "fat", "carb", "sugar", "fiber", "protein", "water"]
        log_rows = [log_headers] + [
            [date,
             entry.get("cal",0), entry.get("fat",0), entry.get("carb",0),
             entry.get("sugar",0), entry.get("fiber",0), entry.get("protein",0),
             entry.get("water",0)]
            for date, entry in sorted(log.items())
        ]
        clear_and_write(sheets_service, spreadsheet_id, "Daily Log", log_rows)
        print(f"  ✓ {len(log)} log entries written to Daily Log sheet")

        print("\n✅  Done! Google Sheet is now up to date.")

    except Exception as e:
        print(f"\n[FAILED] {type(e).__name__}: {e}")

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
