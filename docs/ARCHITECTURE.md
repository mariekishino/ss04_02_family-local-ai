# Architecture

## 1. Overview

Family Local AIは、LLMを自然言語interfaceとして利用し、identity、権限、永続データを決定させない。

```text
Client Device
     │
     ▼
API / Agent Gateway
     ├── Authentication / Session
     ├── Authorization
     ├── Conversation Isolation
     ├── Tool Validation / Confirmation
     └── Audit
             │
        ┌────┴────┐
        ▼         ▼
   Local LLM    Database
        │
        ▼
       GPU
```

## 2. Development Modes

### Study Mode

localhost、単一ユーザー、テストデータに限定した学習環境。GPU、LLM、Tool Callingの仕組みを理解する。認証などを省略した実装は次のModeへそのまま流用しない。

### Dev Mode

複数ユーザー、認証、認可、Agent機能を実装・検証する環境。実データを模したfixtureを使うが、家族の実データは扱わない。世帯間アクセス、session失効、Prompt Injection、backupとrestoreをテストする。

### Family Mode

Dev Modeの完了条件を満たした後に、家族の実データを扱う環境。認証、認可、世帯分離、監査、暗号化backup、復旧、更新手順を必須とする。

```text
Study Mode → Dev Mode → Family Mode
理解          実装・検証      実運用
```

## 3. Main Components

### Client

初期はTerminal、将来はWeb UI、Smartphone、Dedicated Deviceを想定する。ClientはAIモデルや最終的な権限判断を持たない。

### Agent Gateway

責務:

- authenticationとsession検証
- server-side request contextの生成
- conversationとmemoryの分離
- LLM requestとTool proposalの受信
- schema validation、authorization、confirmation
- Tool execution、result filtering、audit

### Local LLM

責務は自然言語理解、Toolの提案、要約、自然言語生成。user identity、household identity、permission、永続保存、Toolの実行可否は決定させない。

### Database

初期はSQLiteを使用する。Dev Mode以降では、すべての対象resourceを `household_id` で分離する。

## 4. Trust Boundaries

LLM、ユーザー入力、Toolから取得した文章、音声認識結果をUntrusted Inputとして扱う。LLM outputをそのままDatabase write、OS command、File accessへ接続しない。

Tool層では次を順に実施する。

1. JSON parse
2. allowlist確認
3. schema validation
4. authorization
5. riskに応じたconfirmation
6. transaction内でのexecution
7. result filtering
8. audit

## 5. Canonical Request Flow

```text
User / Device
      ↓
Authentication
      ↓
Session Context
(actor_user_id, household_id, device_id)
      ↓
Agent Gateway
      ↓
Local LLM (Tool proposal only)
      ↓
Schema Validation
      ↓
Authorization
      ↓
Confirmation if required
      ↓
Tool Execution
      ↓
Result Filtering
      ↓
Local LLM
      ↓
Response
```

認可は一度だけではない。Tool実行前にaction単位で判定し、Database queryでも世帯と参照範囲を強制する。

## 6. Identity Model

```text
device_id ≠ user_id
```

端末を識別できても、現在操作している人物を識別できるとは限らない。requestの信頼できるcontextは認証済みsessionからサーバーが生成する。

LLMやClientから送られた `actor_user_id`、`household_id`、role、permissionを信用しない。音声識別は補助情報として扱い、それだけを高リスク操作の認証には使用しない。

## 7. Data Model

### households

```text
id
name
created_at
```

### users

```text
id
login_name
display_name
disabled_at
created_at
```

### household_members

```text
household_id
user_id
role
joined_at
```

### devices

```text
id
household_id
name
credential_hash
registered_at
revoked_at
```

### sessions

```text
id
user_id
device_id
expires_at
revoked_at
created_at
```

### events

```text
id
household_id
owner_user_id
created_by_user_id
title
start_at
end_at
timezone
visibility
version
created_at
updated_at
deleted_at
```

### messages

```text
id
household_id
sender_user_id
recipient_user_id
content
status
expires_at
read_at
revoked_at
created_at
```

### audit_events

```text
id
household_id
actor_user_id
action
resource_type
resource_id
result
created_at
```

監査ログには予定名、伝言本文、promptなどの機密本文を原則保存しない。

## 8. Authorization Model

初期のvisibilityは `PRIVATE`、`HOUSEHOLD`、`GUARDIANS` とする。

- `role`: 人が世帯内で持つ関係
- `visibility`: resourceの共有範囲
- `action`: read、create、update、delete、shareなどの操作

認可関数は少なくとも以下を入力とする。

```text
authorize(actor, household, resource, action)
```

最初から汎用ACLを作らず、明示的なpolicyで開始する。個別共有が必要になった場合にのみACLを追加する。

## 9. Tool Design

Toolごとにriskと実行条件を宣言する。

```yaml
name: delete_event
risk: medium
requires_confirmation: true
authorization: event.delete
audit: true
idempotent: true
```

### Risk Levels

- Low: 自分が参照可能な予定の検索など
- Medium: 予定追加・更新・削除、伝言送信など
- High: 権限変更、ユーザー・デバイス登録、大量操作など

High Risk操作では再認証または強いconfirmationを要求する。

### Server-owned Arguments

`actor_user_id`、`household_id`、認可済みowner scopeはGatewayが設定する。LLMに生成させない。

### Operational Requirements

- 入出力schemaと長さ・件数制限
- timeout、retry方針、transaction
- 書き込みのidempotency key
- 論理削除とundo
- エラー情報の最小化

## 10. Multi-user Isolation

共有するもの:

- model weights、inference server、GPU

分離するもの:

- identity、session
- conversation history、summary、memory
- household data、permissions
- cache、temporary files、logs

現在の検索結果だけでなく、過去のconversationやcacheからも別ユーザーの情報が混入しないようにする。

## 11. Speech and Device Architecture

```text
Microphone → Wake Word → Speech-to-Text → Agent Gateway
           → LLM / Tool → Text-to-Speech → Speaker
```

Dedicated DeviceはThin Clientとし、Mic、Speaker、confirmation button、recording LED、Wi-Fi、device identityを持つ。重い推論はHome Server側で行う。

## 12. Design Principle

```text
Authenticated Identity
 ↓
Server-owned Context
 ↓
LLM Tool Proposal
 ↓
Validation + Authorization + Confirmation
 ↓
Data Access
 ↓
Filtered Result
```

LLMは便利な提案者であり、権限主体でも実行主体でもない。
