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
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMUnavailable(Exception):
    """LLM server と通信できない。呼び出し元は安全に失敗すること。"""


class ProposalParseError(Exception):
    """LLM 出力を提案として解釈できない。実行してはならない。"""


@dataclass(frozen=True)
class Reply:
    text: str


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any]


MAX_OUTPUT_CHARS = 8000
_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_llm_output(text: str) -> Reply | ToolCall:
    """LLM の生出力を Reply か ToolCall に変換する。

    期待する形式 (JSON object 1 個):
      {"type": "reply", "text": "..."}
      {"type": "tool_call", "tool": "...", "arguments": {...}}

    モデルが ```json フェンスで包むことがあるため、それだけは剥がす。
    それ以外の逸脱はすべて ProposalParseError。
    """
    if len(text) > MAX_OUTPUT_CHARS:
        raise ProposalParseError("LLM 出力が長すぎます")
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    if m:
        stripped = m.group(1)
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ProposalParseError(f"JSON として解釈できません: {e}") from None
    if not isinstance(obj, dict):
        raise ProposalParseError("JSON object ではありません")

    kind = obj.get("type")
    if kind == "reply":
        if not isinstance(obj.get("text"), str):
            raise ProposalParseError("reply に text がありません")
        return Reply(text=obj["text"])
    if kind == "tool_call":
        if not isinstance(obj.get("tool"), str):
            raise ProposalParseError("tool_call に tool 名がありません")
        args = obj.get("arguments", {})
        if not isinstance(args, dict):
            raise ProposalParseError("arguments は object にしてください")
        return ToolCall(tool=obj["tool"], arguments=args)
    raise ProposalParseError(f"不明な type です: {kind!r}")


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
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise LLMUnavailable(f"LLM server error: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMUnavailable(f"LLM server unreachable: {e}") from e
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
