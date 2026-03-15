# Vital Vortex — Project Guide for Claude

## About This Project

**Vital Vortex** is a personal macro and nutrition tracking web app. It was originally built as a Google Apps Script web app backed by a Google Sheet, but is currently running in a local development mode for faster iteration.

The app tracks daily meals across 5 meal slots (Breakfast, Morning Snack, Lunch, Afternoon Snack, Dinner), water intake, macros (calories, protein, fat, carbs, sugar, fiber), a protein goal, and a day history calendar.

---

## About the Collaborator

**The person you are working with is not a developer and does not know how to write code.** Please keep this in mind at all times:

- Do not ask her to edit code files directly.
- Do not give her terminal commands to run (beyond what's already set up).
- Explain what a change will do in plain, friendly terms before making it.
- When a change is complete, tell her clearly what to do to see it — almost always: **"just refresh the browser (F5)"**.
- If something goes wrong, give simple step-by-step recovery instructions.
- Avoid jargon. Say "the app" not "the frontend". Say "saved" not "persisted to the filesystem".

---

## Source Control (Git)

Git is installed and the repo is initialized in `C:\Vital Vortex`. There is no remote — it is purely a local safety net so changes can be reverted if something goes wrong. **The user does not know what git is and does not need to interact with it at all.**

### What is tracked vs. ignored

`vitalvortex_data.json` is listed in `.gitignore` and is **never committed** — it contains personal daily food and health data. Everything else (`Index.html`, `server.py`, `CLAUDE.md`, etc.) is tracked.

### How Claude handles git

Claude has direct access to git via the `git` MCP server. **The user never needs to run any git commands herself.** Claude handles all of this silently.

Tools available: `git:git_status`, `git:git_add`, `git:git_commit`, `git:git_log`, `git:git_diff_unstaged`, `git:git_diff_staged`, `git:git_branch`, `git:git_reset`.

All git tool calls use `repo_path: C:\Vital Vortex`.

### When to commit

After every successful change — once a feature or fix is working and she's happy with it. Do not commit broken or half-finished work. Stage with `git:git_add` then commit with `git:git_commit`.

### Commit message style

Plain present-tense English describing what changed from her perspective:
- `Add calorie goal progress bar to Today page`
- `Fix water cups not saving after browser refresh`
- `Add deployment scripts and data sync tools`

### How to revert (if something breaks)

Use `git:git_log` to find the target commit hash, then ask her to open Command Prompt and run:
```
cd "C:\Vital Vortex" && git reset --hard <hash>
```
Explain in plain terms what this does before asking her to run it.

---

## How to Make Changes — IMPORTANT

**`Index.html` is a large file (~60KB). Never rewrite the whole file to make a change.**

Always use `filesystem:edit_file` to make targeted, surgical edits. This tool does line-based find-and-replace — provide the exact lines to replace (`oldText`) and the new lines (`newText`).

### Correct workflow for any change:

1. **Read only the relevant section** — use `head` or `tail` on `filesystem:read_text_file` to find the area you need, rather than loading the entire file. If you need a specific function, search for a few lines of it.
2. **Make the edit with `filesystem:edit_file`** — provide the minimal `oldText` that is unique in the file, and the replacement `newText`.
3. **Verify** — optionally re-read just the edited section to confirm it looks right.
4. **Tell her to refresh** — she just needs to hit F5 in the browser.

### Example — changing a button label:

```
filesystem:edit_file(
  path = "C:\\Vital Vortex\\Index.html",
  edits = [{ oldText: "🗓 Save & Clear Today's Meals", newText: "🗓 Save Day & Start Fresh" }]
)
```

### When `filesystem:write_file` IS appropriate:
- Creating a brand new file that doesn't exist yet.
- `server.py` needs a structural overhaul (rare).
- The file is small (like `CLAUDE.md` or `Start Vital Vortex.bat`).

**Never use `filesystem:write_file` on `Index.html` just to make a small change.** It's slow, error-prone, and risks losing content.

---

## How the Local Setup Works

The app runs via a tiny Python web server. Here is the full picture:

```
C:\Vital Vortex\
  Index.html              ← The entire app (HTML + CSS + JavaScript in one file)
  server.py               ← Local Python server (serves the HTML, handles data reads/writes)
  Start Vital Vortex.bat  ← Double-click launcher (starts server + opens browser)
  vitalvortex_data.json   ← All app data (foods, daily plan, history log) — auto-created on first run
  code.js                 ← Google Apps Script backend (NOT used locally — kept for future sync)
  CLAUDE.md               ← This file
```

**To start the app:** Double-click `Start Vital Vortex.bat`. It opens a terminal window and launches `http://localhost:8765` in the browser. The terminal must stay open while the app is in use.

**To stop the app:** Close the terminal window (or press Ctrl+C inside it).

**The app talks to `server.py` via `http://localhost:8765/api`** for all data operations. Data is stored in `vitalvortex_data.json`.

---

## When Changes Take Effect

| What changed | What she needs to do |
|---|---|
| `Index.html` (the app UI, styles, or behavior) | **Just refresh the browser** (F5 or Ctrl+R). No restart needed. |
| `server.py` (the local server logic) | **Restart the .bat file** — close the terminal window and double-click `Start Vital Vortex.bat` again. |
| `vitalvortex_data.json` (data edited manually) | **Just refresh the browser**. |

**In practice, almost all changes will be to `Index.html`, which means she will almost always just need to refresh the browser.**

---

## App Architecture (for Claude)

All app logic lives in `Index.html` as a single-file app:

- **`IS_LOCAL`** — detected at runtime; `true` when running on localhost, `false` when deployed
- **`API_URL`** — points to `http://localhost:8765/api` (only used when `IS_LOCAL` is true)
- **`apiFetch()`** — when local, calls the Python server via `fetch()`; when deployed, calls `google.script.run.handleRequest()` directly
- **`STARTER_FOODS`** — hardcoded starter foods, seeded into storage on first launch if empty
- **`state`** — in-memory app state (foods, meals, water, tomorrowMeals, nextId)
- **`localStorage`** — used as a fast in-browser cache; the backing store (JSON file or Google Sheet) is the source of truth
- **`dailyLog`** — history of saved days, keyed by `YYYY-MM-DD`

### Data actions (handled by both `server.py` locally and `code.js` when deployed):

| Action | What it does |
|---|---|
| `read` | Returns all foods |
| `write` | Overwrites the foods array |
| `loadplan` | Returns the saved daily plan blob |
| `saveplan` | Saves the daily plan blob |
| `readlog` | Returns the full history log |
| `log` | Writes or updates a single day's log entry |

---

## Deployment (Live Web App)

The app is deployed as a Google Apps Script web app. The live version runs in the browser (including on her phone) without needing the local Python server.

**The deployed app reads and writes directly to the Google Sheet** — it does not use `vitalvortex_data.json`. The local JSON file and the Google Sheet are two separate data stores that must be explicitly synced using the scripts below.

**Her agreement:** She only uses the deployed web app URL for entering real daily data. Local development is for app changes only, not for tracking food.

### Deployment scripts (all live in `C:\Vital Vortex\Deployment\`):

| Script | What it does | When to use |
|---|---|---|
| `deploy.py` | Pushes the latest `Index.html` and `code.js` to Google Apps Script and creates a new version | After any change to the app UI or backend logic |
| `json_to_sheet.py` | Copies all data from local `vitalvortex_data.json` **up** into the Google Sheet | Once after a local data editing session, or to seed the sheet with new foods added locally |
| `sheet_to_json.py` | Pulls all data from the Google Sheet **down** into local `vitalvortex_data.json` | Before a local work session, to make sure local data reflects what was entered in the live app |

**To run a script:** Double-click the `.py` file, or open Command Prompt in the `Deployment` folder and type `python scriptname.py`. The window will stay open until she presses Enter.

**All three scripts share the same Google login token.** The first time after the token is deleted, whichever script runs first will open a browser login. After that, all scripts reuse the cached token automatically.

---

## Data Sync — When to Suggest Which Script

This is important. The local `vitalvortex_data.json` and the live Google Sheet are **not automatically in sync**. As an agent working locally, you can only see what is in `vitalvortex_data.json`. Data entered through the deployed web app (e.g. on her phone) lives in the Google Sheet and is invisible to you until synced down.

### Trigger rules for agents:

**Suggest running `sheet_to_json.py` when:**
- She asks about data (foods, history, log entries) and the local JSON file is empty, missing entries, or clearly out of date relative to what she describes
- She says something like "I logged that yesterday" or "I added that food last week" but it doesn’t appear in `vitalvortex_data.json`
- She mentions she has been using the app on her phone or via the website
- She asks you to analyze her history or food list and the data looks sparse or stale
- She asks "why doesn’t my data show up" or similar
- **In general: if you need to look at her data and `vitalvortex_data.json` seems incomplete, always suggest this script first before concluding the data doesn’t exist.**

**Suggest running `json_to_sheet.py` when:**
- You (the agent) have just made significant additions to `vitalvortex_data.json` locally (e.g. added many new foods she researched)
- She wants changes made locally to appear in the live app on her phone
- She says "push my changes up" or similar

**Suggest running `deploy.py` when:**
- You have just made changes to `Index.html` or `code.js` that she wants to appear in the live deployed app
- She says "publish" or "deploy" or "update the live app"

### How to phrase the suggestion (keep it simple):

> “I don’t see that data in your local file — it might only exist in the live app. To pull it down, double-click **sheet_to_json.py** in your Deployment folder, wait for it to finish, then come back and I’ll take another look.”
