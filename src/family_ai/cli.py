"""Study Mode terminal REPL.

    python -m family_ai.cli --model qwen3:8b [--db study.db]

localhost の Ollama に接続する。書き込み系 Tool は実行前に y/n で確認する。
STUDY MODE: 単一ユーザー・テストデータ限定。実データを入れない。
"""

from __future__ import annotations

import argparse
import os
import sys
import json
from datetime import datetime, timezone

from . import db
from .agent import Agent
from .calendar_tools import build_registry
from .context import study_context
from .llm import OllamaClient


def confirm_tty(summary: str) -> bool:
    answer = input(f"実行しますか? {summary} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Family Local AI (Study Mode)")
    parser.add_argument(
        "--model",
        default=os.environ.get("FAMILY_AI_MODEL", "qwen3:8b"),
        help="Ollama model name (env: FAMILY_AI_MODEL)",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        help="Ollama base URL (env: OLLAMA_URL)",
    )
    parser.add_argument("--db", default="study.db", help="SQLite file path")
    parser.add_argument("--think", choices=("default", "on", "off"), default="default")
    parser.add_argument("--metrics", help="Append timing records to this JSONL file")
    args = parser.parse_args(argv)

    conn = db.connect(args.db)
    llm = OllamaClient(model=args.model, base_url=args.ollama_url,
                       think={"default": None, "on": True, "off": False}[args.think])
    agent = Agent(
        llm=llm,
        registry=build_registry(),
        conn=conn,
        ctx=study_context(),
        confirm=confirm_tty,
    )

    print(f"Family Local AI — Study Mode (model={args.model}, db={args.db})")
    print("終了: Ctrl-D または exit")
    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("exit", "quit"):
            break
        llm.measurements.clear()
        print(agent.handle(text))
        if args.metrics:
            record = {"timestamp": datetime.now(timezone.utc).isoformat(),
                      "model": args.model, "think": args.think, "stream": False,
                      "agent": agent.last_metrics, "calls": llm.measurements}
            with open(args.metrics, "a", encoding="utf-8") as output:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
            m = agent.last_metrics
            print(f"[計測] 処理 {m['processing_seconds']:.2f}s / "
                  f"LLM {m['llm_calls']}回 {m['llm_seconds']:.2f}s / "
                  f"Tool {m['tool_seconds']:.3f}s / "
                  f"確認待ち {m['confirmation_seconds']:.2f}s")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
