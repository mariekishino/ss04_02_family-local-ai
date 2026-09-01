# Development Log

開発中に「何をやったか」だけでなく、

> 何を理解したか  
> 何が分からなかったか  
> 次に何を確かめるか

を残す。

---

# Entry Template

## YYYY-MM-DD

### Goal

-

### What I Did

-

### What I Learned

-

### Problem

-

### Hypothesis

-

### Next

-

---

# 2026-08-29

## Goal

Family Local AIプロジェクトの方向性を整理する。

## What I Did

以下の構想を整理した。

- 自宅PCでLocal LLMを動かす
- 家族専用のAI Agentとして使用
- 家族ごとにデータと権限を分離
- 機密情報を外部クラウドへ送らない
- 将来的には専用の小型デバイスから会話する

## What I Learned

家族ごとにLLMを複製する必要はない。

共有:

- Model
- GPU
- Inference Server

分離:

- User
- Session
- Memory
- Data
- Permission

また、LLMはデータ保管場所ではなく、

```text
Natural Language Interface
```

として扱う方が安全で設計しやすい。

## Next

Phase 0として現在のGPU / Ollama / Model環境を記録する。

---

# 2026-08-29 — Design Review

## Goal

初期構想を、学習用prototypeと家族の実運用の両面から精査する。

## What I Changed

- Study Mode、Dev Mode、Family Modeを分離
- 読み取り専用Toolから始めるようPhaseを再構成
- identity、session、household、authorizationをFamily MVPより前へ移動
- canonical request flowとTool risk levelを定義
- data modelへhousehold、device、session、auditを追加
- threat scenario、backup、restore、update要件を追加
- GPU実験へ再現性、TTFT、p50 / p95などの指標を追加

## What I Learned

LLMがToolを提案することと、そのToolを実行する権限があることは別である。device identityとuser identity、roleとvisibilityも分けて設計する必要がある。

## Next

Phase 0のBaselineを実機情報で埋め、固定promptによる最初の測定を行う。

---

# 2026-09-01 — Study Mode 実装 (Phase 3-4 + Phase 2 アプリ側)

## Goal

Safe Tool Foundation と Single-user Calendar Study をコードにする。

## What I Did

開発環境 (exe.dev VM) に GPU / Ollama がないため、GPU 実験 (Phase 0-1) は
自宅 PC に残し、コードで進められる部分を先に実装した。Python 3.12、
標準ライブラリのみ (テストは pytest)。

- `src/family_ai/llm.py` — Ollama クライアント (timeout / 切断 / HTTP エラーを
  `LLMUnavailable` に集約)、テスト用 `FakeLLM`、LLM 出力の厳格 parser
- `src/family_ai/tools.py` — Tool allowlist、schema validation
  (型・必須・文字列長・ISO 8601)、余分な引数の拒否、結果件数上限
- `src/family_ai/calendar_tools.py` — get/add/update/delete_event、
  undo_last、論理削除、idempotency key、household_id での分離
- `src/family_ai/agent.py` — canonical request flow (proposal → validation →
  confirmation → execution → result filtering → audit)、ラウンド上限
- `src/family_ai/cli.py` — Terminal REPL (`python -m family_ai.cli`)
- `tests/` — 40 tests。壊れた JSON / 未知 Tool / 型違いの拒否、
  CRUD + undo + idempotency、FakeLLM での MVP シナリオ end-to-end

## What I Learned

- conversation state を LLM server に持たせず messages リストとして
  アプリ側で管理すると、履歴の長さ制限や分離を自分で制御できる
- idempotency key や actor_user_id を「LLM の引数」ではなく
  「Gateway が渡す実行時パラメータ」として型レベルで分けると、
  Server-owned Arguments の原則がコードに現れる
- undo は変更前 snapshot (`changes.prev_json`) を残す方式が最も単純。
  create の undo は論理削除と同じ操作になる

## Problem

- Tool の実行時間は計測して監査に残すのみで、hard timeout は未実装
  (SQLite ローカル実行のみなので Study Mode では許容)
- 日時の自然言語解釈 (「来週」など) は LLM 任せ。小さいモデルで
  どの程度正確か未検証

## Next

- 自宅 PC で Phase 0 Baseline を記録し、Ollama + qwen3:8b などで
  `python -m family_ai.cli` を実際に動かす
- 小さいモデルが JSON プロトコルと日時変換をどこまで守れるか観察し、
  必要なら few-shot 例を system prompt に追加する

---

# 2026-09-01 — 実 LLM での動作確認 (Windows + Ollama + qwen3:8b)

## What I Did

Windows 側にレポジトリをクローンし、Ollama (qwen3:8b) で REPL を確認。
登録 → 確認 (y/N) → 検索の MVP シナリオが動作した。

構成メモ: WSL から Windows 側 Ollama への接続は `OLLAMA_HOST=0.0.0.0` と
IP 指定が必要になるため、Windows 側で完結させた (localhost で接続可)。
アプリ制御ポリシーで venv の exe ラッパーがブロックされるため、
`python -m pytest` のように `-m` 形式で実行する。

## What I Learned

- qwen3:8b は JSON プロトコル・日時変換 (「来週」→ 9/8-14) を正しく守れた
- 「今週病院ある？」に対し `query="病院"` で検索して「歯医者」を
  見落とした。query は文字列一致でしかなく、カテゴリの意味判断は
  SQL 側ではできない。「期間だけで検索し、絞り込みは LLM が結果を
  見て行う」よう system prompt にルールを追加した

## Next

- prompt 修正後に同じシナリオを再確認
- Phase 0 Baseline (GPU / VRAM / tok/s) を EXPERIMENTS.md に記録
