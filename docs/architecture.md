# AgentGate architecture

AgentGate is a local-first control plane for tool-calling agents. The model can propose an action, but the policy engine and persisted action state decide whether that proposal can execute.

## Context and components

```mermaid
flowchart LR
    Browser[Browser console]
    API[FastAPI API]
    Runner[AgentRunner]
    Policy[PolicyEngine]
    DB[(SQLite)]
    Executor[ToolExecutor]
    Tools[Allowlisted tools]
    LLM[Mock or OpenAI-compatible LLM]

    Browser -->|REST + SSE| API
    API --> Runner
    Runner --> LLM
    Runner --> Policy
    Policy --> DB
    Runner --> DB
    Runner --> Executor
    Executor --> Tools
    Executor --> DB
```

The API owns run creation, detail reads, approvals, audit queries and the SSE stream. `AgentRunner` is the single stateful orchestration boundary: it loads a checkpoint, calls the provider-neutral LLM interface, validates tool arguments, routes through policy, and resumes after an approval decision.

## Run and action state machines

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running
    running --> waiting_approval: medium-risk proposal
    waiting_approval --> running: approve or deny
    running --> completed: final answer
    running --> failed: timeout or safe failure
    completed --> [*]
    failed --> [*]
```

```mermaid
stateDiagram-v2
    [*] --> proposed
    proposed --> auto_approved: low-risk read-only
    proposed --> pending_approval: state-changing medium risk
    proposed --> denied: high risk or invalid/unknown tool
    pending_approval --> approved: human approve
    pending_approval --> denied: human deny
    auto_approved --> running
    approved --> running
    running --> succeeded
    running --> failed
    denied --> [*]
    succeeded --> [*]
    failed --> [*]
```

## Approval sequence

```mermaid
sequenceDiagram
    participant Browser
    participant API
    participant Policy
    participant DB
    participant Human
    participant Executor
    participant AgentRunner
    participant LLM

    Browser->>API: POST /api/runs
    API->>AgentRunner: start run
    AgentRunner->>LLM: complete(messages, tools)
    LLM-->>AgentRunner: tool proposal
    AgentRunner->>Policy: evaluate(tool, arguments)
    Policy->>DB: persist decision and action
    Policy-->>AgentRunner: require approval
    AgentRunner-->>API: waiting_approval
    API-->>Browser: detail + SSE update
    Human->>Browser: approve or deny
    Browser->>API: POST /api/approvals/{id}/approve
    API->>DB: atomic pending -> approved
    API->>Executor: execute once
    Executor->>DB: persist result + audit
    API->>AgentRunner: resume from checkpoint
    AgentRunner->>LLM: complete(messages + tool result, tools)
    LLM-->>AgentRunner: final answer or next proposal
    AgentRunner-->>API: completed or next safe state
```

## Transaction and idempotency boundaries

- Run and action checkpoints are committed before the next provider call. A crash therefore leaves the conversation and step count available for resume.
- Policy decisions are persisted with the proposed action before an execution can begin.
- `ToolExecutor` claims an action with a conditional `pending/approved`-style transition to `running`. The unique `idempotency_key` is derived from run ID and model tool-call ID.
- A second execution request returns the persisted success or fails safely when another worker owns the running action. Only the first successful claim may invoke a handler.
- Approval is a conditional `pending_approval -> approved|denied` transition. Duplicate clicks return a conflict and do not resume the run a second time.
- Audit events are append-only records. Sensitive keys are recursively redacted before storage and again at API serialization boundaries.

## Why these choices

- **SSE:** run events are append-only and server-to-browser, so SSE keeps the console simple while still showing persisted state changes promptly. REST remains the source of truth after reconnect.
- **SQLite:** it is zero-setup for a local interview demo and makes checkpoints and audit history inspectable. Production should move to PostgreSQL with migrations and concurrent worker coordination.
- **Direct OpenAI SDK:** the adapter uses the official Python client for OpenAI-compatible chat completions while exposing only provider-neutral `ModelTurn` and `ToolCall` types to the agent loop.
- **One Agent:** a single runner keeps approval semantics, tool-call ordering and checkpoint recovery unambiguous for the MVP. Specialized agents can be added behind the same policy/executor boundary later.

## Local-demo limitations and production path

The demo has a deterministic mock provider, two simulated services, one process-local event broker, SQLite persistence, and no authentication or multi-tenant isolation. Tool handlers are intentionally local and do not change real infrastructure. A production evolution would add authenticated actors, RBAC, PostgreSQL migrations, durable event delivery, distributed action leases, secret-manager integration, richer policy versioning, provider observability, and isolated tool workers.
