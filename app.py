#!/usr/bin/env python3
"""
Vital Vortex - Flask backend (VPS / SQLite).

Serves the single-page app (Index.html) and a small JSON API at /api, backed by
SQLite and gated behind per-user login (server-side signed-cookie sessions).

The API keeps the exact 6-action contract the frontend already speaks
(read / write / loadplan / saveplan / readlog / log) and adds three auth actions
(login / logout / me). Every data action is scoped to the logged-in user_id.

Config via environment:
    VV_DB_PATH    path to the SQLite file        (default ./vitalvortex.db)
    VV_KEYS_DIR   dir holding the session secret  (default ./keys)
In the container these point at the two persisted volumes (/data, /keys).

CLI:
    flask --app app init-db
    flask --app app seed-user <email> <password>
    flask --app app list-users
"""

import json as _json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

import click
from flask import Flask, g, request, jsonify, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VV_DB_PATH", os.path.join(BASE_DIR, "vitalvortex.db"))
KEYS_DIR = os.environ.get("VV_KEYS_DIR", os.path.join(BASE_DIR, "keys"))
HTML_FILE = os.path.join(BASE_DIR, "Index.html")
SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")

# USDA FoodData Central API key (kept server-side; the browser never sees it).
# When unset, the food-search feature is disabled and the UI hides it.
FDC_API_KEY = os.environ.get("VV_FDC_API_KEY", "")
FDC_BASE = "https://api.nal.usda.gov/fdc/v1"


def load_secret_key():
    """Read the session secret from the keys dir, generating it on first boot.

    This is the Flask analog of ChoreDrawer's persisted Data Protection keys:
    keep the key stable across container restarts so sessions (signed cookies)
    survive every redeploy instead of logging everyone out.
    """
    os.makedirs(KEYS_DIR, exist_ok=True)
    key_path = os.path.join(KEYS_DIR, "secret_key")
    if os.path.exists(key_path):
        with open(key_path, "r", encoding="utf-8") as f:
            existing = f.read().strip()
            if existing:
                return existing
    key = secrets.token_hex(32)
    with open(key_path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app = Flask(__name__, static_folder=None)
app.config.update(
    SECRET_KEY=load_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Caddy terminates TLS upstream; cookie is delivered over HTTPS in production.
    SESSION_COOKIE_SECURE=os.environ.get("VV_COOKIE_SECURE", "1") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,  # 30 days
)


# ─── Database helpers ───────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()
    con.close()


# ─── Auth ───────────────────────────────────────────────────────────────────

def current_user_id():
    return session.get("user_id")


def login_required_error():
    return jsonify({"ok": False, "error": "auth required"}), 401


def do_login(body):
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    row = get_db().execute(
        "SELECT id, pw_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
    if row and check_password_hash(row["pw_hash"], password):
        session.clear()
        session.permanent = True
        session["user_id"] = row["id"]
        session["email"] = email
        return jsonify({"ok": True, "email": email, "searchEnabled": bool(FDC_API_KEY)})
    return jsonify({"ok": False, "error": "invalid credentials"}), 401


def do_logout():
    session.clear()
    return jsonify({"ok": True})


def do_register(body):
    """Self-serve sign-up gated by a shared invite code (VV_INVITE_CODE)."""
    required = os.environ.get("VV_INVITE_CODE", "")
    if not required:
        return jsonify({"ok": False, "error": "registration is disabled"}), 403
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    invite = body.get("invite") or ""
    if invite != required:
        return jsonify({"ok": False, "error": "invalid invite code"}), 403
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "a valid email is required"}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "password must be at least 6 characters"}), 400
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return jsonify({"ok": False, "error": "that email is already registered"}), 409
    db.execute(
        "INSERT INTO users (email, pw_hash) VALUES (?, ?)",
        (email, generate_password_hash(password)),
    )
    db.commit()
    uid = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
    session.clear()
    session.permanent = True
    session["user_id"] = uid
    session["email"] = email
    return jsonify({"ok": True, "email": email, "searchEnabled": bool(FDC_API_KEY)})


