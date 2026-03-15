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

Git is installed and the repo is initialized in `C:\Vital Vortex`. There is no remote — it is purely a local safety net so changes can be reverted if something goes wrong. **The user does not know what git is and does not need to interact with it at all.** Claude handles all commits silently as part of its normal workflow.

### What is tracked vs. ignored

`vitalvortex_data.json` is listed in `.gitignore` and is **never committed** — it contains personal daily food and health data. Everything else (`Index.html`, `server.py`, `CLAUDE.md`, etc.) is tracked.

### When to commit

Commit **after every successful change** — once a feature or fix is working and the user is happy with it. Do not commit broken or half-finished work.

### How to commit

Use `bash_tool` to run git commands in the repo directory:

```bash
cd "C:\Vital Vortex" && git add -A && git commit -m "your message here"
```

Write commit messages in plain present-tense English that describe what the change does from the user's perspective — not technical implementation details. Good examples:

- `Add calorie goal progress bar to Today page`
- `Fix water cups not saving after browser refresh`
- `Change protein goal default to 120g`
- `Add new Dinner section to meal planner`

### How to check history or revert (if ever needed)

If something breaks and needs to be rolled back, you can:

```bash
# See recent commits
cd "C:\Vital Vortex" && git log --oneline -10

# Revert the last commit (keeps files, undoes commit)
cd "C:\Vital Vortex" && git revert HEAD

# Hard reset to a specific commit (use commit hash from log)
cd "C:\Vital Vortex" && git reset --hard <hash>
```

If a revert is needed, handle it yourself — do not ask the user to run git commands.

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

- **`API_URL`** — points to `http://localhost:8765/api`
- **`apiFetch()`** — talks to local server instead of Google Apps Script
- **`STARTER_FOODS`** — 42 hardcoded starter foods, seeded into `vitalvortex_data.json` on first launch if it's empty
- **`state`** — in-memory app state (foods, meals, water, tomorrowMeals, nextId)
- **`localStorage`** — used as a fast in-browser cache; the JSON file is the source of truth
- **`dailyLog`** — history of saved days, keyed by `YYYY-MM-DD`

### Data actions handled by `server.py`:

| Action | Method | What it does |
|---|---|---|
| `read` | GET | Returns all foods from `vitalvortex_data.json` |
| `write` | POST | Overwrites the foods array in the JSON file |
| `loadplan` | GET | Returns the saved daily plan blob |
| `saveplan` | POST | Saves the daily plan blob |
| `readlog` | GET | Returns the full history log |
| `log` | POST | Writes or updates a single day's log entry |

---

## Future: Syncing Back to Google Sheets

`code.js` contains the original Google Apps Script backend. When it's time to go back to the live web app, a sync script should:

1. Read `vitalvortex_data.json`
2. Push the `foods` array to the `Menu` sheet
3. Push the `log` entries to the `Daily Log` sheet
4. Push the `plan` blob to the `Plan` sheet
5. Copy the contents of `Index.html` into the Google Apps Script `Index.html` file
6. Deploy a new version of the web app

The API shape in `code.js` matches exactly what `server.py` implements locally, so the HTML file should work in both environments with only the `API_URL` constant needing to change.
