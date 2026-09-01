"""Server-owned request context.

actor_user_id / household_id は必ずサーバー側で確定させる。
LLM や Client から送られた identity は信用しない (ARCHITECTURE.md §6)。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    """認証済み session からサーバーが生成する信頼できる context。

    STUDY MODE: 認証を実装していないため固定値を使う。
    Dev Mode では sessions テーブルの検証結果から生成すること。
    """

    actor_user_id: str
    household_id: str
    device_id: str = "study-terminal"
    session_id: str = "study-session"


def study_context() -> RequestContext:
    """STUDY MODE 専用の固定 context。Family Mode では使用禁止。"""
    return RequestContext(
        actor_user_id="study_user",
        household_id="study_household",
    )
