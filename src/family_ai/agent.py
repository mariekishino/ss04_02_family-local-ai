"""Agent Gateway (Study Mode).

ARCHITECTURE.md §5 の canonical request flow を実装する。

    User text
      ↓ (STUDY MODE: 認証省略、固定 context)
    LLM (Tool proposal only)
      ↓ parse (Untrusted Input)
    Schema Validation (allowlist / 型 / 長さ)
      ↓
    Confirmation (書き込み系)
      ↓
    Tool Execution (idempotency key は Gateway が発行)
      ↓
    Result Filtering → LLM → Response
      ↓
    Audit (全段階)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime

from . import db
from .context import RequestContext
from .llm import (
    LLMClient,
    LLMUnavailable,
    ProposalParseError,
    Reply,
    ToolCall,
    parse_llm_output,
)
from .tools import ToolError, ToolRegistry, ToolRejected

MAX_TOOL_ROUNDS = 4
MAX_HISTORY_MESSAGES = 30

SAFE_LLM_DOWN = "AIモデルに接続できません。しばらくしてからもう一度試してください。"
SAFE_PARSE_FAIL = "応答をうまく解釈できませんでした。もう一度言い方を変えて試してください。"
SAFE_CANCELLED = "操作をキャンセルしました。"


def build_system_prompt(registry: ToolRegistry) -> str:
    tool_lines = []
    for spec in registry.specs():
        params = ", ".join(
            f"{name}: {p.type.__name__}"
            + ("(必須)" if p.required else "")
            + (f" — {p.description}" if p.description else "")
            for name, p in spec.params.items()
        ) or "引数なし"
        tool_lines.append(f"- {spec.name}: {spec.description} [{params}]")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    tools_text = "\n".join(tool_lines)
    return (
        "あなたは家族の予定を管理するアシスタントです。\n"
        f"現在日時: {now}\n\n"
        "必ず次のどちらかの JSON object を 1 個だけ出力してください。"
        "JSON 以外の文章を出力してはいけません。\n"
        '1. 返答: {"type": "reply", "text": "..."}\n'
        '2. Tool 呼び出し: {"type": "tool_call", "tool": "名前",'
        ' "arguments": {...}}\n\n'
        "使える Tool:\n"
        f"{tools_text}\n\n"
        "ルール:\n"
        "- 日時は ISO 8601 (例 2026-09-03T15:00:00) で指定する\n"
        "- 「来週」「明日」などは現在日時から具体的な日付に変換する\n"
        "- get_events の query はタイトルの文字列一致にしか使えない。"
        "「病院ある？」のようにカテゴリや種類で聞かれたら query を使わず"
        "期間だけで検索し、結果の中から自分で該当するもの"
        " (例: 歯医者・皮膚科は病院に該当) を判断して答える\n"
        "- 予定の変更・削除は、先に get_events で対象の id を確認する\n"
        "- ユーザーへの返答は日本語で簡潔にし、id は表示しない\n"
    )


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        conn: sqlite3.Connection,
        ctx: RequestContext,
        confirm: Callable[[str], bool],
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.conn = conn
        self.ctx = ctx
        self.confirm = confirm
        self.messages: list[dict[str, str]] = []

    # -------------------------------------------------------------- helpers

    def _audit(self, action: str, resource_id: str | None, result: str) -> None:
        db.audit(
            self.conn,
            household_id=self.ctx.household_id,
            actor_user_id=self.ctx.actor_user_id,
            action=action,
            resource_type="event",
            resource_id=resource_id,
            result=result,
        )

    def _chat_messages(self) -> list[dict[str, str]]:
        system = {"role": "system", "content": build_system_prompt(self.registry)}
        # 履歴は直近のみ渡す (context 長の管理はアプリケーション側の責務)
        return [system, *self.messages[-MAX_HISTORY_MESSAGES:]]

    def _describe(self, call: ToolCall, args: dict) -> str:
        arg_text = ", ".join(f"{k}={v!r}" for k, v in args.items()) or "なし"
        return f"{call.tool} ({arg_text})"

    # ---------------------------------------------------------------- main

    def handle(self, user_text: str) -> str:
        """ユーザー入力 1 件を処理して応答テキストを返す。"""
        self.messages.append({"role": "user", "content": user_text})
        feedback: str | None = None  # validation エラー等を LLM へ戻す

        for _round in range(MAX_TOOL_ROUNDS):
            if feedback is not None:
                self.messages.append({
                    "role": "user",
                    "content": json.dumps(
                        {"type": "tool_error", "message": feedback},
                        ensure_ascii=False,
                    ),
                })
                feedback = None
            try:
                raw = self.llm.chat(self._chat_messages())
            except LLMUnavailable:
                self._audit("llm.chat", None, "error")
                return SAFE_LLM_DOWN

            try:
                proposal = parse_llm_output(raw)
            except ProposalParseError:
                self._audit("llm.parse", None, "error")
                return SAFE_PARSE_FAIL

            if isinstance(proposal, Reply):
                self.messages.append({"role": "assistant", "content": raw})
                return proposal.text

            # ---- ToolCall
            self.messages.append({"role": "assistant", "content": raw})
            try:
                args = self.registry.validate(proposal.tool, proposal.arguments)
            except ToolRejected as e:
                self._audit(f"tool.{proposal.tool}", None, "denied")
                feedback = str(e)
                continue

            spec = self.registry.get(proposal.tool)
            if spec.requires_confirmation:
                if not self.confirm(self._describe(proposal, args)):
                    self._audit(f"tool.{proposal.tool}", None, "denied")
                    return SAFE_CANCELLED

            try:
                result = self.registry.execute(
                    self.ctx, self.conn, proposal.tool, args,
                    idempotency_key=str(uuid.uuid4()),
                )
            except ToolError as e:
                self._audit(f"tool.{proposal.tool}", None, "error")
                feedback = str(e)
                continue

            resource_id = None
            if isinstance(result.data, dict):
                resource_id = result.data.get("id") or result.data.get("event_id")
            self._audit(f"tool.{proposal.tool}", resource_id, "ok")
            self.messages.append({
                "role": "user",
                "content": json.dumps(
                    {"type": "tool_result", "tool": result.tool,
                     "data": result.data},
                    ensure_ascii=False,
                ),
            })

        self._audit("agent.rounds_exhausted", None, "error")
        return SAFE_PARSE_FAIL