def do_me():
    uid = current_user_id()
    if not uid:
        return login_required_error()
    return jsonify({"ok": True, "email": session.get("email"), "searchEnabled": bool(FDC_API_KEY)})


# ─── Data actions (scoped to the logged-in user) ─────────────────────────────

FOOD_COLS = ("name", "portion", "cal", "fat", "carb", "sugar", "fiber", "protein")
LOG_COLS = ("cal", "fat", "carb", "sugar", "fiber", "protein", "water")


def action_read(uid):
    rows = get_db().execute(
        "SELECT food_id, name, portion, cal, fat, carb, sugar, fiber, protein "
        "FROM foods WHERE user_id = ? ORDER BY food_id",
        (uid,),
    ).fetchall()
    foods = []
    for r in rows:
        foods.append({
            "id": r["food_id"], "name": r["name"], "portion": r["portion"],
            "cal": r["cal"], "fat": r["fat"], "carb": r["carb"],
            "sugar": r["sugar"], "fiber": r["fiber"], "protein": r["protein"],
        })
    return jsonify({"ok": True, "foods": foods})


def action_write(uid, body):
    foods = body.get("foods", [])
    db = get_db()
    db.execute("DELETE FROM foods WHERE user_id = ?", (uid,))
    db.executemany(
        "INSERT INTO foods (user_id, food_id, name, portion, cal, fat, carb, sugar, fiber, protein) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(
            uid, int(f.get("id")), str(f.get("name", "")), str(f.get("portion", "")),
            _num(f.get("cal")), _num(f.get("fat")), _num(f.get("carb")),
            _num(f.get("sugar")), _num(f.get("fiber")), _num(f.get("protein")),
        ) for f in foods if f.get("id") is not None],
    )
    db.commit()
    return jsonify({"ok": True})


def action_loadplan(uid):
    row = get_db().execute(
        "SELECT blob FROM plan WHERE user_id = ?", (uid,)
    ).fetchone()
    return jsonify({"ok": True, "blob": row["blob"] if row else None})


def action_saveplan(uid, body):
    db = get_db()
    db.execute(
        "INSERT INTO plan (user_id, blob) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET blob = excluded.blob",
        (uid, body.get("blob")),
    )
    db.commit()
    return jsonify({"ok": True})


def action_readlog(uid):
    rows = get_db().execute(
        "SELECT date, cal, fat, carb, sugar, fiber, protein, water "
        "FROM log WHERE user_id = ?",
        (uid,),
    ).fetchall()
    log = {}
    for r in rows:
        log[r["date"]] = {c: r[c] for c in LOG_COLS}
    return jsonify({"ok": True, "log": log})


def action_log(uid, body):
    date_key = body.get("date")
    entry = body.get("entry")
    if date_key and entry:
        db = get_db()
        db.execute(
            "INSERT INTO log (user_id, date, cal, fat, carb, sugar, fiber, protein, water) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id, date) DO UPDATE SET "
            "cal=excluded.cal, fat=excluded.fat, carb=excluded.carb, sugar=excluded.sugar, "
            "fiber=excluded.fiber, protein=excluded.protein, water=excluded.water",
            (uid, str(date_key)) + tuple(_num(entry.get(c)) for c in LOG_COLS),
        )
        db.commit()
    return jsonify({"ok": True})


def action_loadsettings(uid):
    row = get_db().execute(
        "SELECT blob FROM settings WHERE user_id = ?", (uid,)
    ).fetchone()
    return jsonify({"ok": True, "blob": row["blob"] if row else None})


def action_savesettings(uid, body):
    db = get_db()
    db.execute(
        "INSERT INTO settings (user_id, blob) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET blob = excluded.blob",
        (uid, body.get("blob")),
    )
    db.commit()
    return jsonify({"ok": True})


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ─── USDA FoodData Central proxy ─────────────────────────────────────────────
# nutrientNumber -> our macro key. All FDC nutrient values here are per 100 g.
FDC_NUTRIENT_MAP = {
    "208": "cal", "203": "protein", "204": "fat",
    "205": "carb", "291": "fiber", "269": "sugar",
}
MACRO_KEYS = ("cal", "protein", "fat", "carb", "fiber", "sugar")


