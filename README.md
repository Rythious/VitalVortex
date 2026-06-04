# Vital Vortex

A personal macro and nutrition tracker. Plan meals across five slots (Breakfast,
Morning Snack, Lunch, Afternoon Snack, Dinner), track water and macros (calories,
protein, fat, carbs, sugar, fiber) against per-user goals, and keep a day-by-day
history calendar.

Live at **https://vitalvortex.duckdns.org**.

Originally a Google Apps Script web app backed by a Google Sheet; now a small
self-hosted Flask + SQLite app deployed the same way as TheChoreDrawer (Docker
Compose on a DigitalOcean droplet behind Caddy).

---

## Tech stack

| Layer        | Choice                                                       |
|--------------|--------------------------------------------------------------|
| Frontend     | Single-file app (`Index.html`) — HTML + CSS + JS, no build   |
| Backend      | Flask, served by gunicorn                                    |
| Data access  | `sqlite3` (stdlib), one connection per request               |
| Database     | **SQLite**, single file on a persisted volume                |
| Auth         | Per-user login, server-side signed-cookie sessions           |
| Container    | Single-stage Docker image on `python:3.12-slim`              |
| Runtime host | Docker Compose on a DigitalOcean droplet behind Caddy        |

---

## Architecture

### Application

- **One process, one origin.** Flask serves both the static app (`/`) and the
  JSON API (`/api`). Same origin means no CORS and the session cookie rides along
  automatically — the frontend is just `fetch('/api?...')`.
- **The API is a 6-action dispatcher** carried over verbatim from the original
  Apps Script / local-server design, so the frontend's data layer was almost
  unchanged: `read` / `write` (foods), `loadplan` / `saveplan` (the plan blob),
  `readlog` / `log` (the day history). Three auth actions were added:
  `login` / `logout` / `me`.
- **Every data action is scoped to the logged-in `user_id`** pulled from the
  session, so each person's foods, plan, and history are fully separate.
- **Schema applied at startup.** `init_db()` runs `CREATE TABLE IF NOT EXISTS`
  on import (gunicorn boot), so deploying a new image provisions the DB with no
  manual migration step — the same "migrate on boot" idea ChoreDrawer uses.

### Persistence

- **SQLite over a database server.** Single instance, light traffic, file-based
  DB — no Postgres container, no pooling. Same accepted trade-off as ChoreDrawer.
- **Two named volumes**, because two things must survive container replacement:
  1. `vitalvortex-data` → `/data` — the SQLite file (`vitalvortex.db`).
  2. `vitalvortex-keys` → `/keys` — the Flask **session secret**
     (`SECRET_KEY`). This is the direct analog of ChoreDrawer's Data Protection
     keys volume: the key is generated once on first boot and read thereafter, so
     it stays stable across restarts. **Without it, every redeploy regenerates the
     key and logs everyone out.** Persist it and the problem disappears.

### Container

The app listens on plain **`http://0.0.0.0:8080`** inside the container — TLS is
terminated upstream by Caddy, so the container never deals with certificates.
`requirements.txt` is copied and installed before the source so the pip layer is
cached until dependencies change.

---

## Running locally

```bash
pip install -r requirements.txt
flask --app app seed-user you@example.com "your-password"   # create a login
flask --app app run --port 8080                              # http://localhost:8080
```

The SQLite file `vitalvortex.db` and a `keys/` dir are created in the working
directory on first run. `flask --app app list-users` shows accounts.

### Run the container locally

```bash
docker compose up --build      # http://localhost:8082
```

---

## Accounts

Each user has their own login and their own data (foods, plan, history,
**and** profile/goals/theme — all scoped per `user_id`).

**Self-serve sign-up is gated by a shared invite code.** Set `VV_INVITE_CODE` in
the environment (a `.env` file next to `docker-compose.yml`) and hand the code to
people you want to let in. The login screen has a "Sign up" toggle that asks for
the code. Leave `VV_INVITE_CODE` unset to disable sign-up entirely.

```
# /opt/vitalvortex/.env
VV_INVITE_CODE=some-shared-secret
```

You can also create or reset accounts directly from the CLI (no invite needed):

```bash
# locally, or inside the container with `docker compose exec vitalvortex …`
flask --app app seed-user her@email.com "her-password"
flask --app app list-users
```

Re-running `seed-user` for an existing email just resets that user's password.

### Per-user settings

Profile (sex, age, height, weight, goals), custom macro goals, and theme are
stored server-side per user (a `settings` JSON blob), so they follow a person
across devices. The BMR calculation branches on sex (Mifflin-St Jeor), so goals
are correct for any user — not just the original single female user the app was
first written for. A brand-new account is prompted to fill in its profile on
first login rather than inheriting placeholder defaults.

> Note: the original Google Sheet stored only foods/plan/history, never the
> profile (that lived in the browser). So after importing, the first login on the
> new app will prompt for profile setup once.

### Food database search (USDA FoodData Central)

On the Menu page, "Add New Food" includes a **search box** backed by USDA
FoodData Central: search a food, pick a result, choose a serving (named household
measures like "1 cup (240 g)" plus an editable gram amount), and the macros
auto-fill — then save as usual. Covers generic whole foods and branded products.

Enable it by setting a free API key (from <https://fdc.nal.usda.gov/api-key-signup.html>)
in the same `.env`:

```
# /opt/vitalvortex/.env
VV_FDC_API_KEY=your-fdc-key
```

The key stays server-side — the app proxies the API through two auth-gated
actions (`foodsearch`, `fooddetail`), so it's never exposed to the browser and
the proxy can't be used by anyone who isn't logged in. Leave `VV_FDC_API_KEY`
unset to disable the feature; the search box hides itself and manual entry still
works. USDA data is public domain, so imported foods can be stored permanently
with no licensing restriction.

---

## Deployment

Same workflow as the other apps on the droplet (see `~/DevNotes/vps.md`). DNS and
the Caddy route for `vitalvortex.duckdns.org → localhost:8082` already exist, so
there are **no infra changes** — just ship the image and bring up the stack.

### One-time setup on the host

1. Copy this repo's `docker-compose.yml` to `/opt/vitalvortex/docker-compose.yml`.
2. The Caddy block for `vitalvortex.duckdns.org` is already present. Done.

### Ship a new version

```bash
# locally
docker build -t rythious/vitalvortex:latest .
docker push rythious/vitalvortex:latest

# on the droplet, in /opt/vitalvortex
docker compose pull
docker compose up -d
```

Schema is created/upgraded at startup; data and the session key live in named
volumes, so this is the entire deploy.

---

## Migrating the existing Google Sheet data (one-time)

The original history lived in the Google Sheet. To bring it into SQLite:

1. On the machine that has Google access, run `Deployment/sheet_to_json.py` to
   produce a fresh `vitalvortex_data.json` from the sheet.
2. Build a local DB seeded with that data under her account:

   ```bash
   python import_data.py vitalvortex_data.json her@email.com "her-password"
   ```

   This creates `vitalvortex.db` with her foods, plan, and full day history.
3. Push the DB into the live volume (procedure from `vps.md`):

   ```bash
   scp vitalvortex.db root@<droplet>:/tmp/vitalvortex.db
   docker compose -f /opt/vitalvortex/docker-compose.yml stop
   docker cp /tmp/vitalvortex.db <container>:/data/vitalvortex.db
   docker compose -f /opt/vitalvortex/docker-compose.yml start
   ```

Add the second account with `seed-user` (above) once the container is up.
