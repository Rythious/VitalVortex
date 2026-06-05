# Vital Vortex — Project Guide for Claude

## About This Project

**Vital Vortex** is a personal macro and nutrition tracking web app. It is a
self-hosted **Flask + SQLite** app, deployed with **Docker Compose on a
DigitalOcean droplet behind Caddy**, live at **https://vitalvortex.duckdns.org**.

It started life as a Google Apps Script web app backed by a Google Sheet; that
backend has been fully retired (see "History" below). Don't suggest Google
Sheet / Apps Script workflows — they no longer exist.

The app tracks daily meals across 5 slots (Breakfast, Morning Snack, Lunch,
Afternoon Snack, Dinner), water, macros (calories, protein, fat, carbs, sugar,
fiber) against per-user goals, a day-history calendar, a menstrual cycle tracker
with phase-aware food recommendations, and USDA food-database search for adding
foods. Each user has their own login and their own data.

See `README.md` for the full architecture and deployment reference. This file is
the orientation for Claude agents working in the repo.

---

## About the Collaborators

This repo is worked on by two people from two machines, and **two different Claude
agents read this file** — so adjust to whoever you're working with (the git
`user.name` is a good tell):

- **Carolyn** (`Carolyn Morgan`) — the app's creator and primary daily user.
  **She is not a developer and does not write code.** When working in her copy:
  - Don't ask her to edit code or run unfamiliar terminal commands.
  - Explain changes in plain, friendly terms; avoid jargon ("the app", not "the
    frontend"; "saved", not "persisted").
  - She develops features by describing them to her Claude agent, which edits
    `Index.html`. To preview a change locally she **just refreshes the browser
    (F5)**. To get a change onto the *live* site, the Docker image must be rebuilt
    and pushed (that's Justin's side — see Deployment).
  - If something breaks, give simple step-by-step recovery.

- **Justin** (`Justin Morgan`, rythious) — handles the VPS, Docker, and
  deployment. Normal technical depth is fine; he runs the droplet and pushes
  images.

---

## How to Make Changes — IMPORTANT

**`Index.html` is a large single-file app (~115KB — all HTML + CSS + JS).
Never rewrite the whole file.** Always make targeted, surgical edits:

1. **Read only the relevant section** (search for a unique nearby string rather
   than loading the whole file).
2. **Make a minimal edit** — match a unique snippet and replace just that.
3. **Verify** the edited region if unsure.
4. **Tell the user how to see it:** locally, refresh the browser (F5). For the
   live site, the image needs a rebuild + push (Deployment).

Full-file writes are only appropriate for small files (this file, `schema.sql`)
or brand-new files — never for `Index.html`.

---

## Architecture (for Claude)

```
Index.html        ← entire frontend (HTML + CSS + JS, one file, no build step)
app.py            ← Flask backend: serves Index.html at /, JSON API at /api, SQLite + auth
schema.sql        ← SQLite schema (users, foods, plan, log, settings), applied at startup
Dockerfile        ← python:3.12-slim image (gunicorn)
docker-compose.yml← one stack; publishes 127.0.0.1:8082 -> container 8080; two volumes
import_data.py    ← seed one user's foods/plan/log into SQLite from a JSON export
requirements.txt  ← Flask + gunicorn
README.md         ← architecture + deployment reference
```

**Backend (`app.py`).** Flask serves the static app and a single `/api` action
dispatcher, same origin (no CORS). Per-user login via server-side signed-cookie
sessions; every data action is scoped to the logged-in `user_id`. `init_db()`
runs `CREATE TABLE IF NOT EXISTS` at startup, so a new image provisions/updates
the DB automatically.

**`/api` actions:**

| Action | What it does |
|---|---|
| `read` / `write` | Get / replace the user's foods (write dedupes by id) |
| `loadplan` / `saveplan` | Get / save the daily-plan JSON blob |
| `readlog` / `log` | Get the history log / upsert one day. **A `log` with `entry: null` deletes that date** (used to unmark a period day and to move an entry to another date) |
| `login` / `logout` / `register` / `me` | Auth. `register` is gated by `VV_INVITE_CODE`; `me`/`login`/`register` also return `searchEnabled` |
| `loadsettings` / `savesettings` | Per-user profile, custom goals, and theme (one JSON blob) |
| `foodsearch` / `fooddetail` | Server-side proxy to USDA FoodData Central (key stays server-side) |

**Frontend (`Index.html`).** `apiFetch()` is a plain same-origin `fetch('/api…')`
with the session cookie (no `google.script.run`, no `IS_LOCAL`). Key state:
`state` (foods/meals/water/…), `dailyLog` (history keyed `YYYY-MM-DD`),
`periodDates`, `userProfile`/`customGoals`. `localStorage` is a per-user cache;
SQLite is the source of truth. Period markers are stored in the log under
`period_<date>` keys.

**Config (environment):** `VV_INVITE_CODE` (enable sign-up), `VV_FDC_API_KEY`
(enable food search), `VV_DB_PATH` (default `./vitalvortex.db`; `/data/...` in the
container), `VV_KEYS_DIR` (session secret; `/keys` in the container). On the VPS
these come from `/opt/vitalvortex/.env`.

---

## Running locally

```bash
pip install -r requirements.txt
flask --app app seed-user you@example.com "your-password"   # create a login
flask --app app run --port 8080                              # http://localhost:8080
```

A local `vitalvortex.db` and `keys/` dir are created on first run. Editing
`Index.html` → just refresh the browser. Editing `app.py` → restart the `flask`
process. (Both are gitignored locally.)

---

## Deployment (live site)

The live site runs the Docker image `rythious/vitalvortex:latest`. **Refreshing
the browser only shows local changes — the live site updates only when the image
is rebuilt and pushed.** Full steps are in `README.md` and `~/DevNotes/vps.md`:

```bash
# locally
docker build -t rythious/vitalvortex:latest .
docker push rythious/vitalvortex:latest
# on the droplet, in /opt/vitalvortex
docker compose pull && docker compose up -d
```

User data and the session key live in the `vitalvortex-data` and
`vitalvortex-keys` Docker volumes, so they survive redeploys.

---

## Source Control (Git)

The repo has a GitHub remote (`origin` = `github.com:Rythious/VitalVortex`).
Carolyn's feature work is committed on her machine and pushed to origin; Justin
pulls and deploys.

- **Commit after a change is working** — not broken/half-finished work.
- Branch off `main` for new work; don't push unless asked.
- Commit messages: plain present-tense English describing the change
  (`Add cycle phase banner to Tomorrow tab`, `Fix water cups not saving`).
- `vitalvortex_data.json`, `*.db`, and `keys/` are gitignored — personal data and
  runtime files are never committed.

---

## History (retired)

Originally a Google Apps Script web app reading/writing a Google Sheet, with a
local Python `server.py` + JSON file for development and sync scripts in a
`Deployment/` folder. All of that (`code.js`, `server.py`, `Deployment/`, the
`.bat` launchers) was removed when the app moved to Flask + SQLite on the VPS.
The historical Sheet data was migrated into SQLite once via `import_data.py`,
which remains as a general JSON-seeding utility.
