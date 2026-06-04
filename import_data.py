#!/usr/bin/env python3
"""
One-time data import: vitalvortex_data.json -> SQLite, under one user account.

Use this to migrate your wife's existing history (foods, plan, saved days) out of
the Google Sheet and into the new SQLite database:

    1. On her machine, run the existing Deployment/sheet_to_json.py to produce a
       fresh vitalvortex_data.json from the Google Sheet.
    2. Run this script to load that JSON into a local vitalvortex.db, creating (or
       updating) her account in the process:

       python import_data.py vitalvortex_data.json her@email.com "her-password"

    3. Ship vitalvortex.db up to the VPS volume per DEPLOY.md.

Re-running for the same user replaces that user's foods/plan/log (it does not
touch other users). The expected JSON shape matches the old local server:
    { "foods": [ {id,name,portion,cal,fat,carb,sugar,fiber,protein}, ... ],
      "plan":  "<json string blob>" | null,
      "log":   { "YYYY-MM-DD": {cal,fat,carb,sugar,fiber,protein,water}, ... } }
"""

import argparse
import json
import os
import sqlite3
import sys

from werkzeug.security import generate_password_hash

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
LOG_COLS = ("cal", "fat", "carb", "sugar", "fiber", "protein", "water")


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    ap = argparse.ArgumentParser(description="Import vitalvortex_data.json into SQLite for one user.")
    ap.add_argument("json_file", help="path to vitalvortex_data.json")
    ap.add_argument("email", help="account email to import the data under")
    ap.add_argument("password", help="account password (set or reset)")
    ap.add_argument("--db", default="vitalvortex.db", help="SQLite path (default: vitalvortex.db)")
    args = ap.parse_args()

    if not os.path.exists(args.json_file):
        sys.exit(f"No such file: {args.json_file}")

    with open(args.json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    foods = data.get("foods", []) or []
    plan = data.get("plan")
    log = data.get("log", {}) or {}

    con = sqlite3.connect(args.db)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        con.executescript(f.read())

    # Upsert the user, then fetch their id.
    con.execute(
        "INSERT INTO users (email, pw_hash) VALUES (?, ?) "
        "ON CONFLICT(email) DO UPDATE SET pw_hash = excluded.pw_hash",
        (args.email.strip(), generate_password_hash(args.password)),
    )
    uid = con.execute("SELECT id FROM users WHERE email = ?", (args.email.strip(),)).fetchone()[0]

    # Replace this user's data only.
    con.execute("DELETE FROM foods WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM plan  WHERE user_id = ?", (uid,))
    con.execute("DELETE FROM log   WHERE user_id = ?", (uid,))

    con.executemany(
        "INSERT INTO foods (user_id, food_id, name, portion, cal, fat, carb, sugar, fiber, protein) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(
            uid, int(food["id"]), str(food.get("name", "")), str(food.get("portion", "")),
            num(food.get("cal")), num(food.get("fat")), num(food.get("carb")),
            num(food.get("sugar")), num(food.get("fiber")), num(food.get("protein")),
        ) for food in foods if food.get("id") is not None],
    )

    if plan is not None:
        # plan is stored as the JSON string blob the frontend produced.
        blob = plan if isinstance(plan, str) else json.dumps(plan)
        con.execute("INSERT INTO plan (user_id, blob) VALUES (?, ?)", (uid, blob))

    con.executemany(
        "INSERT INTO log (user_id, date, cal, fat, carb, sugar, fiber, protein, water) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [(uid, str(date)) + tuple(num(entry.get(c)) for c in LOG_COLS)
         for date, entry in log.items()],
    )

    con.commit()
    con.close()

    print(f"Imported into {args.db} for {args.email}:")
    print(f"  foods: {len(foods)}")
    print(f"  plan:  {'yes' if plan is not None else 'none'}")
    print(f"  log days: {len(log)}")


if __name__ == "__main__":
    main()
