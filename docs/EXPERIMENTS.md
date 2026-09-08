# LLM / GPU Experiments

このファイルには、Local LLMとNVIDIA GPUの実験結果を記録する。

目的は「動いた」で終わらず、

> なぜそのVRAM使用量・速度・GPU負荷になったか

を説明できるようにすること。

---

# Environment

## Hardware

```text
GPU:
VRAM:
CPU:
RAM:
OS:
```

## Software

```text
NVIDIA Driver:
CUDA Runtime:
Ollama Version:
llama.cpp Version / Commit:
```

## Reproducibility Rules

- model ID、filename、hashを記録する
- 固定promptまたはfixtureを使用する
- sampler設定とseedを記録する
- warm-up後に複数回測定する
- 単発値だけでなくp50 / p95を記録する
- prompt処理とtoken生成を分けて測定する

---

# Experiment Template

## Experiment XX

### Question

何を確認する実験か。

### Configuration

```text
Model:
Model ID / File:
File Hash:
Parameters:
Quantization:
Context Length:
Batch:
GPU Offload:
Prompt Fixture:
Prompt Tokens:
Max Generated Tokens:
Temperature:
Top-p / Top-k:
Seed:
Warm-up Runs:
Measured Runs:
```

### Measurement

```text
Idle VRAM:
Loaded VRAM:
Peak VRAM:
Peak System RAM:
GPU Utilization:
Power:
Prompt Tokens/sec:
Generation Tokens/sec:
TTFT p50 / p95:
Total Latency p50 / p95:
Generated Tokens:
```

### Observation

-

### Interpretation

-

### Unknown

-

---

# Experiment 01 — Model Size vs VRAM

## Goal

パラメータ数とVRAM使用量の関係を見る。

| Model | Params | Quant | File Size | Peak VRAM | Prompt tok/s | Gen tok/s | TTFT |
|---|---:|---|---:|---:|---:|---:|---:|
| | | | | | | | |

---

# Experiment 02 — Quantization

## Goal

Q4 / Q6 / Q8の違いを見る。

| Quant | File Size | Peak VRAM | Prompt tok/s | Gen tok/s | Output Quality |
|---|---:|---:|---:|---:|---|
| Q4 | | | | | |
| Q6 | | | | | |
| Q8 | | | | | |

---

# Experiment 03 — Context Length

## Goal

Context Lengthを増やしたときのKV CacheとVRAM変化を見る。

| Context | Peak VRAM | Prompt tok/s | Gen tok/s | TTFT |
|---:|---:|---:|---:|---:|
| 2048 | | | | |
| 4096 | | | | |
| 8192 | | | | |
| 16384 | | | | |
| 32768 | | | | |

---

# Experiment 04 — Prefill vs Decode

## Question

長いPromptを処理する時と、1 tokenずつ生成する時ではGPUの使われ方がどう違うか。

### Notes

- Prefill:
- Decode:

---

# Experiment 05 — Concurrent Requests

## Goal

複数ユーザーが同じモデルを使ったときの挙動を見る。

| Concurrent Users | Peak VRAM | Aggregate tok/s | TTFT p50 | TTFT p95 | Total p95 |
|---:|---:|---:|---:|---:|---:|
| 1 | | | | | |
| 2 | | | | | |
| 4 | | | | | |

---

# Experiment 06 — Calendar Agent の応答遅延

## Goal / Status

2026-09-08 に検証計画を作成。同日に実機の予備測定を開始（結果は下記）。
自宅 Windows PC + Ollama + qwen3:8b で感じた予定登録・検索の遅延を、
モデルロード、入力処理、生成、Tool 実行、表示待ちに分けて調べる。

## 確認済みの事実

- ユーザー報告: 前回の実機確認では応答が遅く、`ollama ps` は `100% GPU` と表示された。
  所要時間の数値はまだ記録していない。
- `100% GPU` はモデル全体が GPU にロードされていることを示す。
  GPU 使用率や速度を示すものではなく、GPU 側の性能制約は除外できない。
- `src/family_ai/llm.py` は `stream: False` を指定し、応答全体を受信してから
  `message.content` だけを返す。`think` は未指定で、思考や性能指標は取り出していない。
- `src/family_ai/agent.py` は LLM 呼び出しごとに system prompt を作り直し、
  冒頭付近に秒単位の現在日時を挿入する。
- Tool を1回使って返答する場合、通常は Tool 提案と最終返答のために LLM を2回呼ぶ。

