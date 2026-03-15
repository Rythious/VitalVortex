# Vital Vortex Deployment — Setup Guide

This folder contains three scripts that connect your local Vital Vortex app
to your live Google Apps Script web app and Google Sheet.

| Script | What it does |
|---|---|
| `deploy.py` | Pushes the latest `Index.html` and `code.js` to Google Apps Script and creates a new version of the live web app |
| `json_to_sheet.py` | Copies all data from your local `vitalvortex_data.json` **up** into the Google Sheet |
| `sheet_to_json.py` | Pulls all data from the Google Sheet **down** into your local `vitalvortex_data.json` |

---

## One-time setup (do this before running any script)

### Step 1 — Make sure Python is installed

Open Command Prompt and run:

```
python --version
```

If you see `Python 3.x.x` you're good. If not, download it from https://python.org.

---

### Step 2 — Install the required packages

In Command Prompt, navigate to this folder and run:

```
pip install -r requirements.txt
```

---

### Step 3 — Enable the required APIs in Google Cloud

1. Go to https://console.cloud.google.com/
2. In the top bar, click the project selector and pick the project that owns
   your Apps Script. If there is no project, click **New Project**, give it
   any name, and click Create.
3. Search for **"Google Apps Script API"** and click **Enable**.
4. Search for **"Google Sheets API"** and click **Enable**.

> Both APIs must be enabled. The Apps Script API lets the scripts push code
> and look up your spreadsheet ID. The Sheets API lets them read and write
> your actual data.

---

### Step 4 — Create OAuth credentials

Still in Google Cloud Console:

1. Go to **APIs & Services → Credentials** in the left sidebar.
2. Click **+ Create Credentials → OAuth client ID**.
3. If prompted to configure a consent screen first:
   - Choose **External**, click Create.
   - Fill in just the App name (e.g. "Vital Vortex") and your email.
   - Skip scopes, skip test users, click Save and Continue until done.
4. Back on Create OAuth client ID:
   - Application type: **Desktop app**
   - Name: anything (e.g. "Vital Vortex Scripts")
   - Click **Create**
5. Click **Download JSON** on the confirmation dialog.
6. Rename the downloaded file to exactly `credentials.json`.
7. Move it into this `Deployment` folder.

---

### Step 5 — Find your Script ID and Deployment ID

**Script ID:**
1. Open your Apps Script project at https://script.google.com
2. Click the ⚙️ gear icon (Project Settings) in the left sidebar
3. Copy the **Script ID**

**Deployment ID:**
1. In Apps Script, click **Deploy → Manage deployments**
2. Find your active Web App deployment
3. Click the ✏️ edit icon
4. Copy the **Deployment ID** (looks like `AKfycb...`)

The first time you run `deploy.py` it will ask you to paste these in.
They get saved to `deploy_config.json` automatically so you never need to
enter them again.

---

## Everyday usage

### To publish a new version of the web app:

Just double-click `deploy.py` (or run `python deploy.py` in Command Prompt).
It will push the latest `Index.html` and `code.js` to Apps Script and create
a new version. Your web app URL stays the same.

### To push your local food data up to the Google Sheet (do this once to seed it):

Run `python json_to_sheet.py`. This copies everything from
`vitalvortex_data.json` into the Google Sheet — foods, today's plan, and
your history log.

### To pull the latest Google Sheet data down to your local machine:

Run `python sheet_to_json.py`. This overwrites your local
`vitalvortex_data.json` with whatever is in the Google Sheet, then refresh
the browser (F5) to see the updated data in the app.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `credentials.json not found` | Make sure the file is in this `Deployment` folder |
| `Access Not Configured` error | Make sure you enabled **both** APIs in Step 3 |
| Browser doesn't open for auth | Run the script from a regular Command Prompt, not VS Code terminal |
| `insufficientPermissions` | Delete `token.json` and re-run to re-authenticate |
| `Could not find a Google Sheet linked...` | The Apps Script must be a *bound* script — created from inside a Google Sheet, not a standalone script at script.google.com |
