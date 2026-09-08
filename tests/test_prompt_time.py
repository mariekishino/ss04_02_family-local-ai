"""System prompt time controls for cache experiments without a live model."""

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest

from family_ai import cli
from family_ai.agent import Agent
from family_ai.llm import FakeLLM
from test_agent import reply, tool_call


@pytest.mark.parametrize("fixed", [False, True])
def test_prompt_time_across_tool_rounds_and_turns(conn, ctx, registry, monkeypatch, fixed):
    start = datetime(2026, 9, 8, 16, tzinfo=timezone(timedelta(hours=9)))
    times = [start + timedelta(seconds=i) for i in range(3)]
    ticks = iter(times)

    class AdvancingDatetime(datetime):
        @classmethod
        def now(cls):
            if fixed:
                pytest.fail("Fixed prompt time must not read the current clock")
            return next(ticks)

    monkeypatch.setattr("family_ai.agent.datetime", AdvancingDatetime)
    llm = FakeLLM(responses=[tool_call("get_events"), reply("none"), reply("hello")])
    agent = Agent(llm, registry, conn, ctx, confirm=lambda _: True,
                  fixed_prompt_time=start if fixed else None)
    assert agent.handle("search") == "none"
    assert agent.handle("hello") == "hello"

    prompts = [messages[0]["content"] for messages in llm.calls]
    assert len(prompts) == 3
    for i, prompt in enumerate(prompts):
        expected = start if fixed else times[i].astimezone()
        assert f"現在日時: {expected.isoformat(timespec='seconds')}\n" in prompt
    assert (len(set(prompts)) == 1) is fixed


@pytest.mark.parametrize("value, expected", [
    (None, None),
    ("2026-09-08T16:00:00+09:00", "2026-09-08T16:00:00+09:00"),
    ("2026-09-08T07:00:00Z", "2026-09-08T07:00:00+00:00"),
])
def test_cli_prompt_time_reaches_request_and_metrics(conn, monkeypatch, tmp_path, value, expected):
    requests = []

    def respond(req, timeout):
        requests.append(json.loads(req.data))
        return BytesIO(json.dumps({"message": {"content": reply("hello")}}).encode())

    answers = iter(["hello", "exit"])
    monkeypatch.setattr("urllib.request.urlopen", respond)
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    monkeypatch.setattr(cli.db, "connect", lambda path: conn)
    metrics = tmp_path / "metrics.jsonl"
    argv = ["--metrics", str(metrics)]
    if value is not None:
        argv += ["--fixed-prompt-time", value]
    assert cli.main(argv) == 0
    record = json.loads(metrics.read_text(encoding="utf-8"))
    assert record["fixed_prompt_time"] == expected
    assert record["agent"]["outcome"] == "reply"
    if expected is not None:
        assert f"現在日時: {expected}\n" in requests[0]["messages"][0]["content"]


@pytest.mark.parametrize("value", [
    "not-a-date", "2026-09-08", "2026-09-08T16:00:00", "2026-09-08T16:00:00+25:00",
])
def test_invalid_prompt_time_fails_before_db_connect(monkeypatch, capsys, value):
    def unexpected_connect(path):
        pytest.fail("Invalid command-line arguments must not open a database")

    monkeypatch.setattr(cli.db, "connect", unexpected_connect)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--fixed-prompt-time", value])
    assert exc.value.code == 2
    assert "--fixed-prompt-time" in capsys.readouterr().err