## 未検証の仮説

- 思考生成が、短い返答でも生成時間を増やしている。
  Ollama の現行公式資料では Qwen3 は思考対応で、対応モデルはデフォルト有効。
  実機のバージョンと `message.thinking` の有無を確認する。
- 現在日時の更新が共通の入力先頭部分を変え、プロンプトキャッシュの再利用を妨げている。
  「毎回キャッシュ全体が無効」とはまだ断定しない。
- 非ストリーミングが、表示開始までの待ち時間を長くしている。
  表示開始の改善と生成完了までの短縮は分けて評価する。
- 複数回の LLM 呼び出しで上記の待ち時間が積み重なっている。

## 再現条件

- 上記 Environment と Experiment Template に GPU、VRAM、OS、Ollama version、
  モデル ID・量子化、context length、sampler 設定・seed を記録する。
- コードの commit、入力文、system prompt、会話履歴、テスト用予定 DB を固定して保存する。
  各試行では同じ履歴・DB から開始し、予定登録によるデータ増加を混入させない。
- 日時とタイムゾーンを記録し、「今週」「来週」の期待範囲を事前に決める。
- 初回ロードを含む測定とウォームアップ後を分ける。各条件の warm-up 回数、
  測定回数、実行順を記録し、複数回の値と p50 / p95 を残す。
- 同時リクエストや他アプリの GPU 利用を揃え、条件を一度に複数変更しない。

## 検証順序

1. 現状のまま計測を追加し、LLM 呼び出しごとと Agent 全体の内訳を記録する。
2. 同じ入力・履歴で `think: true` と `think: false` を比較する。
3. 思考設定を揃え、実験用に日時を固定する条件と、現状どおり更新する条件を比較する。
   各条件の同一リクエスト反復も記録し、キャッシュの再利用を調べる。
   日時固定は実験用であり、実運用で日時を古いままにする修正ではない。
4. 他の条件を揃えて `stream: false / true` を比較し、最初の思考、最初の回答内容、
   生成完了、実際の画面表示の時刻を分けて測る。
   現行の Agent は JSON 全体の parse・validation 後に Tool を実行するため、
   ストリーム受信だけで Tool 実行やユーザー向け表示が早まるとは限らない。

## 測定項目

| 範囲 | 記録する項目 |
|---|---|
| Agent 全体 | 入力から返答までの実時間、LLM 呼び出し回数、Tool 実行時間、確認入力待ち時間 |
| LLM 呼び出しごと | クライアント実時間、`total_duration`、`load_duration`、`prompt_eval_duration`、`eval_duration` |
| トークン | `prompt_eval_count`、`eval_count`、生成 tok/s、対応版で返る場合は `prompt_eval_cached_count` |
| 思考 | `message.thinking` の有無・文字数（文字数をトークン数として扱わない） |
| ストリーミング | 最初の非空 thinking、最初の非空 content、受信完了、画面表示開始までの時間 |
| 実機 | 推論中の GPU 使用率・VRAM 使用量 |

Ollama の duration はナノ秒。生成 tok/s は `eval_count / eval_duration * 1e9`。
未提供の指標は 0 とせず「未提供」と記録する。確認の y/N を人間が入力する時間は
処理時間から分離する。サーバー時間とクライアント実時間の差をすべて通信遅延と断定しない。

## 品質確認

- JSON が正しく parse でき、未知 Tool や不正な引数を出さないか。
- 「今週」「来週」などを期待した日時範囲へ変換できるか。
- 「今週病院ある？」で期間内の「歯医者」を拾い、無関係な予定を除けるか。
- 登録前の確認と、登録・検索結果の正確さが維持されるか。

## 結果と判断

### 最初の実機測定手順（2026-09-08 計測実装）

CLI に `--think default|on|off` と `--metrics FILE` を追加した。
`default` は従来と同じく API に think を指定しない。
JSONL は入力1件につき1行追記し、予定本文・入力文・思考本文は保存しない。
入力・履歴・DB の再現用 fixture は別途管理する。

Windows のプロジェクトディレクトリで、仮想環境の Python を使用する。

```powershell
python -m pytest -q
ollama --version
ollama list
nvidia-smi

# まず従来設定で時間の内訳を確認
python -m family_ai.cli --model qwen3:8b --db study.db --think default --metrics latency-default.jsonl

# 比較時は各プロセスを exit で終了してから次を起動
python -m family_ai.cli --model qwen3:8b --db study.db --think on --metrics latency-on.jsonl
python -m family_ai.cli --model qwen3:8b --db study.db --think off --metrics latency-off.jsonl
```