def _fdc_get(path, params, body=None):
    # Only the api_key goes in the query string. Anything with spaces or special
    # characters (e.g. the dataType "Survey (FNDDS)") goes in a JSON POST body —
    # putting it in the URL sporadically trips api.data.gov's edge with a 400.
    url = FDC_BASE + path + "?" + urllib.parse.urlencode(dict(params, api_key=FDC_API_KEY))
    headers = {"User-Agent": "VitalVortex"}
    data = None
    if body is not None:
        data = _json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    # api.data.gov sporadically fails transient requests, so retry those. Don't
    # retry deterministic client errors like 404 (some FDC foods have no detail).
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                return _json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise
            last = e
            time.sleep(0.3 * (attempt + 1))
        except urllib.error.URLError as e:
            last = e
            time.sleep(0.3 * (attempt + 1))
    raise last


def _macros_from_search_nutrients(nutrients):
    """foods/search shape: flat entries with nutrientNumber/value (per 100 g)."""
    out = {k: 0.0 for k in MACRO_KEYS}
    for n in nutrients or []:
        key = FDC_NUTRIENT_MAP.get(str(n.get("nutrientNumber")))
        if key:
            out[key] = _num(n.get("value"))
    return out


def _macros_from_detail_nutrients(nutrients):
    """food/{id} shape: nested nutrient{number}/amount (per 100 g)."""
    out = {k: 0.0 for k in MACRO_KEYS}
    for n in nutrients or []:
        nut = n.get("nutrient") or {}
        key = FDC_NUTRIENT_MAP.get(str(nut.get("number")))
        if key:
            out[key] = _num(n.get("amount"))
    return out


def action_foodsearch(query):
    if not FDC_API_KEY:
        return jsonify({"ok": False, "error": "food search is not configured"}), 503
    query = (query or "").strip()
    if not query:
        return jsonify({"ok": True, "results": []})
    try:
        data = _fdc_get("/foods/search", {}, body={
            "query": query,
            "pageSize": 25,
            "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded"],
        })
    except Exception:
        return jsonify({"ok": False, "error": "search failed"}), 502
    results = [{
        "fdcId": f.get("fdcId"),
        "name": f.get("description", ""),
        "brand": f.get("brandName") or f.get("brandOwner") or "",
        "dataType": f.get("dataType", ""),
        "per100": _macros_from_search_nutrients(f.get("foodNutrients")),
    } for f in data.get("foods", [])]
    # Stable sort: generic data types ahead of Branded, relevance order preserved.
    results.sort(key=lambda r: 1 if r["dataType"] == "Branded" else 0)
    return jsonify({"ok": True, "results": results})


