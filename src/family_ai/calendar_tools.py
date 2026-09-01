"""Calendar tools (Phase 4).

get_events / add_event / update_event / delete_event / undo_last / get_current_time

- すべての query に household_id を含める (世帯分離の習慣づけ)
- delete は deleted_at による論理削除
- 書き込みは changes に変更前 snapshot を残し undo_last で戻せる
- add_event は idempotency key で二重実行を防ぐ
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any

from .context import RequestContext
from .db import utcnow
from .tools import Param, ToolError, ToolRegistry, ToolSpec

DEFAULT_TZ = "+09:00"  # Asia/Tokyo。naive な日時はこの offset として解釈する

EVENT_COLUMNS = (
    "id, household_id, owner_user_id, created_by_user_id, title,"
    " start_at, end_at, timezone, visibility, version,"
    " created_at, updated_at, deleted_at"
)


def _normalize_dt(value: str) -> str:
    """ISO 8601 文字列を offset 付きに正規化する (naive は JST とみなす)。"""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.isoformat(timespec="seconds") + DEFAULT_TZ
    return dt.isoformat(timespec="seconds")


def _event_view(row: sqlite3.Row) -> dict[str, Any]:
    """LLM へ返す最小限の形に filter する (Result Filtering)。"""
    return {
        "id": row["id"],
        "title": row["title"],
        "start_at": row["start_at"],
        "end_at": row["end_at"],
    }


def _fetch_event(
    conn: sqlite3.Connection, ctx: RequestContext, event_id: str
) -> sqlite3.Row:
    # household_id を必ず条件に含める。別世帯の ID を直接指定されても
    # 「見つからない」と同じ応答になる (存在を推測させない)。
    row = conn.execute(
        f"SELECT {EVENT_COLUMNS} FROM events"
        " WHERE id = ? AND household_id = ? AND deleted_at IS NULL",
        (event_id, ctx.household_id),
    ).fetchone()
    if row is None:
        raise ToolError("指定された予定が見つかりません")
    return row


def _record_change(
    conn: sqlite3.Connection,
    ctx: RequestContext,
    event_id: str,
    op: str,
    prev: sqlite3.Row | None,
) -> None:
    prev_json = json.dumps(dict(prev), ensure_ascii=False) if prev else None
    conn.execute(
        "INSERT INTO changes (household_id, event_id, op, prev_json, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (ctx.household_id, event_id, op, prev_json, utcnow()),
    )


# ---------------------------------------------------------------- handlers


def get_current_time(ctx: RequestContext, conn: sqlite3.Connection) -> dict:
    now = datetime.now().astimezone()
    return {"now": now.isoformat(timespec="seconds")}


def get_events(
    ctx: RequestContext,
    conn: sqlite3.Connection,
    *,
    start: str | None = None,
    end: str | None = None,
    query: str | None = None,
) -> list[dict]:
    start = _normalize_dt(start) if start else _normalize_dt(
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat(timespec="seconds")
    )
    end = _normalize_dt(end) if end else _normalize_dt(
        (datetime.fromisoformat(start) + timedelta(days=30))
        .isoformat(timespec="seconds")
    )
    sql = (
        f"SELECT {EVENT_COLUMNS} FROM events"
        " WHERE household_id = ? AND deleted_at IS NULL"
        " AND start_at >= ? AND start_at < ?"
    )
    params: list[Any] = [ctx.household_id, start, end]
    if query:
        sql += " AND title LIKE ?"
        params.append(f"%{query}%")
    sql += " ORDER BY start_at LIMIT 50"
    return [_event_view(r) for r in conn.execute(sql, params)]


def add_event(
    ctx: RequestContext,
    conn: sqlite3.Connection,
    *,
    title: str,
    start_at: str,
    end_at: str | None = None,
    _idempotency_key: str | None = None,
) -> dict:
    if _idempotency_key:
        hit = conn.execute(
            "SELECT result_json FROM idempotency WHERE key = ?",
            (_idempotency_key,),
        ).fetchone()
        if hit:
            return json.loads(hit["result_json"])

    event_id = str(uuid.uuid4())
    now = utcnow()
    start = _normalize_dt(start_at)
    end = _normalize_dt(end_at) if end_at else None
    if end is not None and end <= start:
        raise ToolError("終了時刻は開始時刻より後にしてください")
    with conn:
        conn.execute(
            "INSERT INTO events (id, household_id, owner_user_id,"
            " created_by_user_id, title, start_at, end_at, timezone,"
            " visibility, version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PRIVATE', 1, ?, ?)",
            (event_id, ctx.household_id, ctx.actor_user_id,
             ctx.actor_user_id, title, start, end, "Asia/Tokyo", now, now),
        )
        _record_change(conn, ctx, event_id, "create", None)
        result = {"id": event_id, "title": title, "start_at": start,
                  "end_at": end}
        if _idempotency_key:
            conn.execute(
                "INSERT INTO idempotency (key, tool, result_json, created_at)"
                " VALUES (?, 'add_event', ?, ?)",
                (_idempotency_key,
                 json.dumps(result, ensure_ascii=False), now),
            )
    return result


def update_event(
    ctx: RequestContext,
    conn: sqlite3.Connection,
    *,
    event_id: str,
    title: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
) -> dict:
    if title is None and start_at is None and end_at is None:
        raise ToolError("変更する項目がありません")
    prev = _fetch_event(conn, ctx, event_id)
    new_title = title if title is not None else prev["title"]
    new_start = _normalize_dt(start_at) if start_at else prev["start_at"]
    new_end = _normalize_dt(end_at) if end_at else prev["end_at"]
    if new_end is not None and new_end <= new_start:
        raise ToolError("終了時刻は開始時刻より後にしてください")
    with conn:
        _record_change(conn, ctx, event_id, "update", prev)
        conn.execute(
            "UPDATE events SET title = ?, start_at = ?, end_at = ?,"
            " version = version + 1, updated_at = ?"
            " WHERE id = ? AND household_id = ?",
            (new_title, new_start, new_end, utcnow(),
             event_id, ctx.household_id),
        )
    return {"id": event_id, "title": new_title, "start_at": new_start,
            "end_at": new_end}


def delete_event(
    ctx: RequestContext,
    conn: sqlite3.Connection,
    *,
    event_id: str,
) -> dict:
    prev = _fetch_event(conn, ctx, event_id)
    with conn:
        _record_change(conn, ctx, event_id, "delete", prev)
        conn.execute(
            "UPDATE events SET deleted_at = ?, version = version + 1,"
            " updated_at = ?"
            " WHERE id = ? AND household_id = ?",
            (utcnow(), utcnow(), event_id, ctx.household_id),
        )
    return {"id": event_id, "deleted": True, "title": prev["title"]}


def undo_last(ctx: RequestContext, conn: sqlite3.Connection) -> dict:
    change = conn.execute(
        "SELECT * FROM changes"
        " WHERE household_id = ? AND undone_at IS NULL"
        " ORDER BY id DESC LIMIT 1",
        (ctx.household_id,),
    ).fetchone()
    if change is None:
        raise ToolError("取り消せる操作がありません")
    op = change["op"]
    event_id = change["event_id"]
    with conn:
        if op == "create":
            # 作成の取り消し = 論理削除
            conn.execute(
                "UPDATE events SET deleted_at = ?, updated_at = ?"
                " WHERE id = ? AND household_id = ?",
                (utcnow(), utcnow(), event_id, ctx.household_id),
            )
        else:
            # update / delete の取り消し = 変更前 snapshot へ戻す
            prev = json.loads(change["prev_json"])
            conn.execute(
                "UPDATE events SET title = ?, start_at = ?, end_at = ?,"
                " deleted_at = ?, version = version + 1, updated_at = ?"
                " WHERE id = ? AND household_id = ?",
                (prev["title"], prev["start_at"], prev["end_at"],
                 prev["deleted_at"], utcnow(), event_id, ctx.household_id),
            )
        conn.execute(
            "UPDATE changes SET undone_at = ? WHERE id = ?",
            (utcnow(), change["id"]),
        )
    return {"undone": op, "event_id": event_id}


# ---------------------------------------------------------------- registry


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="get_current_time",
        description="現在の日時を返す",
        params={},
        handler=get_current_time,
    ))
    reg.register(ToolSpec(
        name="get_events",
        description="期間とキーワードで予定を検索する"
                    " (start/end は ISO 8601。省略時は今日から30日間)",
        params={
            "start": Param(str, is_datetime=True,
                           description="検索開始日時 (ISO 8601)"),
            "end": Param(str, is_datetime=True,
                         description="検索終了日時 (ISO 8601)"),
            "query": Param(str, max_length=100,
                           description="タイトルの部分一致キーワード"),
        },
        handler=get_events,
    ))
    reg.register(ToolSpec(
        name="add_event",
        description="予定を登録する",
        params={
            "title": Param(str, required=True, max_length=200,
                           description="予定のタイトル"),
            "start_at": Param(str, required=True, is_datetime=True,
                              description="開始日時 (ISO 8601)"),
            "end_at": Param(str, is_datetime=True,
                            description="終了日時 (ISO 8601)"),
        },
        handler=add_event,
        risk="medium",
        requires_confirmation=True,
        idempotent=True,
    ))
    reg.register(ToolSpec(
        name="update_event",
        description="既存の予定を変更する",
        params={
            "event_id": Param(str, required=True, max_length=64),
            "title": Param(str, max_length=200),
            "start_at": Param(str, is_datetime=True),
            "end_at": Param(str, is_datetime=True),
        },
        handler=update_event,
        risk="medium",
        requires_confirmation=True,
    ))
    reg.register(ToolSpec(
        name="delete_event",
        description="予定を削除する (論理削除。undo_last で戻せる)",
        params={
            "event_id": Param(str, required=True, max_length=64),
        },
        handler=delete_event,
        risk="medium",
        requires_confirmation=True,
    ))
    reg.register(ToolSpec(
        name="undo_last",
        description="直前の予定変更 (登録・変更・削除) を取り消す",
        params={},
        handler=undo_last,
        risk="medium",
        requires_confirmation=True,
    ))
    return reg
