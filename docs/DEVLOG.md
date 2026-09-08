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

---

# 2026-09-08 — 応答遅延の検証計画

## Context

ユーザーから前回の実機確認について補足: Ollama + qwen3:8b で登録・検索は
動作したが、応答が遅かった。`ollama ps` は `100% GPU` と表示されていた。
今回は機能追加より先に、遅延の内訳を検証するところから再開する。

## What I Did / Learned

- 現行コードの非ストリーミング受信、`think` 未指定、LLM 呼び出しごとの
  system prompt 内の現在日時更新を確認した。
- `ollama ps` の `100% GPU` はモデルの配置を示すため、GPU 性能が原因ではないとは断定しない。
- 思考生成、プロンプトキャッシュの再利用、表示待ち、複数回の LLM 呼び出しを
  切り分ける計画を [EXPERIMENTS.md](EXPERIMENTS.md#experiment-06--calendar-agent-の応答遅延) に記録した。
- キャッシュが毎回すべて無効になるか、思考が遅延の主因かは未検証。
  今回は文書の追記のみで、計測実装・実機測定はまだ行っていない。

## Next

1. LLM 呼び出しごとの性能指標と Agent 全体の時間を計測できるようにする。
2. 自宅 PC で環境・固定入力・履歴・テスト用 DB を記録し、現状と思考 ON/OFF を比較する。
3. 日時固定/更新、ストリーミング ON/OFF を順に比較し、結果から改善の優先順位を決める。
4. 速度と合わせて JSON・日時変換・「病院→歯医者」の検索品質を確認する。

---

# 2026-09-08 — 遅延計測と think 切り替えの実装

## What I Did

- マージ後の main から `feature/latency-measurement` を作成。
- CLI に `--think default|on|off` と `--metrics FILE` を追加。
- LLM 呼び出しごとのクライアント時間、Ollama の性能指標、思考文字数を記録。
  本文は計測ログに保存せず、未提供の指標は null とする。
- Agent 全体、LLM 呼び出し回数・時間、Tool 時間、確認待ち時間を分けて計測。
- think 指定の送信、指標欠損、接続失敗の計測、確認時間の分離と入力ごとの
  集計リセットをテスト。既存テストを含め45件通過。
- 実機用コマンドと比較時の履歴・日時の注意点を EXPERIMENTS.md に追記。

## Next

自宅 PC で現状の測定ログを取得し、think ON/OFF の生成時間・生成量・品質を比較する。
実 LLM の測定は未実施。日時固定とストリーミングはまだ実装していない。

---

# 2026-09-08 — 実機予備測定と応答形式の診断

## What I Learned

- ユーザー提供のログで、default の登録に44.94秒、ON の検索に9.60秒。
- OFF の検索は5.38秒で応答形式の解釈に失敗。同一会話での再質問は2.70秒で返答したが、
  LLM 呼び出し回数が2回から1回に変わるため、同一条件の成功例としては比較しない。
- OFF 初回も思考文字数は0で、生成時間は合計約0.70秒。ON は約2.80秒。
- Ollama total と client の間に各呼び出し約2秒の差が再現した。原因は未特定。

## What I Did

- 実測値と比較上の制約を EXPERIMENTS.md に記録。
- 計測へ Agent の outcome と parse エラー種別・発生回・出力文字数を追加。
  応答本文は保存せず、従来の形式検証とエラー時の停止動作を維持する。
- 検索後の parse エラー種別、本文をログに含めないこと、次の入力でのリセットを
  テストし、既存分を含む52件が通過。

## Next

更新した計測で OFF の新規質問を試し、形式エラーが再発する場合は種別を確認する。
追加の診断機能は実機未検証。接続などの約2秒の待ち時間の切り分けも残る。

---

# 2026-09-08 — invalid_json の再現と出力形式の比較準備

## What I Learned

診断追加後の OFF 新規質問でも7.41秒で失敗。2回目の39文字の出力で `invalid_json` が発生した。
思考は0文字、生成は2回合計約0.67秒。本文はまだ見ていないため、通常文か壊れた JSON かは未確定。

## What I Did

- 従来はプロンプトだけで JSON を要求していたため、API の `format` に JSON schema を渡す
  `--structured-output` を追加。既定のリクエスト内容は維持し、比較条件として選べるようにした。
- `--debug-output` で失敗した content を画面だけに表示し、次の試行で本文を観察できるようにした。
- 計測ログに形式制約の有無と API の `done_reason` を追加。
- 引数送信、診断表示の明示指定、本文の非保存、表示上限と入力ごとのリセットを確認。
  既存分を含む58件のテスト通過。実機結果と次の比較手順は EXPERIMENTS.md に記録。

## Next

新規会話で OFF の失敗本文を観察し、続いて OFF + API 形式制約を比較する。
追加オプションは実機未検証。形式の成功率と日時・予定内容の正確さを確認する。

---

# 2026-09-08 — 思考 OFF + 出力形式指定で検索成功

## What I Learned

- 失敗本文を確認すると、モデルは日時と予定名を通常の日本語で返しており、Reply JSON に
  包んでいなかった。今回の失敗は返答形式の問題と確認できた。
- 同じ質問を OFF + `--structured-output` で試し、予定名と14:00を含む返答に成功。
  `outcome: reply`、`parse_error: null`、2回とも思考0文字。処理時間5.3190秒。
- Ollama total は合計1.2284秒で、client 時間との差は合計4.0883秒。
  この1試行で形式指定の効果は観察できたが、成功率・他の質問の品質は未検証。

## What I Did / Next

実測値を EXPERIMENTS.md に追記。既存の `--ollama-url` を使い、次は接続先を
127.0.0.1 と明示したときに約2秒/呼び出しの差が変わるかを比較する。
この追記は文書のみ。アドレス選択・接続・プロキシ等のどれが原因かはまだ未特定。

---

# 2026-09-08 — 127.0.0.1 指定で呼び出しごとの待ち時間が縮小

## What I Learned

- 同じ OFF + schema で接続先を127.0.0.1と明示し、予定名と14:00を正しく返答。
  処理3.3404秒、LLM 2回、思考0文字、parse エラーなし。
- client と Ollama total の差は合計0.008333秒（各0.007310秒、0.001023秒）。
  前の条件で合計4.0883秒あった差が、この試行ではほぼ消えた。
- 今回はロード合計2.3949秒を含む。単純に差し引いた残りは約0.9455秒だが、
  ロード済み状態でその速さになることはまだ実測していない。

## What I Did / Next

実測値と比較上の制約を EXPERIMENTS.md に追記。文書のみの更新。
次は localhost を明示して再測定し、約2秒/呼び出しの差が戻るかを確認する。
接続先指定の影響は有力だが、IPv6・名前解決・プロキシ等のどこが原因かは未特定。

---

# 2026-09-08 — localhost に戻すと約2秒/呼び出しの差が再発

## What I Learned

- localhost を明示して同じ質問を再測定。返答成功、処理5.4526秒、思考0文字。
- モデルロード合計0.0163秒、Ollama total 合計1.2957秒に対し、client 合計5.4485秒。
  差が各2.0790秒・2.0738秒（合計4.1528秒）へ戻った。
- 127.0.0.1 指定の差約0.0083秒と対比し、接続先表記に伴う待ち時間の変化が再現した。
  内部原因の特定は未完了だが、以降の速度測定は127.0.0.1を明示して進める。

## What I Did / Next

実測値と次の測定手順を EXPERIMENTS.md に追記。文書のみの更新。
次は127.0.0.1、思考 OFF、形式指定ありで、ロード済みの処理時間と成功を複数回確認する。
現在日時固定によるキャッシュの比較、ストリーミングの比較は未実施。

---

# 2026-09-08 — ロード済み検索の基準値を約1.13秒と実測

## What I Learned

- IPv4 + 思考 OFF + API 形式指定で、新規 CLI から同じ質問を3回実行。
  ウォームアップ3.3015秒、続く2回は1.1723秒・1.0860秒（平均1.1291秒）。
- 3回とも予定名と14:00を正しく返答し、LLM 2回、思考0文字、parse エラーなし。
- 初回ロード合計2.3720秒に対し、続く2回は0.0044秒・0.0072秒。
  client と Ollama total の差も合計0.0076秒・0.0087秒で、約2秒/呼び出しの差は再発しなかった。
- 同じ質問の少数測定に限るが、ロード済みの約1.1秒を実測で確認できた。
  元の約45秒の登録とは条件が異なるため、単純な高速化倍率は算出しない。

## What I Did / Next

EXPERIMENTS.md に実測値と現在の到達点を追記。文書のみの更新。
次は同じ IPv4 + schema のロード済み条件で思考 ON を測り、OFFとの差を確認する。
その後に日時固定によるキャッシュ比較、ストリーミング比較へ進む。

---

# 2026-09-08 — 接続条件を揃えた思考 ON/OFF 比較

## What I Learned

- 同じ IPv4 + schema の思考 ON で3回測定。1回目を除いた平均は3.3033秒。
  OFF の後半2回の平均1.1291秒との差は2.1741秒（約65.8%短縮）。
- 生成時間は ON 平均2.7728秒、OFF 0.6639秒で、処理時間差の大半を占める。
  生成トークン数は396.5対97.5、思考文字数は1053対0。
- ON も3回とも形式成功し、提示された予定名・14:00は OFF と一致。
  この単純な質問での効果を確認できたが、複雑な質問の品質や一般的な成功率は未検証。

## What I Did / Next

EXPERIMENTS.md に実測値と比較結果を追記。
次は system prompt の日時固定/更新を切り替えて、キャッシュの再利用と入力処理時間を比較する。
そのための実験用オプション `--fixed-prompt-time` を追加し、通常の日時更新と比較できるようにした。
system prompt の日時だけを固定し、時刻 Tool と DB の時計は変更しない。
日時の固定・既定の時計追随、CLI のタイムゾーン検証と送信・計測への配線を確認し、全67件が通過。
日時固定オプションの実機測定はまだ行っていない。
ストリーミング比較は引き続き未実施。
