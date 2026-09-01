"""Phase 3 exit criteria:

壊れた JSON、不正な引数、存在しない Tool を実行せず、安全に拒否できる。
"""

import pytest

from family_ai.llm import ProposalParseError, Reply, ToolCall, parse_llm_output
from family_ai.tools import ToolRejected


# ---------------------------------------------------------- proposal parse


def test_parse_reply():
    out = parse_llm_output('{"type": "reply", "text": "こんにちは"}')
    assert isinstance(out, Reply)
    assert out.text == "こんにちは"


def test_parse_tool_call():
    out = parse_llm_output(
        '{"type": "tool_call", "tool": "get_events", "arguments": {}}'
    )
    assert isinstance(out, ToolCall)
    assert out.tool == "get_events"


def test_parse_strips_json_fence():
    out = parse_llm_output('```json\n{"type": "reply", "text": "ok"}\n```')
    assert isinstance(out, Reply)


@pytest.mark.parametrize("bad", [
    "予定を登録しました",                        # JSON でない
    '{"type": "reply", "text": "x"',            # 壊れた JSON
    '[1, 2, 3]',                                # object でない
    '{"type": "shell", "cmd": "rm -rf /"}',     # 未知の type
    '{"type": "tool_call", "arguments": {}}',   # tool 名なし
    '{"type": "tool_call", "tool": "x", "arguments": "not-object"}',
])
def test_parse_rejects_malformed(bad):
    with pytest.raises(ProposalParseError):
        parse_llm_output(bad)


def test_parse_rejects_huge_output():
    with pytest.raises(ProposalParseError):
        parse_llm_output('{"type": "reply", "text": "' + "a" * 20000 + '"}')


# ------------------------------------------------------- schema validation


def test_unknown_tool_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate("run_shell", {})


def test_extra_argument_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate("get_events", {"query": "x", "household_id": "hh"})


def test_missing_required_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate("add_event", {"title": "歯医者"})  # start_at なし


def test_wrong_type_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate(
            "add_event", {"title": 123, "start_at": "2026-09-03T15:00:00"}
        )


def test_overlong_string_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate(
            "add_event",
            {"title": "a" * 500, "start_at": "2026-09-03T15:00:00"},
        )


def test_invalid_datetime_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate(
            "add_event", {"title": "歯医者", "start_at": "9月3日15時"}
        )


def test_non_dict_arguments_rejected(registry):
    with pytest.raises(ToolRejected):
        registry.validate("get_events", ["not", "a", "dict"])


def test_valid_arguments_pass(registry):
    args = registry.validate(
        "add_event", {"title": "歯医者", "start_at": "2026-09-03T15:00:00"}
    )
    assert args == {"title": "歯医者", "start_at": "2026-09-03T15:00:00"}
