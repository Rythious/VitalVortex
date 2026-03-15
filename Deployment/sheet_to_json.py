"""
sheet_to_json.py — Pull Google Sheet data down into a local JSON file
======================================================================
Reads all three data sheets from the connected Google Sheet and writes
a fresh vitalvortex_data.json in the Vital Vortex folder.

  • "Menu" sheet      →  foods array
  • "Plan" sheet      →  plan blob
  • "Daily Log" sheet →  log dictionary

This completely overwrites the local JSON file, so the local copy will
match the Google Sheet exactly when done.

Usage:
    python sheet_to_json.py

Run this whenever you want to bring your local environment up to date
with data that was entered through the live deployed web app.

NOTE: If you'd rather not run this script, you can also:
  1. Open the Google Sheet
  2. File → Download → Microsoft Excel (.xlsx) or CSV
  3. Tell your assistant to use that file instead
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
except ImportError:
    print("\n[ERROR] Required packages not installed.")
    print("Run:  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib\n")
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
        print(f"\n[ERROR] credentials.json not found in {SCRIPT_DIR}")
        print("Follow the setup steps in SETUP.md to create it.\n")
        sys.exit(1)

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


def load_config():
    if not CONFIG_FILE.exists():
        print(f"\n[ERROR] deploy_config.json not found in {SCRIPT_DIR}")
        print("Run deploy.py first (or create the config manually).\n")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def get_spreadsheet_id(script_service, script_id):
    project   = script_service.projects().get(scriptId=script_id).execute()
    parent_id = project.get("parentId")
    if not parent_id:
        print("\n[ERROR] Could not find a Google Sheet linked to this Apps Script project.")
        print("Make sure the script is a *bound* script (created from inside a Google Sheet).\n")
        sys.exit(1)
    return parent_id


def read_sheet(sheets_service, spreadsheet_id, sheet_name):
    """Return all values from a sheet as a list of lists, or [] if the sheet doesn't exist."""
    try:
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'",
        ).execute()
        return result.get("values", [])
    except Exception:
        return []


# ── main logic ────────────────────────────────────────────────────────────────

def main():
    print("═" * 55)
    print("  Vital Vortex — Google Sheet → JSON")
    print("═" * 55)

    # Auth + services
    print("\nAuthenticating with Google …")
    creds = get_credentials()
    print("✓ Authenticated\n")

    config         = load_config()
    script_service = discovery.build("script", "v1", credentials=creds)
    sheets_service = discovery.build("sheets", "v4", credentials=creds)

    spreadsheet_id = get_spreadsheet_id(script_service, config["script_id"])
    print(f"Spreadsheet ID: {spreadsheet_id}\n")

    # ── Menu sheet → foods ────────────────────────────────────────────────────
    print("[1/3] Reading Menu sheet (foods) …")
    menu_rows = read_sheet(sheets_service, spreadsheet_id, "Menu")
    foods = []
    if len(menu_rows) > 1:
        headers = menu_rows[0]
        for row in menu_rows[1:]:
            # Pad short rows so zip doesn't drop columns
            padded = row + [""] * (len(headers) - len(row))
            obj = dict(zip(headers, padded))
            # Convert numeric fields from strings
            for num_field in ["id", "cal", "fat", "carb", "sugar", "fiber", "protein"]:
                try:
                    obj[num_field] = float(obj[num_field]) if "." in str(obj[num_field]) else int(obj[num_field])
                except (ValueError, TypeError):
                    obj[num_field] = 0
            foods.append(obj)
    print(f"      ✓ {len(foods)} foods read")

    # ── Plan sheet → plan blob ────────────────────────────────────────────────
    print("[2/3] Reading Plan sheet …")
    plan_rows = read_sheet(sheets_service, spreadsheet_id, "Plan")
    plan = plan_rows[0][0] if plan_rows and plan_rows[0] else ""
    print("      ✓ Plan read")

    # ── Daily Log sheet → log dict ────────────────────────────────────────────
    print("[3/3] Reading Daily Log sheet …")
    log_rows = read_sheet(sheets_service, spreadsheet_id, "Daily Log")
    log = {}
    if len(log_rows) > 1:
        log_headers = log_rows[0]
        for row in log_rows[1:]:
            if not row:
                continue
            padded = row + [""] * (len(log_headers) - len(row))
            obj    = dict(zip(log_headers, padded))
            date   = obj.pop("date", None)
            if not date:
                continue
            for num_field in ["cal", "fat", "carb", "sugar", "fiber", "protein", "water"]:
                try:
                    obj[num_field] = float(obj[num_field]) if "." in str(obj[num_field]) else int(obj[num_field])
                except (ValueError, TypeError):
                    obj[num_field] = 0
            log[date] = obj
    print(f"      ✓ {len(log)} log entries read")

    # ── Write JSON ────────────────────────────────────────────────────────────
    output = {"foods": foods, "plan": plan, "log": log}
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅  Done! {DATA_FILE.name} has been updated with the latest sheet data.")
    print("    Refresh the app in your browser (F5) to see the changes.")

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
