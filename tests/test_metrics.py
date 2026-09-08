"""Timing records and thinking request controls without a live Ollama server."""
import json
from io import BytesIO

import pytest

from family_ai.llm import OllamaClient, LLMUnavailable, MAX_OUTPUT_CHARS
from family_ai.agent import SAFE_PARSE_FAIL
from test_agent import make_agent, tool_call, reply


@pytest.mark.parametrize('think', [None, True, False])
@pytest.mark.parametrize('structured', [False, True])
def test_ollama_metrics(monkeypatch, think, structured):
    requests = []

    def respond(req, timeout):
        requests.append(json.loads(req.data))
        return BytesIO(json.dumps({
            'message': {'content': 'answer', 'thinking': 'abc'},
            'eval_count': 12, 'eval_duration': 1000000000,
        }).encode())

    monkeypatch.setattr('urllib.request.urlopen', respond)
    client = OllamaClient('test', think=think, structured_output=structured)
    assert client.chat([]) == 'answer'
    if think is None:
        assert 'think' not in requests[0]
    else:
        assert requests[0]['think'] is think
    if structured:
        schema = requests[0]['format']
        assert len(schema['anyOf']) == 2
        assert schema['anyOf'][0]['required'] == ['type', 'text']
        assert schema['anyOf'][1]['properties']['arguments']['additionalProperties'] is True
    else:
        assert 'format' not in requests[0]
    assert requests[0]['options'] == {'temperature': 0.2}
    record = client.measurements[0]
    assert record['thinking_chars'] == 3
    assert record['eval_count'] == 12
    assert record['prompt_eval_cached_count'] is None
    assert record['client_seconds'] >= 0
    assert record['structured_output'] is structured
    assert 'abc' not in json.dumps(record)


def test_failed_call_is_measured(monkeypatch):
    def fail(*args, **kwargs):
        raise TimeoutError('test')

    monkeypatch.setattr('urllib.request.urlopen', fail)
    client = OllamaClient('test')
    with pytest.raises(LLMUnavailable):
        client.chat([])
    assert client.measurements[0]['status'] == 'error'
    assert client.measurements[0]['client_seconds'] >= 0


def test_agent_metrics_separate_confirmation_and_reset(conn, ctx, registry, monkeypatch):
    ticks = iter(range(100))
    monkeypatch.setattr('family_ai.agent.perf_counter', lambda: next(ticks))
    agent = make_agent(conn, ctx, registry, [
        tool_call('add_event', title='test', start_at='2026-09-09T15:00:00'),
        reply('done'), reply('hello'),
    ])
    assert agent.handle('add') == 'done'
    m = agent.last_metrics
    assert m['llm_calls'] == 2
    assert m['llm_seconds'] == 2
    assert m['tool_seconds'] == 1
    assert m['confirmation_seconds'] == 1
    assert m['processing_seconds'] == m['total_seconds'] - 1
    agent.handle('hello')
    assert agent.last_metrics['llm_calls'] == 1
    assert agent.last_metrics['confirmation_seconds'] == 0
    assert agent.last_metrics['tool_seconds'] == 0


@pytest.mark.parametrize('raw, code', [
    ('appointment details', 'invalid_json'),
    ('[]', 'not_object'),
    ('{"type": "reply", "text": 123}', 'invalid_reply_text'),
    ('{"type": "tool_call"}', 'invalid_tool_name'),
    ('{"type": "tool_call", "tool": "get_events", "arguments": []}', 'invalid_arguments'),
    ('{"type": "appointment details"}', 'unknown_type'),
    ('x' * (MAX_OUTPUT_CHARS + 1), 'output_too_long'),
])
def test_parse_failure_after_search_is_measured_without_body(conn, ctx, registry, raw, code):
    agent = make_agent(conn, ctx, registry, [
        tool_call('get_events'), raw, reply('ok'),
    ])
    assert agent.handle('search') == SAFE_PARSE_FAIL
    assert agent.last_metrics['outcome'] == 'parse_error'
    assert agent.last_metrics['parse_error'] == {
        'code': code, 'round': 2, 'output_chars': len(raw),
    }
    assert 'appointment details' not in json.dumps(agent.last_metrics)
    assert any('tool_result' in message['content'] for message in agent.messages)
    agent.handle('retry')
    assert agent.last_metrics['outcome'] == 'reply'
    assert agent.last_metrics['parse_error'] is None


@pytest.mark.parametrize('debug', [False, True])
def test_cli_failed_output_is_opt_in_and_never_saved(conn, monkeypatch, tmp_path, capsys, debug):
    from family_ai import cli

    raw = 'appointment details\n\x1b[31m'
    replies = iter([raw, reply('ok')])

    def respond(req, timeout):
        return BytesIO(json.dumps({'message': {'content': next(replies)}}).encode())

    answers = iter(['search', 'retry', 'exit'])
    monkeypatch.setattr('urllib.request.urlopen', respond)
    monkeypatch.setattr('builtins.input', lambda *args: next(answers))
    monkeypatch.setattr(cli.db, 'connect', lambda path: conn)
    metrics = tmp_path / 'metrics.jsonl'
    assert cli.main(['--metrics', str(metrics)] + (['--debug-output'] if debug else [])) == 0
    display = capsys.readouterr().out
    assert display.count('[失敗出力・最大8000文字]') == int(debug)
    if debug:
        assert json.dumps(raw, ensure_ascii=False) in display
        assert '\x1b' not in display
    else:
        assert 'appointment details' not in display
    saved = metrics.read_text(encoding='utf-8')
    assert 'appointment details' not in saved
    records = [json.loads(line) for line in saved.splitlines()]
    assert records[0]['agent']['outcome'] == 'parse_error'
    assert records[1]['agent']['outcome'] == 'reply'
    assert records[1]['agent']['parse_error'] is None
    assert records[0]['structured_output'] is False


def test_failed_output_capture_is_bounded_and_reset(conn, ctx, registry):
    agent = make_agent(conn, ctx, registry, ['x' * (MAX_OUTPUT_CHARS + 1), reply('ok')])
    agent.capture_failed_output = True
    agent.handle('test')
    assert len(agent.last_failed_output) == MAX_OUTPUT_CHARS
    agent.handle('retry')
    assert agent.last_failed_output is None
