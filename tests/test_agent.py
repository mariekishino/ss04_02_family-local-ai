"""Agent Gateway の end-to-end テスト (FakeLLM 使用)。

README の Initial MVP シナリオを台本化して検証する。
"""

import json

import pytest

from family_ai.agent import SAFE_CANCELLED, SAFE_LLM_DOWN, SAFE_PARSE_FAIL, Agent
from family_ai.llm import FakeLLM


def make_agent(conn, ctx, registry, responses, confirm=lambda s: True):
    return Agent(
        llm=FakeLLM(responses=list(responses)),
        registry=registry,
        conn=conn,
        ctx=ctx,
        confirm=confirm,
    )


def tool_call(tool, **arguments):
    return json.dumps(
        {"type": "tool_call", "tool": tool, "arguments": arguments},
        ensure_ascii=False,
    )


def reply(text):
    return json.dumps({"type": "reply", "text": text}, ensure_ascii=False)


def test_add_event_flow(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, [
        tool_call("add_event", title="歯医者",
                  start_at="2026-09-03T15:00:00"),
        reply("9月3日15時に歯医者を登録しました。"),
    ])
    answer = agent.handle("9月3日15時に歯医者")
    assert "登録しました" in answer
    row = conn.execute("SELECT title, household_id FROM events").fetchone()
    assert row["title"] == "歯医者"
    assert row["household_id"] == ctx.household_id


def test_search_flow(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, [
        tool_call("add_event", title="歯医者",
                  start_at="2026-09-03T15:00:00"),
        reply("登録しました。"),
        tool_call("get_events", query="歯医者"),
        reply("9月3日15時に歯医者があります。"),
    ])
    agent.handle("9月3日15時に歯医者")
    answer = agent.handle("来週病院ある？")
    assert "歯医者" in answer
    # tool_result が LLM へ渡っていることを確認
    last_call = agent.llm.calls[-1]
    assert any("tool_result" in m["content"] for m in last_call)


def test_confirmation_declined(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, [
        tool_call("add_event", title="歯医者",
                  start_at="2026-09-03T15:00:00"),
    ], confirm=lambda s: False)
    answer = agent.handle("9月3日15時に歯医者")
    assert answer == SAFE_CANCELLED
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0


def test_read_only_tool_needs_no_confirmation(conn, ctx, registry):
    called = []
    agent = make_agent(conn, ctx, registry, [
        tool_call("get_events"),
        reply("予定はありません。"),
    ], confirm=lambda s: called.append(s) or False)
    answer = agent.handle("予定ある？")
    assert answer == "予定はありません。"
    assert called == []  # 読み取りは confirmation なしで実行される


def test_broken_json_is_safe(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, ["予定を登録しました"])
    assert agent.handle("9月3日15時に歯医者") == SAFE_PARSE_FAIL
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0


def test_unknown_tool_feeds_error_back(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, [
        tool_call("run_shell", cmd="rm -rf /"),
        reply("その操作はできません。"),
    ])
    answer = agent.handle("シェルを実行して")
    assert answer == "その操作はできません。"
    # 拒否が audit されている
    row = conn.execute(
        "SELECT result FROM audit_events WHERE action = 'tool.run_shell'"
    ).fetchone()
    assert row["result"] == "denied"


def test_llm_down_is_safe(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, [])  # 応答なし → LLMUnavailable
    assert agent.handle("こんにちは") == SAFE_LLM_DOWN


def test_rounds_are_limited(conn, ctx, registry):
    # 延々と不正な Tool を提案し続けても有限回で打ち切る
    agent = make_agent(conn, ctx, registry,
                       [tool_call("nope")] * 10)
    answer = agent.handle("テスト")
    assert answer == SAFE_PARSE_FAIL
    assert len(agent.llm.responses) >= 5  # 全部は消費されない


def test_audit_records_success(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, [
        tool_call("add_event", title="歯医者",
                  start_at="2026-09-03T15:00:00"),
        reply("登録しました。"),
    ])
    agent.handle("9月3日15時に歯医者")
    rows = conn.execute(
        "SELECT action, result FROM audit_events ORDER BY id"
    ).fetchall()
    assert ("tool.add_event", "ok") in [(r["action"], r["result"]) for r in rows]
    # 監査ログに予定タイトルなどの本文が含まれない
    for r in conn.execute("SELECT * FROM audit_events"):
        assert "歯医者" not in json.dumps(dict(r), ensure_ascii=False)
