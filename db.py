"""SQLite persistence: users, settings, profiles, stats, rate limiting."""
import json
import os
import sqlite3
import time

import config
from core.settings import merge as merge_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    first_name    TEXT,
    username      TEXT,
    joined_at     REAL NOT NULL,
    last_seen     REAL NOT NULL,
    processed     INTEGER NOT NULL DEFAULT 0,
    is_banned     INTEGER NOT NULL DEFAULT 0,
    rate_count    INTEGER NOT NULL DEFAULT 0,
    rate_ts       REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    user_id  INTEGER PRIMARY KEY,
    json     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id   INTEGER NOT NULL,
    rowid_key INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    json      TEXT NOT NULL,
    created   REAL NOT NULL,
    UNIQUE (user_id, name)
);
"""


def _conn():
    conn = sqlite3.connect(config.DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def init_db():
    with _conn() as c:
        c.executescript(_SCHEMA)


# ------------------------------------------------------------- users

def ensure_user(user_id, first_name=None, username=None):
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO users (user_id, first_name, username, joined_at, last_seen)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET last_seen=?, first_name=?,"
            " username=?",
            (user_id, first_name, username, now, now, now, first_name, username))


def is_banned(user_id):
    with _conn() as c:
        row = c.execute("SELECT is_banned FROM users WHERE user_id=?",
                        (user_id,)).fetchone()
    return bool(row and row["is_banned"])


def set_banned(user_id, banned):
    ensure_user(user_id)
    with _conn() as c:
        c.execute("UPDATE users SET is_banned=? WHERE user_id=?",
                  (1 if banned else 0, user_id))


def bump_processed(user_id):
    ensure_user(user_id)
    with _conn() as c:
        c.execute("UPDATE users SET processed=processed+1 WHERE user_id=?",
                  (user_id,))


def user_stats(user_id):
    with _conn() as c:
        row = c.execute("SELECT processed, joined_at FROM users WHERE user_id=?",
                        (user_id,)).fetchone()
    if not row:
        return {"processed": 0, "joined": None}
    return {"processed": row["processed"], "joined": row["joined_at"]}


def global_stats():
    with _conn() as c:
        users = c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        active = c.execute(
            "SELECT COUNT(*) n FROM users WHERE processed>0").fetchone()["n"]
        total = c.execute("SELECT COALESCE(SUM(processed),0) n FROM users"
                          ).fetchone()["n"]
    return {"users": users, "active": active, "processed": total}


def all_user_ids():
    with _conn() as c:
        return [r["user_id"] for r in
                c.execute("SELECT user_id FROM users WHERE is_banned=0")]


# ------------------------------------------------------------- settings

def get_settings(user_id):
    with _conn() as c:
        row = c.execute("SELECT json FROM settings WHERE user_id=?",
                        (user_id,)).fetchone()
    return merge_settings(json.loads(row["json"]) if row else None)


def save_settings(user_id, settings):
    ensure_user(user_id)
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (user_id, json) VALUES (?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET json=?",
            (user_id, json.dumps(settings, ensure_ascii=False),
             json.dumps(settings, ensure_ascii=False)))


# ------------------------------------------------------------- profiles

def save_profile(user_id, name, settings):
    ensure_user(user_id)
    name = str(name).strip()[:40]
    if not name:
        return False
    payload = json.dumps(settings, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            "INSERT INTO profiles (user_id, name, json, created) VALUES (?,?,?,?)"
            " ON CONFLICT(user_id, name) DO UPDATE SET json=?",
            (user_id, name, payload, time.time(), payload))
    return True


def list_profiles(user_id):
    with _conn() as c:
        rows = c.execute(
            "SELECT rowid_key, name, created FROM profiles WHERE user_id=?"
            " ORDER BY created DESC", (user_id,)).fetchall()
    return [{"id": r["rowid_key"], "name": r["name"], "created": r["created"]}
            for r in rows]


def load_profile(user_id, name_or_id):
    with _conn() as c:
        try:
            rid = int(name_or_id)
            row = c.execute(
                "SELECT json FROM profiles WHERE user_id=? AND rowid_key=?",
                (user_id, rid)).fetchone()
        except (TypeError, ValueError):
            row = c.execute(
                "SELECT json FROM profiles WHERE user_id=? AND name=?",
                (user_id, str(name_or_id))).fetchone()
    return json.loads(row["json"]) if row else None


def delete_profile(user_id, name_or_id):
    with _conn() as c:
        try:
            rid = int(name_or_id)
            cur = c.execute("DELETE FROM profiles WHERE user_id=? AND rowid_key=?",
                            (user_id, rid))
        except (TypeError, ValueError):
            cur = c.execute("DELETE FROM profiles WHERE user_id=? AND name=?",
                            (user_id, str(name_or_id)))
        return cur.rowcount > 0


# ------------------------------------------------------------- rate limit

def rate_allow(user_id, limit=None, window=3600.0):
    """Sliding-hour token counter. True if the job is allowed."""
    limit = limit or config.RATE_JOBS_PER_HOUR
    now = time.time()
    ensure_user(user_id)
    with _conn() as c:
        row = c.execute("SELECT rate_count, rate_ts FROM users WHERE user_id=?",
                        (user_id,)).fetchone()
        count, ts = row["rate_count"], row["rate_ts"]
        if now - ts >= window:
            count = 0
            ts = now
        if count >= limit:
            return False
        c.execute("UPDATE users SET rate_count=?, rate_ts=? WHERE user_id=?",
                  (count + 1, ts, user_id))
    return True


# ------------------------------------------------------------- maintenance

def cleanup_tmp(max_age_secs=3600):
    now = time.time()
    if not os.path.isdir(config.TMP_DIR):
        return
    for name in os.listdir(config.TMP_DIR):
        path = os.path.join(config.TMP_DIR, name)
        try:
            if os.path.isdir(path):
                if now - os.path.getmtime(path) > max_age_secs:
                    import shutil
                    shutil.rmtree(path, ignore_errors=True)
            elif now - os.path.getmtime(path) > max_age_secs:
                os.remove(path)
        except OSError:
            pass