最初は同じテスト予定が入った DB に対して「今週病院ある？」を使用し、
返答内容と JSONL の各呼び出しを確認する。検索だけなら DB の予定は変わらない。
各プロセスの最初の質問を比較すれば会話履歴を揃えられる。
同じセッションで質問を繰り返すと履歴が増えるので、同一条件の反復とは扱わない。
初回ロードありの結果を記録後、モデルがロードされた状態でも複数回測定する。

これは現状把握と think 比較のための計測。日時は現状どおり更新されるため、
入力処理の差も確認し、全体時間の差をすべて思考の影響と断定しない。
日時固定とストリーミング比較は後続の検証で実装する。

`agent.processing_seconds` は確認待ちを除く処理時間、`calls` は各 LLM 呼び出しの
性能指標。クライアントと Agent の時間は秒、Ollama の `*_duration` はナノ秒。
画面への表示時間・JSONL 保存時間は Agent の処理時間に含まない。

### 2026-09-08 予備測定（ユーザー提供の実機ログ）

Windows + qwen3:8b、stream=false、日時更新は従来どおり。
計測実装の配布 commit は c32aa46。実機の commit、GPU、Ollama version、
モデル ID・量子化、正確な warm-up 回数は未確認。各行は1試行で、p50 / p95 は未算出。
default は予定登録、ON/OFF は「9月10日の予定を教えて」に対する結果。

| ログ時刻 (UTC) / 条件 | 結果 | 処理秒（確認待ち除外） | LLM 回数 | 思考文字数合計 |
|---|---|---:|---:|---:|
| 06:13:16 / default 登録 | 成功 | 44.9445 | 2 | 4107 |
| 06:25:48 / ON 検索 | 成功、14時の美容院を返答 | 9.6014 | 2 | 1144 |
| 06:27:26 / OFF 検索 | 応答形式の解釈に失敗 | 5.3833 | 2 | 0 |
| 06:27:49 / OFF 同一会話で再質問 | 予定名を返答、時刻は省略 | 2.6958 | 1 | 0 |
| 06:38:16 / OFF 新規会話・診断追加後 | 2回目 invalid_json、出力39文字 | 7.4092 | 2 | 0 |

呼び出し別の内訳（時間は秒、tokens は生成トークン数）。

| 条件 / 呼出 | ロード | 入力処理 | 生成 | tokens | cached tokens | Ollama total | client |
|---|---:|---:|---:|---:|---:|---:|---:|
| default / 1 | 13.8688 | 11.8734 | 12.8185 | 951 | 0 | 38.5669 | 40.6294 |
| default / 2 | 0.0089 | 0.1803 | 1.9465 | 277 | 38 | 2.2583 | 4.3100 |
| ON / 1 | 2.4056 | 0.1192 | 1.6635 | 239 | 0 | 4.1925 | 6.2926 |
| ON / 2 | 0.0039 | 0.0733 | 1.1384 | 167 | 40 | 1.2523 | 3.3064 |
| OFF / 1 | 0.0096 | 0.2020 | 0.4482 | 66 | 38 | 0.7403 | 2.7682 |
| OFF / 2 | 0.0072 | 0.2171 | 0.2513 | 28 | 41 | 0.5252 | 2.6098 |
| OFF 再質問 / 1 | 0.0088 | 0.3545 | 0.2118 | 31 | 40 | 0.6461 | 2.6956 |
| OFF 診断追加後 / 1 | 2.3942 | 0.1222 | 0.4755 | 66 | 0 | 3.0031 | 5.0354 |
| OFF 診断追加後 / 2 | 0.0062 | 0.0724 | 0.1901 | 28 | 40 | 0.3067 | 2.3687 |

観測と解釈:

- default の約45秒にはモデルロード約13.88秒、入力処理約12.05秒が含まれる。
  全時間を思考生成に帰することはできない。
- ON/OFF 初回はどちらも2呼び出し。生成時間合計は 2.8019 → 0.6996秒、
  生成量は 406 → 94 tokens に減少。OFF の思考文字数は両呼び出しとも0。
  ただし OFF は失敗し、ロード・入力処理条件も異なるため、品質を維持した高速化とは結論しない。
