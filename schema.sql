-- Vital Vortex schema (SQLite)
-- Applied at startup with CREATE TABLE IF NOT EXISTS, so deploying a new image
-- creates the DB on first boot with no manual migration step.

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per food per user. food_id is the id the frontend assigns and uses to
-- reference foods inside the plan blob, so it must round-trip unchanged.
CREATE TABLE IF NOT EXISTS foods (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    food_id INTEGER NOT NULL,
    name    TEXT    NOT NULL,
    portion TEXT    NOT NULL DEFAULT '',
    cal     REAL    NOT NULL DEFAULT 0,
    fat     REAL    NOT NULL DEFAULT 0,
    carb    REAL    NOT NULL DEFAULT 0,
    sugar   REAL    NOT NULL DEFAULT 0,
    fiber   REAL    NOT NULL DEFAULT 0,
    protein REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, food_id)
);

-- Exactly one plan blob per user (the JSON string the frontend produces).
CREATE TABLE IF NOT EXISTS plan (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    blob    TEXT
);

-- One saved-day row per user per date (YYYY-MM-DD).
CREATE TABLE IF NOT EXISTS log (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date    TEXT    NOT NULL,
    cal     REAL    NOT NULL DEFAULT 0,
    fat     REAL    NOT NULL DEFAULT 0,
    carb    REAL    NOT NULL DEFAULT 0,
    sugar   REAL    NOT NULL DEFAULT 0,
    fiber   REAL    NOT NULL DEFAULT 0,
    protein REAL    NOT NULL DEFAULT 0,
    water   REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);
