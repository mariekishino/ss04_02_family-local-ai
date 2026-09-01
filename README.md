# Family Local AI

自宅PC上のローカルLLMを使って、家族専用のAIエージェント基盤を作るプロジェクト。

このプロジェクトの主目的は、単に「家族向けAIサービスを完成させること」ではなく、実装を通して以下を理解すること。

- Local LLM の推論の仕組み
- NVIDIA GPU / CUDA / VRAM の使われ方
- 量子化とモデルサイズの関係
- Context / KV Cache
- LLM Server / API
- Tool Calling
- Agent設計
- 認証・認可
- ローカルでの音声処理
- 家族ごとのデータ分離

最終的には、家族それぞれが専用デバイスからAIエージェントと会話し、予定・伝言・学校情報・健康情報などを、権限に応じて安全に扱える仕組みを目指す。

---

## Concept

```text
                    Home PC
                       │
                 NVIDIA GPU
                       │
          ┌────────────┼────────────┐
          │            │            │
         LLM          STT          TTS
          │            │            │
          └────────────┼────────────┘
                       │
                  Agent Server
                       │
               Authorization
                       │
                  Family Data
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      Parent A       Parent B        Child
        │              │              │
     Device         Device          Device
```

家族ごとにLLMを別々に起動するのではなく、1つのLLMを共有し、

- user_id
- memory
- accessible data
- permissions
- conversation context

をAgent層で分離する。

---

## Core Principle

### Agent ≠ LLM

LLMは推論エンジン。

家族ごとの違いはAgent側で管理する。

```text
User / Device
 ↓ Authentication
Session Context
 ↓
Agent / Local LLM (Tool proposal only)
 ↓ Validation / Authorization / Confirmation
Tool / Database
 ↓ Filtered Result
Local LLM
 ↓
Response
```

LLMはToolを提案できるが、identity、権限、実行可否は決定しない。

---

## Development Modes

### Study Mode

Local LLMとGPUを理解するための、localhost・単一ユーザー・テストデータ限定の環境。

### Dev Mode

複数ユーザー、認証、認可、Agent機能を実装・検証する環境。テスト用の家族データだけを使い、実データは扱わない。

### Family Mode

家族の実データを扱う環境。認証、認可、世帯分離、監査、暗号化backup、復旧手順を必須とする。

Study Modeで仕組みを理解し、Dev Modeで安全性を検証してからFamily Modeへ進む。

```text
Study Mode → Dev Mode → Family Mode
理解          実装・検証      実運用
```

---

## Important Security Principle

LLMをデータベースとして使わない。

予定や健康情報などは構造化データとして保存し、必要なものだけをLLMへ渡す。

悪い例:

```text
System prompt:
"父親には母親の病院情報を見せないでください"
```

これはセキュリティではない。

正しい考え方:

```text
Request
 ↓
Authorization Check
 ↓
Allowed Data Only
 ↓
LLM
```

現在のrequestに必要なデータだけをLLMへ渡す。conversation history、memory、cache、log、backupも同じ単位で分離・保護する。

---

## Initial MVP

最初のCalendar Studyでは、物理デバイスも音声も使わず、localhost・単一ユーザー・テストデータに限定する。

Terminalから以下ができればよい。

```text
Marie:
> 9月3日15時に歯医者

AI:
> 予定を登録しました。

Marie:
> 来週病院ある？

AI:
> 9月3日15時に歯医者があります。
```

内部では:

```text
Natural Language
 ↓
Local LLM
 ↓
Tool Proposal
 ↓
Validation / Confirmation
 ↓
SQLite
```

実データを使うFamily MVPは、認証、session、authorization、監査、backupとrestore testの完成後に開始する。

---

## Getting Started (Study Mode)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# テスト (LLM 不要)
.venv/bin/pytest

# Ollama が動いているマシンで REPL を起動
.venv/bin/python -m family_ai.cli --model qwen3:8b --db study.db
```

---

## Project Roadmap

詳細は以下。

- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [LLM / GPU Experiments](docs/EXPERIMENTS.md)
- [Security](docs/SECURITY.md)
- [Development Log](docs/DEVLOG.md)

---

## Initial Technology Candidates

### Inference

- Ollama
- llama.cpp

### Model

候補:

- Qwen系
- Llama系

モデルサイズ・量子化方式は実測しながら決定する。

### Database

Initial MVP:

- SQLite

将来的には必要に応じてPostgreSQLなどを検討。

### Agent Server

候補:

- Python
- TypeScript

### Speech

後期フェーズで追加。

- Speech-to-Text
- Text-to-Speech
- Wake Word

すべて可能な範囲でローカル処理する。

---

## Development Philosophy

このプロジェクトでは、完成を急ぐより「何が起きているかを理解する」ことを優先する。

特に以下は実測する。

- モデルロード時のVRAM
- 推論中のGPU使用率
- tokens/sec
- context lengthとVRAM
- KV cache
- Q4 / Q6 / Q8の違い
- 8B / 14B / 30Bクラスの違い
- concurrent request時の挙動

`nvidia-smi` などを使い、LLMの内部挙動とGPUの状態を対応づける。

---

## Non-Goals

初期段階では以下をやらない。

- 完成されたスマートフォンアプリ
- 商用レベルのUI
- 独自ハードウェア
- 完璧な音声UX
- クラウド連携
- 大規模なRAG

まずはLocal LLM / GPU / Agent / Data / Permissionの理解を優先する。

---

## Final Vision

```text
Family AI Hub
    │
    ├── Local LLM
    ├── Local STT
    ├── Local TTS
    ├── Family Database
    ├── Authentication
    ├── Authorization
    └── Agent API
          │
     ┌────┼────┐
     │    │    │
    👩    👨   👧
```

家族の情報をクラウドへ送らず、自宅のコンピュータ上で管理する。

単なるAIチャットではなく、

**Private / Local-first Family AI Platform**

を作る。
