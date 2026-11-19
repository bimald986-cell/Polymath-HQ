"""SQLite storage for Elevate Edge: accounts, server-side CVs and the AI counter.

One file, no service. The path comes from ``ELEVATE_DB_PATH`` (default
``elevate-edge/data/elevate.db``) and the database is created on first run.

Everything that decides access lives here so the route layer cannot invent a
second answer: ``plan`` is the entitlement, the counter is only ever incremented
by :func:`record_ai_call`, and every CV query carries ``user_id`` in its ``WHERE``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

#: The gate. ``free`` is 3 successful AI calls per period; ``pro`` is 200.
PLANS = {"free": 3, "pro": 200}
PERIOD_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    plan          TEXT NOT NULL DEFAULT 'free',
    ai_calls      INTEGER NOT NULL DEFAULT 0,
    period_start  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cvs (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT,
    content    TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cvs_user_id ON cvs(user_id);
"""


class DuplicateEmail(ValueError):
    """An account with that email already exists."""


class UnknownUser(LookupError):
    """No account with that email."""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _today() -> str:
    return date.today().isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the database, creating the directory if needed. Rows are dict-like."""
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # makes ON DELETE CASCADE real
    return conn


def init_db(path: str | Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- accounts ---
def create_user(conn: sqlite3.Connection, email: str, password_hash: str) -> int:
    email = normalize_email(email)
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, plan, ai_calls, period_start, created_at)"
            " VALUES (?, ?, 'free', 0, ?, ?)",
            (email, password_hash, _today(), _now()),
        )
    except sqlite3.IntegrityError as exc:
        raise DuplicateEmail(email) from exc
    conn.commit()
    return int(cur.lastrowid)


def get_user_by_email(conn: sqlite3.Connection, email: str):
    return conn.execute(
        "SELECT * FROM users WHERE email = ?", (normalize_email(email),)
    ).fetchone()


def get_user(conn: sqlite3.Connection, user_id: int):
    return conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
    conn.commit()


def grant_plan(conn: sqlite3.Connection, email: str, plan: str) -> bool:
    """Set a user's plan. The one seam a checkout webhook would call.

    Today the only caller is ``admin.py`` (``python admin.py grant <email> pro``);
    when a payment provider exists, its webhook calls this same function and
    nothing else in the gate changes. Returns False when the email is unknown.
    """
    if plan not in PLANS:
        raise ValueError(f"unknown plan {plan!r}; expected one of {sorted(PLANS)}")
    cur = conn.execute(
        "UPDATE users SET plan = ? WHERE email = ?", (plan, normalize_email(email))
    )
    conn.commit()
    return cur.rowcount > 0


# --------------------------------------------------------------------- CVs ---
def save_cv(conn: sqlite3.Connection, user_id: int, content, title: str | None = None) -> str:
    """Store the caller's own CV. Any ``id`` in the payload is ignored by design.

    The row is found by ``user_id`` only, so a caller who guesses another user's
    CV id cannot overwrite it -- there is no code path that writes by CV id.
    """
    blob = content if isinstance(content, str) else json.dumps(content)
    updated = _now()
    row = conn.execute(
        "SELECT id FROM cvs WHERE user_id = ? ORDER BY id LIMIT 1", (int(user_id),)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO cvs (user_id, title, content, updated_at) VALUES (?, ?, ?, ?)",
            (int(user_id), title, blob, updated),
        )
    else:
        conn.execute(
            "UPDATE cvs SET title = ?, content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (title, blob, updated, row["id"], int(user_id)),
        )
    conn.commit()
    return updated


def get_cv(conn: sqlite3.Connection, user_id: int):
    """The caller's own CV, or None. ``user_id`` is in the WHERE, not the template."""
    row = conn.execute(
        "SELECT id, title, content, updated_at FROM cvs WHERE user_id = ? ORDER BY id LIMIT 1",
        (int(user_id),),
    ).fetchone()
    if row is None:
        return None
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError):
        content = row["content"]
    return {"title": row["title"], "content": content, "updated_at": row["updated_at"]}


# -------------------------------------------------------------------- gate ---
def _roll_period(conn: sqlite3.Connection, user) -> sqlite3.Row:
    """Reset the counter when the 30-day window has elapsed."""
    try:
        started = date.fromisoformat(user["period_start"])
    except (TypeError, ValueError):
        started = date.today()
    if date.today() >= started + timedelta(days=PERIOD_DAYS):
        conn.execute(
            "UPDATE users SET ai_calls = 0, period_start = ? WHERE id = ?",
            (_today(), user["id"]),
        )
        conn.commit()
        return get_user(conn, user["id"])
    return user


def ai_usage(conn: sqlite3.Connection, user_id: int) -> dict:
    user = get_user(conn, user_id)
    if user is None:
        raise UnknownUser(user_id)
    user = _roll_period(conn, user)
    plan = user["plan"] if user["plan"] in PLANS else "free"
    limit = PLANS[plan]
    used = int(user["ai_calls"])
    return {
        "plan": plan,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "period_start": user["period_start"],
    }


def record_ai_call(conn: sqlite3.Connection, user_id: int) -> None:
    """Count one *successful* call. Never called when the provider fails."""
    conn.execute("UPDATE users SET ai_calls = ai_calls + 1 WHERE id = ?", (int(user_id),))
    conn.commit()
