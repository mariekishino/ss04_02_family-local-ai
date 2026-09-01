"""Phase 4 exit criteria:

読み取り、追加、更新、論理削除、undo がテストデータで動作する。
加えて世帯分離 (household_id filter) と idempotency を確認する。
"""

import pytest

from family_ai.calendar_tools import (
    add_event,
    delete_event,
    get_events,
    undo_last,
    update_event,
)
from family_ai.tools import ToolError


def _add(ctx, conn, title="歯医者", start="2026-09-03T15:00:00", **kw):
    return add_event(ctx, conn, title=title, start_at=start, **kw)


def test_add_and_get(ctx, conn):
    added = _add(ctx, conn)
    events = get_events(ctx, conn, start="2026-09-01T00:00:00",
                        end="2026-09-30T00:00:00")
    assert [e["id"] for e in events] == [added["id"]]
    assert events[0]["title"] == "歯医者"
    # naive な日時は JST として正規化される
    assert added["start_at"] == "2026-09-03T15:00:00+09:00"


def test_get_with_query(ctx, conn):
    _add(ctx, conn, title="歯医者")
    _add(ctx, conn, title="授業参観", start="2026-09-05T10:00:00")
    events = get_events(ctx, conn, start="2026-09-01T00:00:00",
                        end="2026-09-30T00:00:00", query="歯医者")
    assert len(events) == 1
    assert events[0]["title"] == "歯医者"


def test_household_isolation(ctx, other_ctx, conn):
    added = _add(ctx, conn)
    # 別世帯からは検索でも見えない
    assert get_events(other_ctx, conn, start="2026-09-01T00:00:00",
                      end="2026-09-30T00:00:00") == []
    # ID を直接指定しても「見つからない」と同じ応答になる
    with pytest.raises(ToolError):
        delete_event(other_ctx, conn, event_id=added["id"])
    with pytest.raises(ToolError):
        update_event(other_ctx, conn, event_id=added["id"], title="乗っ取り")


def test_update(ctx, conn):
    added = _add(ctx, conn)
    updated = update_event(ctx, conn, event_id=added["id"],
                           start_at="2026-09-04T15:00:00")
    assert updated["start_at"] == "2026-09-04T15:00:00+09:00"
    assert updated["title"] == "歯医者"
    row = conn.execute("SELECT version FROM events WHERE id = ?",
                       (added["id"],)).fetchone()
    assert row["version"] == 2


def test_update_requires_some_field(ctx, conn):
    added = _add(ctx, conn)
    with pytest.raises(ToolError):
        update_event(ctx, conn, event_id=added["id"])


def test_end_before_start_rejected(ctx, conn):
    with pytest.raises(ToolError):
        _add(ctx, conn, end_at="2026-09-03T14:00:00")


def test_logical_delete(ctx, conn):
    added = _add(ctx, conn)
    delete_event(ctx, conn, event_id=added["id"])
    assert get_events(ctx, conn, start="2026-09-01T00:00:00",
                      end="2026-09-30T00:00:00") == []
    # 行自体は残っている (論理削除)
    row = conn.execute("SELECT deleted_at FROM events WHERE id = ?",
                       (added["id"],)).fetchone()
    assert row["deleted_at"] is not None


def test_undo_delete(ctx, conn):
    added = _add(ctx, conn)
    delete_event(ctx, conn, event_id=added["id"])
    result = undo_last(ctx, conn)
    assert result["undone"] == "delete"
    events = get_events(ctx, conn, start="2026-09-01T00:00:00",
                        end="2026-09-30T00:00:00")
    assert [e["id"] for e in events] == [added["id"]]


def test_undo_update_restores_previous(ctx, conn):
    added = _add(ctx, conn)
    update_event(ctx, conn, event_id=added["id"], title="皮膚科")
    undo_last(ctx, conn)
    row = conn.execute("SELECT title FROM events WHERE id = ?",
                       (added["id"],)).fetchone()
    assert row["title"] == "歯医者"


def test_undo_create_hides_event(ctx, conn):
    _add(ctx, conn)
    undo_last(ctx, conn)
    assert get_events(ctx, conn, start="2026-09-01T00:00:00",
                      end="2026-09-30T00:00:00") == []


def test_undo_nothing(ctx, conn):
    with pytest.raises(ToolError):
        undo_last(ctx, conn)


def test_undo_scoped_to_household(ctx, other_ctx, conn):
    added = _add(ctx, conn)
    delete_event(ctx, conn, event_id=added["id"])
    # 別世帯からは他世帯の変更を undo できない
    with pytest.raises(ToolError):
        undo_last(other_ctx, conn)


def test_idempotency(ctx, conn):
    key = "req-123"
    first = _add(ctx, conn, _idempotency_key=key)
    second = _add(ctx, conn, _idempotency_key=key)
    assert first == second
    count = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    assert count == 1
