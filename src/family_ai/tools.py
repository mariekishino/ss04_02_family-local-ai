"""Safe Tool Foundation (Phase 3).

LLM の Tool proposal を直接実行しない境界。

    proposal → allowlist 確認 → schema validation → (認可) → 実行 → 監査

- 不明な Tool、余分な引数、型違い、長すぎる文字列を実行前に拒否する
- actor_user_id / household_id は引数に含めない (Gateway が context で渡す)
- 実行時間は計測して監査に残す (hard kill は inference server 側の
  timeout と組で扱う。Study Mode ではローカル SQLite のみなので計測のみ)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .context import RequestContext


class ToolError(Exception):
    """ユーザー/LLM に返してよい安全なエラーメッセージを持つ。

    内部事情 (SQL、スタックトレース等) を message に含めないこと。
    """


class ToolRejected(ToolError):
    """validation / policy 段階での拒否。実行前に発生する。"""


@dataclass(frozen=True)
class Param:
    """Tool 引数 1 個の schema。"""

    type: type
    required: bool = False
    max_length: int = 200          # 文字列の最大長
    description: str = ""
    is_datetime: bool = False      # True なら ISO 8601 として解釈可能か検証


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict[str, Param]
    handler: Callable[..., Any]     # handler(ctx, conn, **args)
    risk: str = "low"               # low / medium / high (ARCHITECTURE.md §9)
    requires_confirmation: bool = False
    max_result_items: int = 50
    idempotent: bool = False        # True なら handler が _idempotency_key を受ける


def _validate_value(tool: str, name: str, spec: Param, value: Any) -> Any:
    if not isinstance(value, spec.type):
        # JSON 由来なので int → float などの暗黙変換は行わない
        raise ToolRejected(
            f"Tool '{tool}' の引数 '{name}' の型が不正です"
        )
    if isinstance(value, str):
        if len(value) > spec.max_length:
            raise ToolRejected(
                f"Tool '{tool}' の引数 '{name}' が長すぎます"
                f" (最大 {spec.max_length} 文字)"
            )
        if spec.is_datetime:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                raise ToolRejected(
                    f"Tool '{tool}' の引数 '{name}' は"
                    " ISO 8601 形式の日時にしてください"
                ) from None
    return value


@dataclass
class ToolResult:
    tool: str
    data: Any
    duration_ms: int


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def validate(self, name: str, args: Any) -> dict[str, Any]:
        """allowlist と schema を検証し、正規化した引数を返す。

        失敗は ToolRejected。この関数を通らない引数で handler を
        呼んではならない。
        """
        spec = self._tools.get(name)
        if spec is None:
            raise ToolRejected(f"Tool '{name}' は存在しません")
        if not isinstance(args, dict):
            raise ToolRejected(f"Tool '{name}' の引数は object にしてください")

        unknown = set(args) - set(spec.params)
        if unknown:
            raise ToolRejected(
                f"Tool '{name}' に不明な引数があります: {sorted(unknown)}"
            )
        validated: dict[str, Any] = {}
        for pname, pspec in spec.params.items():
            if pname not in args or args[pname] is None:
                if pspec.required:
                    raise ToolRejected(
                        f"Tool '{name}' の引数 '{pname}' は必須です"
                    )
                continue
            validated[pname] = _validate_value(name, pname, pspec, args[pname])
        return validated

    def execute(
        self,
        ctx: RequestContext,
        conn,
        name: str,
        validated_args: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        """validate 済みの引数で Tool を実行する。

        idempotency_key は Gateway (Agent) が発行する。LLM の引数からは
        受け取らない (Server-owned Arguments, ARCHITECTURE.md §9)。
        """
        spec = self._tools.get(name)
        if spec is None:
            raise ToolRejected(f"Tool '{name}' は存在しません")
        start = time.monotonic()
        kwargs = dict(validated_args)
        if spec.idempotent and idempotency_key is not None:
            kwargs["_idempotency_key"] = idempotency_key
        data = spec.handler(ctx, conn, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)
        if isinstance(data, list) and len(data) > spec.max_result_items:
            data = data[: spec.max_result_items]
        return ToolResult(tool=name, data=data, duration_ms=duration_ms)
