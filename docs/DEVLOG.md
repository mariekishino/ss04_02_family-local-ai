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
