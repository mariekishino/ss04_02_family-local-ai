# Roadmap

## Goal

Family Local AIの実装を通して、Local LLM、GPU、Agent、Tool Calling、Database、認証・認可、音声、Hardware、家庭内サーバー運用を段階的に理解する。

完成を急ぐのではなく、各Phaseで「何が起きているか」を説明できる状態を目指す。

## Development Modes

### Study Mode

学習・実験専用の環境。

- localhost限定、単一ユーザー、テストデータのみ
- DBは破棄可能で、外部公開しない
- 認証を省略する場合は、その制約を明記する

### Dev Mode

複数ユーザー機能と安全性を実装・検証する環境。

- テスト用の家族データのみを使用
- 認証、session、世帯分離、認可を実装
- 攻撃・障害・backup・restoreをテスト
- 実データは扱わない

### Family Mode

家族の実データを扱う運用環境。

- 認証必須、世帯・ユーザー・sessionを分離
- すべてのToolで認可
- 暗号化backup、監査ログ、更新・復旧手順を用意

```text
Study Mode → Dev Mode → Family Mode
理解          実装・検証      実運用
```

Study Modeで動いたことを理由に、そのままFamily Modeへ移行しない。Dev ModeでFamily Modeのentry criteriaを検証する。

## Mode Assignment

| Phase | Primary Mode | Meaning |
|---|---|---|
| 0–4 | Study Mode | 推論、Server、Tool、単一ユーザー予定を理解する |
| 5–6 | Dev Mode | identity、世帯分離、認証・認可を実装・検証する |
| 7 | Dev → Family | entry criteriaを満たし、Family Calendarを実運用へ移す |
| 8–11 | Study → Dev → Family | 各機能を理解・検証してから段階的に実運用へ追加する |

3つのModeは別々の設定・データとして維持し、Family Mode上で直接実験しない。

---

# Phase 0 — Reproducible Baseline

## Goal

現在のLocal LLM環境を、後から再現できる形で記録する。

## Tasks

- [ ] GPU、VRAM、CPU、RAM、OSを記録
- [ ] NVIDIA Driver、CUDA runtimeを記録
- [ ] Ollama、llama.cppのversionを記録
- [ ] model ID、GGUFファイル名、hashを記録
- [ ] 固定promptによる初期測定

## Deliverables

`docs/EXPERIMENTS.md` にBaselineを記録する。

## Exit Criteria

同じモデルと設定で再測定し、結果の差を説明できる。

---

# Phase 1 — Understand Local Inference

## Goal

LLM推論時にGPUで何が起きているか理解する。

## Tasks

- [ ] 8B、14B、可能なら30B前後を試す
- [ ] Q4 / Q6 / Q8を比較
- [ ] context lengthとKV Cacheの変化を観察
- [ ] Prompt PrefillとDecodeを分けて測定
- [ ] peak VRAM、RAM、消費電力を測定
- [ ] prompt tok/s、generation tok/s、TTFTを測定
- [ ] warm-up後に複数回測定し、p50 / p95を記録

## Questions

- パラメータ数とVRAM使用量はどの程度比例するか
- 量子化で何が減り、何が劣化するか
- KV Cacheはいつ、どれだけ増えるか
- PrefillとDecodeでGPU負荷はどう違うか
- どこがボトルネックになるか

## Exit Criteria

モデルサイズ、量子化、context lengthと性能の関係を実測値で説明できる。

---

# Phase 2 — Inference Server

## Goal

Ollamaとllama.cppが抽象化している処理を理解し、アプリケーションから安全に呼べるようにする。

## Tasks

- [ ] llama.cppをビルドし、GGUFモデルを直接ロード
- [ ] GPU offload、context、batchを設定
- [ ] Ollamaとllama.cppを比較
- [ ] Local HTTP Serverを起動
- [ ] curlとPythonまたはTypeScriptから呼び出す
- [ ] timeout、切断、モデル停止時のエラーを処理
- [ ] conversation stateをアプリケーション側で管理
- [ ] concurrent requestを測定

## Non-Goals

- Agentや家族データの実装
- 外部ネットワークへの公開

## Exit Criteria

- request / response構造を説明できる
- 異常時に呼び出し元が安全に失敗できる
- 同時リクエスト時の待ち時間とthroughputを説明できる

---

# Phase 3 — Safe Tool Foundation

## Goal

LLMの出力を直接実行しないTool境界を作る。

```text
LLM Tool Proposal
 ↓ JSON Parse
Schema Validation
 ↓ Policy Check
Execution
 ↓
Sanitized Result
```

## Initial Tools

- `get_current_time`
- `get_test_events`

最初は読み取り専用Toolだけを使う。

## Tasks

- [ ] Tool allowlistと厳格な入出力schema
- [ ] 不明なToolと余分な引数の拒否
- [ ] 文字列長、取得件数、実行時間の上限
- [ ] timeoutと安全なエラー応答
- [ ] Tool呼び出しの監査記録

## Exit Criteria

壊れたJSON、不正な引数、存在しないToolを実行せず、安全に拒否できる。

