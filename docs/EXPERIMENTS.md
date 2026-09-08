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

2026-09-08 に検証計画を作成。実測は未実施。
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

## 結果と判断（実測後に記入）

| 条件 / 試行数 | 全体時間 p50 / p95 | LLM 回数 | 入力処理時間 | 生成時間 / tokens | 表示開始時間 | 品質 |
|---|---|---|---|---|---|---|
| 未測定 | — | — | — | — | — | — |

呼び出し別の測定値も残し、観測事実、解釈、残る不明点を分けて追記する。
まず思考 ON/OFF の結果を見て、キャッシュ改善と表示改善の優先順位を判断する。

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
