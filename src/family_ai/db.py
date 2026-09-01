"""SQLite storage for Study Mode.

ARCHITECTURE.md §7 の data model のうち、Phase 4 で必要な
events / audit_events に加えて idempotency / changes (undo 用) を持つ。
すべての行に household_id を持たせ、query 時にも必ず household_id で
絞り込む (Dev Mode 以降の世帯分離をここから習慣にする)。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    household_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    created_by_user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Tokyo',
    visibility TEXT NOT NULL DEFAULT 'PRIVATE',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_household_start
    ON events (household_id, start_at);

-- 書き込み Tool の二重実行防止。key は Gateway が発行する (LLM に生成させない)。
CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- undo 用の変更履歴。prev_json は変更前の行 snapshot (create は NULL)。
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    op TEXT NOT NULL,               -- create / update / delete
    prev_json TEXT,
    created_at TEXT NOT NULL,
    undone_at TEXT
);

-- 監査ログ。機密本文 (タイトル等) は保存しない (ARCHITECTURE.md §7)。
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    result TEXT NOT NULL,           -- ok / denied / error
    created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def audit(
    conn: sqlite3.Connection,
    *,
    household_id: str,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    result: str,
) -> None:
    conn.execute(
        "INSERT INTO audit_events"
        " (household_id, actor_user_id, action, resource_type, resource_id,"
        "  result, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (household_id, actor_user_id, action, resource_type, resource_id,
         result, utcnow()),
    )
    conn.commit()