---

# Phase 4 — Single-user Calendar Study

## Goal

Study Modeで自然言語から予定を登録・検索する。

## Constraints

- localhost限定、単一ユーザー、テストデータのみ
- disposable SQLite database

## Features

- [ ] `get_events`
- [ ] `add_event`
- [ ] `update_event`
- [ ] `delete_event`

## Safety

- 書き込み前に、解釈した日時と内容を確認する
- `delete_event` は `deleted_at` を使った論理削除にする
- undoを用意する
- idempotency keyとtransactionを使う

## Example

```text
User: 「9月3日15時に歯医者」
Agent: 「2026年9月3日15時に『歯医者』を登録します。よいですか？」

Tool Proposal:
add_event(start_at="2026-09-03T15:00:00+09:00", title="歯医者")
```

## Exit Criteria

読み取り、追加、更新、論理削除、undoがテストデータで動作する。

---

# Phase 5 — Household and Identity

## Goal

世帯、ユーザー、デバイス、sessionを明示的に分離する。

このPhaseからDev Modeを使用する。

## Tasks

- [ ] `households`、`users`、`household_members`
- [ ] `devices`、`sessions`
- [ ] session期限と失効
- [ ] デバイス紛失時の失効

## Principle

```text
device_id ≠ user_id
```

デバイスを識別できても、現在操作している人を識別できるとは限らない。

## Exit Criteria

- すべてのrequestにサーバー側で確定した `actor_user_id` と `household_id` がある
- sessionの期限切れと失効を処理できる

---

# Phase 6 — Authorization

## Goal

「家族だから全部見える」をやめ、データアクセスをサーバー側で強制する。

## Initial Visibility

| Visibility | Owner | Household Member | Guardian |
|---|---:|---:|---:|
| PRIVATE | RW | - | - |
| HOUSEHOLD | RW | R | R |
| GUARDIANS | RW | - | R |

実際の権限は、resource種別、本人との関係、actionを含めて判定する。

## Rules

- LLMに `actor_user_id` や `household_id` を指定させない
- 検索条件には必ず `household_id` を含める
- Tool実行前にaction単位で認可する
- Database queryでも参照可能範囲を制限する
- 拒否応答からresourceの存在を推測できないようにする

## Exit Criteria

- 別ユーザーのPRIVATEデータを取得できない
- resource IDを直接指定しても別世帯のデータへアクセスできない
- 不正なTool Callを実行前に拒否できる

---

# Phase 7 — Family Calendar MVP

## Goal

Family Modeで安全に使える最初の機能を完成させる。

Dev Modeで以下のentry criteriaを満たした後、Family Modeへ移行する。

## Entry Criteria

- 認証、session失効、authorization testが動作する
- OSのdisk encryptionが有効
- backupが暗号化されている

## Tasks

- [ ] 複数ユーザーの予定登録・検索
- [ ] PRIVATE / HOUSEHOLD / GUARDIANS
- [ ] 操作監査
- [ ] 論理削除とundo
- [ ] backupとrestore test

## Exit Criteria

認証、認可、監査、復元を含むend-to-end testが成功する。

---

# Phase 8 — Basic Messaging

## Goal

家族間で単純な伝言を送受信する。

## Scope

- 送信、受信一覧、既読、送信取り消し、有効期限

## Non-Goals

- 在宅・オンライン状態による自動配送
- 複雑な条件式

条件付き配送は、event検知、永続queue、重複防止、期限切れを設計した別Phaseで扱う。

---

# Phase 9 — Speech Study

## Goal

音声入出力の品質とリスクをStudy Modeで評価し、認証や権限制御との統合をDev Modeで検証する。

```text
Microphone → Wake Word → Local STT → Agent Gateway → Local TTS → Speaker
```

## Tasks

- [ ] Local STT / TTSとend-to-end latency
- [ ] 誤起動・聞き逃し測定
- [ ] 録音中を示すUI
- [ ] 音声データの保存方針
- [ ] 認証が曖昧な場合の操作制限

## Principle

音声識別だけを強い認証として扱わない。

---

# Phase 10 — Dedicated Device

## Goal

Thin Clientとして専用デバイスを作る。

## Responsibilities

- microphone、speaker、confirmation button、recording LED
- Wi-Fi、device identity、安全な登録・失効・更新

重い推論はHome Server側で行う。

---

# Phase 11 — Family AI Hub Operations

## Goal

家庭内で常時、安全に動作するサーバーとして統合する。

## Tasks

- [ ] 自動起動とhealth check
- [ ] database backupと定期restore test
- [ ] ログローテーションとディスク容量監視
- [ ] 停電・異常終了後の復旧
- [ ] セキュリティ更新手順
- [ ] model、STT、TTSのGPU競合測定

---

# Common Phase Template

各Phaseは必要に応じて次の項目を持つ。

```markdown
## Goal
## Scope
## Non-Goals
## Threats
## Tasks
## Deliverables
## Exit Criteria
## Questions
```

新機能を追加する前に、このPhaseで何を理解し、どの条件を満たせば完了なのかを明確にする。
