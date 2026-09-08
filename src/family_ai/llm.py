"""LLM client layer (Phase 2 のアプリケーション側).

- OllamaClient: Ollama の /api/chat を timeout 付きで呼ぶ。
  接続不能・timeout・HTTP エラーは LLMUnavailable にまとめ、
  呼び出し元 (Agent) が安全に失敗できるようにする。
- FakeLLM: テスト用。台本どおりに応答を返す。
- parse_llm_output: LLM の出力を Untrusted Input として厳格に parse する。
  壊れた JSON・未知の形式は ProposalParseError (実行はしない)。

conversation state は LLM server に持たせず、アプリケーション側
(Agent の messages リスト) で管理する。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from time import perf_counter
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMUnavailable(Exception):
    """LLM server と通信できない。呼び出し元は安全に失敗すること。"""


class ProposalParseError(Exception):
    """LLM 出力を提案として解釈できない。実行してはならない。"""

    def __init__(self, message: str, *, code: str = "invalid_output") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Reply:
    text: str


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any]


MAX_OUTPUT_CHARS = 8000
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

# The model selects a proposal; ToolRegistry still validates tool names and arguments.
OUTPUT_SCHEMA = {
    "anyOf": [
        {
            "type": "object",
            "properties": {"type": {"const": "reply"}, "text": {"type": "string"}},
            "required": ["type", "text"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "type": {"const": "tool_call"},
                "tool": {"type": "string"},
                "arguments": {"type": "object", "additionalProperties": True},
            },
            "required": ["type", "tool", "arguments"],
            "additionalProperties": False,
        },
    ],
}


def parse_llm_output(text: str) -> Reply | ToolCall:
    """LLM の生出力を Reply か ToolCall に変換する。

    期待する形式 (JSON object 1 個):
      {"type": "reply", "text": "..."}
      {"type": "tool_call", "tool": "...", "arguments": {...}}

    モデルが ```json フェンスで包むことがあるため、それだけは剥がす。
    それ以外の逸脱はすべて ProposalParseError。
    """
    if len(text) > MAX_OUTPUT_CHARS:
        raise ProposalParseError("LLM 出力が長すぎます", code="output_too_long")
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1)
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ProposalParseError(f"JSON として解釈できません: {e}",
                                 code="invalid_json") from None
    if not isinstance(obj, dict):
        raise ProposalParseError("JSON object ではありません", code="not_object")

    kind = obj.get("type")
    if kind == "reply":
        if not isinstance(obj.get("text"), str):
            raise ProposalParseError("reply に text がありません", code="invalid_reply_text")
        return Reply(text=obj["text"])
    if kind == "tool_call":
        if not isinstance(obj.get("tool"), str):
            raise ProposalParseError("tool_call に tool 名がありません", code="invalid_tool_name")
        args = obj.get("arguments", {})
        if not isinstance(args, dict):
            raise ProposalParseError("arguments は object にしてください", code="invalid_arguments")
        return ToolCall(tool=obj["tool"], arguments=args)
    raise ProposalParseError(f"不明な type です: {kind!r}", code="unknown_type")


class LLMClient(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> str:
        """messages (role/content) を渡し、assistant の生テキストを返す。"""
        ...


class OllamaClient:
    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_sec: float = 120.0,
        think: bool | None = None,
        structured_output: bool = False,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.think = think
        self.structured_output = structured_output
        self.measurements: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        request_body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if self.think is not None:
            request_body["think"] = self.think
        if self.structured_output:
            request_body["format"] = OUTPUT_SCHEMA
        payload = json.dumps(request_body).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        started = perf_counter()
        measurement: dict[str, Any] = {"status": "error", "think": self.think,
                                       "structured_output": self.structured_output}
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                body = json.loads(resp.read().decode())
                for key in ("total_duration", "load_duration", "prompt_eval_duration",
                            "eval_duration", "prompt_eval_count", "eval_count",
                            "prompt_eval_cached_count", "done_reason"):
                    measurement[key] = body.get(key)
                thinking = body.get("message", {}).get("thinking", "")
                measurement["thinking_chars"] = len(thinking or "")
                measurement["status"] = "ok"
        except urllib.error.HTTPError as e:
            raise LLMUnavailable(f"LLM server error: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMUnavailable(f"LLM server unreachable: {e}") from e
        finally:
            measurement["client_seconds"] = perf_counter() - started
            self.measurements.append(measurement)
        try:
            return body["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LLMUnavailable("unexpected response shape") from e


@dataclass
class FakeLLM:
    """テスト用: 呼ばれるたびに scripted responses を順に返す。"""

    responses: list[str]
    calls: list[list[dict[str, str]]] = field(default_factory=list)

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append([dict(m) for m in messages])
        if not self.responses:
            raise LLMUnavailable("no scripted response left")
        return self.responses.pop(0)
