"""Timing records and thinking request controls without a live Ollama server."""
import json
from io import BytesIO

import pytest

from family_ai.llm import OllamaClient, LLMUnavailable, MAX_OUTPUT_CHARS
from family_ai.agent import SAFE_PARSE_FAIL
from test_agent import make_agent, tool_call, reply


@pytest.mark.parametrize('think', [None, True, False])
def test_ollama_metrics(monkeypatch, think):
    requests = []

    def respond(req, timeout):
        requests.append(json.loads(req.data))
        return BytesIO(json.dumps({
            'message': {'content': 'answer', 'thinking': 'abc'},
            'eval_count': 12, 'eval_duration': 1000000000,
        }).encode())

    monkeypatch.setattr('urllib.request.urlopen', respond)
    client = OllamaClient('test', think=think)
    assert client.chat([]) == 'answer'
    if think is None:
        assert 'think' not in requests[0]
    else:
        assert requests[0]['think'] is think
    record = client.measurements[0]
    assert record['thinking_chars'] == 3
    assert record['eval_count'] == 12
    assert record['prompt_eval_cached_count'] is None
    assert record['client_seconds'] >= 0
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