- OFF 再質問は1呼び出しであり、直前の検索結果を履歴から利用した可能性がある。
  実装は返答の parse 失敗時にも取得済み Tool 結果を履歴に残す。
  再質問の2.70秒を、新規質問の ON 9.60秒と直接比較しない。
- client と Ollama total の差が1呼び出しごとに約2.03〜2.10秒ある。
  OFF 初回では合計約4.11秒。接続などの待ち時間を調べる候補だが、原因は未特定。
- cached tokens が一部非ゼロなので、毎回すべてのキャッシュが無効とはいえない。
  日時固定との比較は未実施。
- 診断追加後も OFF の新規質問で失敗が再発。`invalid_json` は2回目の39文字の出力を
  JSON として解析できなかったことを示す。本文未取得なので、通常文か壊れた JSON かは未確定。
  この回はロード合計2.40秒、入力処理0.19秒、生成0.67秒、client と Ollama total の差4.09秒。

### 次の測定：形式エラーの診断

旧ログの `calls[].status: ok` は Ollama の応答受信についての記録で、
アプリが応答を解釈できたことを意味しない。旧ログには失敗の具体的な種類がない。
追加実装で `agent.outcome` と `agent.parse_error` を記録する。
parse_error は `code`、LLM の呼び出し回 `round`（1始まり）、出力の文字数を持つ。
予定本文・LLM 応答本文は記録しない。

| code | 意味 |
|---|---|
| invalid_json | JSON として読み取れない |
| not_object | JSON object ではない |
| invalid_reply_text | reply の text がない、または文字列でない |
| invalid_tool_name | tool 名がない、または文字列でない |
| invalid_arguments | arguments が object でない |
| unknown_type | type が未指定、または reply / tool_call 以外 |
| output_too_long | 出力が文字数上限を超過 |

更新後、OFF を新規 CLI で起動し、同じ質問を1回だけ入力する。
成功・失敗をそのまま残し、次の試行は exit 後に起動し直す。
まず失敗の種類を特定し、その後ロード・入力条件を揃えた ON/OFF の複数回比較へ進む。

### 次の比較：プロンプトでの形式指定と API の出力形式指定

`invalid_json` の再発を受け、以下の任意オプションを追加した。実機検証はこれから。

- `--debug-output`: parse 失敗時の `message.content` を画面に表示（最大8000文字）。
  改行や制御文字は JSON 文字列としてエスケープ。本文は metrics や audit には保存しない。
  指定しない場合は従来どおり失敗本文を表示しない。
- `--structured-output`: Ollama API の `format` に Reply / ToolCall の JSON schema を渡す。
  既定では送信しない。モデル・think・温度・system prompt は変更しない。
  形式制約を指定した場合もアプリの parse、Tool 名・引数検証、書き込み確認は実行する。

手順（Windows、現在のブランチを更新後）。各起動で「9月10日の予定を教えて」を1回入力し、
成功・失敗にかかわらず exit。まず指定なしの失敗本文を観察し、次に形式制約ありを試す。
今回も予備測定であり、ロード時間・入力処理時間を分けて評価する。

```powershell
git pull --ff-only

# 形式指定なし: 失敗時の本文を観察
.\.venv\Scripts\python.exe -m family_ai.cli --model qwen3:8b --db study.db --think off --debug-output --metrics latency-off.jsonl

# exit 後、新しい会話で API の形式制約ありを比較
.\.venv\Scripts\python.exe -m family_ai.cli --model qwen3:8b --db study.db --think off --structured-output --debug-output --metrics latency-off-schema.jsonl
```

条件はログの `structured_output` で識別する。`done_reason` が API から返れば呼び出しごとに記録する。
形式が守られても日時や回答内容の正確さは別途確認する。ユーザーの Ollama version は未確認であり、
この schema の実機対応・成功率はまだ確かめていない。
[Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs) を参照。

## 参考資料

- [Ollama FAQ: GPU へのロード確認](https://docs.ollama.com/faq)
- [Ollama Thinking](https://docs.ollama.com/capabilities/thinking)
- [Ollama Usage: 性能指標](https://docs.ollama.com/api/usage)
- [Ollama Streaming](https://docs.ollama.com/api/streaming)

---

# Important Concepts

実験を通して以下を説明できるようにする。

- Model Weights
- VRAM
- Quantization
- Tensor
- CUDA
- KV Cache
- Context Window
- Prefill
- Decode
- Batch
- GPU Offload
- Tokens/sec