def action_fooddetail(fdc_id):
    if not FDC_API_KEY:
        return jsonify({"ok": False, "error": "food search is not configured"}), 503
    if not fdc_id:
        return jsonify({"ok": False, "error": "missing fdcId"}), 400
    try:
        data = _fdc_get("/food/" + urllib.parse.quote(str(fdc_id)), {})
    except Exception:
        # Includes deterministic 404s (some FDC foods have no detail record). The
        # frontend falls back to the search result's per-100g macros, so this is
        # an expected "no detail" rather than a server fault.
        return jsonify({"ok": False, "error": "no detail available"})
    base = _macros_from_detail_nutrients(data.get("foodNutrients"))
    servings = [{"label": "100 g", "grams": 100.0}]
    default_index = 0
    if data.get("dataType") == "Branded":
        size = _num(data.get("servingSize"))
        unit = (data.get("servingSizeUnit") or "").lower()
        if size > 0 and unit in ("g", "ml"):
            house = (data.get("householdServingFullText") or "").strip()
            label = ("{} ".format(house) if house else "") + "({:g} {})".format(size, unit)
            servings.append({"label": label.strip(), "grams": size})
            default_index = len(servings) - 1
    else:
        seen = set()
        for p in data.get("foodPortions", []):
            grams = _num(p.get("gramWeight"))
            if grams <= 0:
                continue
            # Survey (FNDDS) foods carry the readable name in portionDescription
            # and a numeric code in modifier; SR/Foundation use modifier as text.
            desc = (p.get("portionDescription") or "").strip()
            if desc and desc.lower() != "quantity not specified":
                label = desc
            else:
                modifier = p.get("modifier") or ((p.get("measureUnit") or {}).get("name") or "")
                if modifier in ("undetermined", None) or str(modifier).isdigit():
                    modifier = ""
                amount = p.get("amount")
                amt = "{:g} ".format(_num(amount)) if amount else ""
                label = (amt + modifier).strip() or "serving"
            label = "{} ({:g} g)".format(label, grams)
            if label in seen:
                continue
            seen.add(label)
            servings.append({"label": label, "grams": grams})
            if len(servings) >= 9:  # cap the dropdown (100 g + up to 8 portions)
                break
        if len(servings) > 1:
            default_index = 1
    return jsonify({
        "ok": True,
        "name": data.get("description", ""),
        "base": base,
        "servings": servings,
        "defaultIndex": default_index,
    })


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # Static shell is served to everyone; the data API enforces auth and the
    # frontend shows its login screen when /api?action=me returns 401.
    return send_file(HTML_FILE)


@app.route("/api", methods=["GET", "POST", "OPTIONS"])
def api():
    if request.method == "OPTIONS":
        return ("", 204)

    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        action = body.get("action", "")
    else:
        body = {}
        action = request.args.get("action", "")

    # Public auth actions
    if action == "login":
        return do_login(body)
    if action == "logout":
        return do_logout()
    if action == "register":
        return do_register(body)
    if action == "me":
        return do_me()

    # Everything else requires a session
    uid = current_user_id()
    if not uid:
        return login_required_error()

    if action == "read":
        return action_read(uid)
    if action == "write":
        return action_write(uid, body)
    if action == "loadplan":
        return action_loadplan(uid)
    if action == "saveplan":
        return action_saveplan(uid, body)
    if action == "readlog":
        return action_readlog(uid)
    if action == "log":
        return action_log(uid, body)
    if action == "loadsettings":
        return action_loadsettings(uid)
    if action == "savesettings":
        return action_savesettings(uid, body)
    if action == "foodsearch":
        return action_foodsearch(request.args.get("q"))
    if action == "fooddetail":
        return action_fooddetail(request.args.get("fdcId"))

    return jsonify({"ok": False, "error": "unknown action: " + str(action)}), 400


# ─── CLI commands ─────────────────────────────────────────────────────────────

@app.cli.command("init-db")
def init_db_command():
    """Create tables if they don't exist."""
    init_db()
    click.echo(f"Initialized database at {DB_PATH}")


@app.cli.command("seed-user")
@click.argument("email")
@click.argument("password")
def seed_user_command(email, password):
    """Create a user (or reset their password)."""
    init_db()
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT INTO users (email, pw_hash) VALUES (?, ?) "
        "ON CONFLICT(email) DO UPDATE SET pw_hash = excluded.pw_hash",
        (email.strip(), generate_password_hash(password)),
    )
    con.commit()
    con.close()
    click.echo(f"Saved user {email}")


@app.cli.command("list-users")
def list_users_command():
    """List registered users."""
    init_db()
    con = sqlite3.connect(DB_PATH)
    for row in con.execute("SELECT id, email, created_at FROM users ORDER BY id"):
        click.echo(f"  #{row[0]}  {row[1]}  ({row[2]})")
    con.close()


# Ensure tables exist when imported by gunicorn (analog of Migrate() at startup).
init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=True)
