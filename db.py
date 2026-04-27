import sqlite3
from contextlib import contextmanager
from typing import Any

from config import DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                slack_user_id TEXT PRIMARY KEY,
                display_name  TEXT,
                image_url     TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS current_checkins (
                slack_user_id TEXT PRIMARY KEY,
                work_date     TEXT NOT NULL,
                site          TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                source        TEXT NOT NULL,
                FOREIGN KEY (slack_user_id) REFERENCES users(slack_user_id)
            );

            CREATE TABLE IF NOT EXISTS checkin_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                slack_user_id TEXT NOT NULL,
                work_date     TEXT NOT NULL,
                site          TEXT NOT NULL,
                checked_in_at TEXT NOT NULL,
                source        TEXT NOT NULL,
                FOREIGN KEY (slack_user_id) REFERENCES users(slack_user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_history_work_date
                ON checkin_history(work_date);
            CREATE INDEX IF NOT EXISTS idx_history_user_date
                ON checkin_history(slack_user_id, work_date);

            CREATE TABLE IF NOT EXISTS app_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_schedule (
                slack_user_id  TEXT PRIMARY KEY,
                schedule_type  TEXT NOT NULL CHECK(schedule_type IN ('front_half', 'back_half', 'custom', 'always_expected', 'never_expected')),
                custom_pattern TEXT,
                is_active      INTEGER NOT NULL DEFAULT 1,
                notes          TEXT,
                updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (slack_user_id) REFERENCES users(slack_user_id)
            );

            CREATE TABLE IF NOT EXISTS schedule_overrides (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                slack_user_id TEXT NOT NULL,
                work_date     TEXT NOT NULL,
                status        TEXT NOT NULL CHECK(status IN ('expected', 'not_expected')),
                note          TEXT,
                UNIQUE(slack_user_id, work_date),
                FOREIGN KEY (slack_user_id) REFERENCES users(slack_user_id)
            );
            """
        )


def row_to_dict(row: sqlite3.Row | None):
    return dict(row) if row else None


def upsert_user(user_id: str, display_name: str, image_url: str | None):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO users (slack_user_id, display_name, image_url, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                display_name = excluded.display_name,
                image_url = excluded.image_url,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, display_name, image_url or ""),
        )


def set_schedule(user_id: str, schedule_type: str, custom_pattern: str | None = None, notes: str | None = None):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO user_schedule (slack_user_id, schedule_type, custom_pattern, notes, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                schedule_type = excluded.schedule_type,
                custom_pattern = excluded.custom_pattern,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP,
                is_active = 1
            """,
            (user_id, schedule_type, custom_pattern, notes),
        )


def set_schedule_override(user_id: str, work_date: str, status: str, note: str | None = None):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO schedule_overrides (slack_user_id, work_date, status, note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(slack_user_id, work_date) DO UPDATE SET
                status = excluded.status,
                note = excluded.note
            """,
            (user_id, work_date, status, note),
        )

def get_schedule_override(user_id: str, work_date: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT status FROM schedule_overrides
            WHERE slack_user_id = ? AND work_date = ?
            """,
            (user_id, work_date),
        ).fetchone()
    return row["status"] if row else None


def record_checkin(
    user_id: str,
    site: str,
    work_date: str,
    checked_in_at: str,
    source: str,
):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO current_checkins (slack_user_id, work_date, site, updated_at, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                work_date = excluded.work_date,
                site = excluded.site,
                updated_at = excluded.updated_at,
                source = excluded.source
            """,
            (user_id, work_date, site, checked_in_at, source),
        )
        conn.execute(
            """
            INSERT INTO checkin_history (slack_user_id, work_date, site, checked_in_at, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, work_date, site, checked_in_at, source),
        )


def clear_current_checkins_for_date(work_date: str):
    with get_db() as conn:
        conn.execute("DELETE FROM current_checkins WHERE work_date = ?", (work_date,))


def clear_all_current_checkins():
    with get_db() as conn:
        conn.execute("DELETE FROM current_checkins")


def get_current_checkin(user_id: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT work_date, site, updated_at, source
            FROM current_checkins
            WHERE slack_user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return row_to_dict(row)


def get_live_statuses(work_date: str):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT u.slack_user_id, u.display_name, u.image_url,
                   c.work_date, c.site, c.updated_at, c.source
            FROM current_checkins c
            JOIN users u ON u.slack_user_id = c.slack_user_id
            WHERE c.work_date = ?
            ORDER BY u.display_name COLLATE NOCASE
            """,
            (work_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_statuses_for_date(work_date: str):
    with get_db() as conn:
        rows = conn.execute(
            """
            WITH latest AS (
                SELECT slack_user_id, MAX(id) AS max_id
                FROM checkin_history
                WHERE work_date = ?
                GROUP BY slack_user_id
            )
            SELECT u.slack_user_id, u.display_name, u.image_url,
                   h.work_date, h.site, h.checked_in_at AS updated_at, h.source
            FROM latest l
            JOIN checkin_history h ON h.id = l.max_id
            JOIN users u ON u.slack_user_id = h.slack_user_id
            ORDER BY u.display_name COLLATE NOCASE
            """,
            (work_date,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_history(user_id: str, limit: int = 20):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT work_date, site, checked_in_at, source
            FROM checkin_history
            WHERE slack_user_id = ?
            ORDER BY checked_in_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_movements(work_date: str):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT u.slack_user_id, u.display_name, u.image_url,
                   h.site, h.checked_in_at, h.source
            FROM checkin_history h
            JOIN users u ON u.slack_user_id = h.slack_user_id
            WHERE h.work_date = ?
            ORDER BY u.display_name COLLATE NOCASE, h.checked_in_at ASC, h.id ASC
            """,
            (work_date,),
        ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        user_id = item["slack_user_id"]
        grouped.setdefault(
            user_id,
            {
                "slack_user_id": user_id,
                "display_name": item["display_name"],
                "image_url": item["image_url"],
                "events": [],
            },
        )
        grouped[user_id]["events"].append(
            {
                "site": item["site"],
                "checked_in_at": item["checked_in_at"],
                "source": item["source"],
            }
        )
    return sorted(grouped.values(), key=lambda x: x["display_name"].lower())


def get_state(key: str):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO app_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def clear_state(key: str):
    with get_db() as conn:
        conn.execute("DELETE FROM app_state WHERE key = ?", (key,))


def get_all_users():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT u.slack_user_id, u.display_name, u.image_url,
                   s.schedule_type, s.custom_pattern, s.notes, s.is_active
            FROM users u
            LEFT JOIN user_schedule s ON s.slack_user_id = u.slack_user_id
            ORDER BY u.display_name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_schedule_for_user(user_id: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT schedule_type, custom_pattern, notes, is_active
            FROM user_schedule
            WHERE slack_user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_dict(row)
