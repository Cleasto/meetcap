"""SQLite helpers for tracking action items extracted from meeting summaries."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".config" / "meetcap" / "actions.db"


def init_db() -> None:
    """Create the actions database and table if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS action_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                stem       TEXT NOT NULL,
                text       TEXT NOT NULL,
                item_hash  TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at  TEXT,
                UNIQUE(stem, item_hash)
            )
        """)
        conn.commit()


def sync_from_markdown(stem: str, body: str) -> int:
    """Parse `- [ ] ` checkboxes from markdown body and insert new ones.

    Returns the number of newly inserted items.
    """
    checkboxes = re.findall(r"^- \[ \] (.+)$", body, re.MULTILINE)
    inserted = 0
    with sqlite3.connect(DB_PATH) as conn:
        for raw in checkboxes:
            text = raw.strip()
            item_hash = hashlib.sha256(f"{stem}{text}".encode()).hexdigest()[:12]
            cursor = conn.execute(
                "INSERT OR IGNORE INTO action_items (stem, text, item_hash) VALUES (?, ?, ?)",
                (stem, text, item_hash),
            )
            inserted += cursor.rowcount
        conn.commit()
    return inserted


def close_item(item_id: int) -> None:
    """Mark an action item as closed with the current timestamp."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE action_items SET status = 'closed', closed_at = datetime('now') WHERE id = ?",
            (item_id,),
        )
        conn.commit()


def reopen_item(item_id: int) -> None:
    """Reopen a previously closed action item."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE action_items SET status = 'open', closed_at = NULL WHERE id = ?",
            (item_id,),
        )
        conn.commit()


def get_open_count() -> int:
    """Return the number of open action items across all meetings."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM action_items WHERE status = 'open'"
            ).fetchone()
            return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def get_items_for_stem(stem: str) -> list[dict]:
    """Return all action items for a single recording stem."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM action_items WHERE stem = ? ORDER BY created_at",
            (stem,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_items() -> list[dict]:
    """Return all open action items, newest meeting first."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM action_items WHERE status = 'open' ORDER BY stem DESC, created_at"
        ).fetchall()
        return [dict(r) for r in rows]
