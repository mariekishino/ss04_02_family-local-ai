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
