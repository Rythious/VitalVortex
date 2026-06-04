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

import os
import secrets
import sqlite3

import click
from flask import Flask, g, request, jsonify, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("VV_DB_PATH", os.path.join(BASE_DIR, "vitalvortex.db"))
KEYS_DIR = os.environ.get("VV_KEYS_DIR", os.path.join(BASE_DIR, "keys"))
HTML_FILE = os.path.join(BASE_DIR, "Index.html")
SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")


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
        return jsonify({"ok": True, "email": email})
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
    return jsonify({"ok": True, "email": email})


def do_me():
    uid = current_user_id()
    if not uid:
        return login_required_error()
    return jsonify({"ok": True, "email": session.get("email")})


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
