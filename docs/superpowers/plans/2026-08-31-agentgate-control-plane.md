# AgentGate Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 3–5 天内从空仓库构建一个可本地演示的 Agent 动作控制平面，展示 tool calling、风险策略、人工审批、持久化暂停/恢复、实时 UI、审计和确定性评测。

**Architecture:** FastAPI 单体负责 Agent loop、工具注册、策略、审批和 SQLite 持久化；React 控制台通过 REST 写入、通过 SSE 观察运行状态。模型层同时提供 OpenAI-compatible adapter 与确定性的 Mock adapter，所有工具执行先经过 schema 校验、策略决策和幂等保护。

**Tech Stack:** Python 3.11+、FastAPI、SQLModel、Pydantic v2、OpenAI Python SDK、SQLite、React 18、TypeScript、Vite、pytest、Vitest、Playwright、Docker Compose、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-08-31-agentgate-control-plane-design.md`

## Global Constraints

- 本计划在一个名为 `agentgate-control-plane` 的全新仓库根目录执行，不在 `realtime-ai-intel-warehouse` 中执行实现步骤。
- 每个行为变更遵守 red → green → refactor：先写测试并看到预期失败，再写最小实现，再运行目标测试。
- 所有运维工具只修改本地 SQLite 模拟状态；禁止执行 shell、访问真实基础设施或真的轮换凭据。
- 默认 CI 使用 `MockLLMProvider`，不依赖网络或付费 API；live smoke test 仅手动运行。
- API key 只从后端环境变量读取，不进入前端、不写日志、不提交 Git。
- 未注册工具、无风险元数据、参数错误和非法状态转换全部 fail closed。
- 在完成每个任务前运行该任务列出的验证命令；在声称项目完成前运行最终验证矩阵。
- 所有提交信息使用 Conventional Commits；每个任务的提交点可在测试通过后执行。

---

## Milestone Map

| Day | Outcome | Tasks |
|---|---|---|
| Day 1 | 仓库、数据模型、策略内核可测试 | 1–3 |
| Day 2 | 工具执行与 Agent loop 可确定性运行 | 4–5 |
| Day 3 | 审批恢复、REST/SSE 与核心 UI 完成 | 6–7 |
| Day 4 | eval、E2E、文档与容器化完成 | 8–9 |
| Day 5 buffer | 真实模型联调、视觉细化、录屏和面试演练 | Task 9 的 live smoke 与 polish，不新增产品范围 |

## Task 1: Scaffold the Monorepo and Lock Contracts

**Files:**

- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `compose.yaml`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/app/__init__.py`
- Create: `apps/api/app/config.py`
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/api/__init__.py`
- Create: `apps/api/app/api/health.py`
- Create: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_health.py`
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/styles.css`
- Create: `apps/web/src/App.test.tsx`
- Create: `.github/workflows/ci.yml`
- Copy: `docs/superpowers/specs/2026-08-31-agentgate-control-plane-design.md`
- Copy: `docs/superpowers/plans/2026-08-31-agentgate-control-plane.md`

- [ ] **Step 1: Initialize the empty repository and directories**

Run from the parent directory:

```powershell
New-Item -ItemType Directory -Path agentgate-control-plane
Set-Location agentgate-control-plane
git init
New-Item -ItemType Directory -Force -Path apps/api/app/api,apps/api/tests,apps/web/src,docs/superpowers/specs,docs/superpowers/plans,.github/workflows,scripts,data
```

Copy this specification and plan into the matching `docs/superpowers/...` paths before continuing.

- [ ] **Step 2: Write the backend health test first**

`apps/api/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "agentgate-api"}
```

`apps/api/tests/conftest.py` must set deterministic test configuration before app imports:

```python
import os

os.environ.setdefault("AGENTGATE_LLM_PROVIDER", "mock")
os.environ.setdefault("AGENTGATE_DATABASE_URL", "sqlite://")
```

- [ ] **Step 3: Define backend dependencies and confirm the test fails for missing app code**

Use this dependency set in `apps/api/pyproject.toml`:

```toml
[project]
name = "agentgate-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.141,<1",
  "httpx>=0.28,<1",
  "openai>=3.6,<4",
  "pydantic-settings>=2.15,<3",
  "sqlmodel>=0.0.42,<0.1",
  "uvicorn[standard]>=0.52,<1",
]

[project.optional-dependencies]
dev = [
  "mypy>=2.3,<3",
  "pytest>=9.1,<10",
  "pytest-asyncio>=1.4,<2",
  "ruff>=0.16,<1",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
```

Run:

```powershell
Set-Location apps/api
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_health.py -q
```

Expected: FAIL because `app.main` or `/health` does not exist.

- [ ] **Step 4: Implement minimal settings and health route**

`apps/api/app/config.py` must define a cached `Settings` with these environment-backed fields:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTGATE_",
        env_file=(".env", "../../.env"),
        extra="ignore",
    )

    app_name: str = "agentgate-api"
    llm_provider: str = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "mock-operations-agent"
    database_url: str = "sqlite:///./data/agentgate.db"
    max_steps: int = 8
    tool_timeout_seconds: int = 10
    run_timeout_seconds: int = 120
    web_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Create an `APIRouter` in `health.py`; include it in `main.py`; add local-only CORS using `settings.web_origin`.

- [ ] **Step 5: Run backend test and quality checks**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_health.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

Expected: one passing test and zero lint/type errors.

- [ ] **Step 6: Create frontend shell test, see it fail, then implement the shell**

`apps/web/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("identifies the product as a local agent control plane", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "AgentGate" })).toBeInTheDocument();
    expect(screen.getByText("Local Demo")).toBeInTheDocument();
  });
});
```

Configure `package.json` scripts: `dev`, `build`, `test`, `lint`, and `typecheck`. Dependencies must include React, React DOM and React Router; dev dependencies must include Vite, TypeScript, Vitest, jsdom, ESLint, Testing Library and React type packages.

Run `npm install`, then `npm test -- --run`; confirm the test fails before implementing `App.tsx`. Implement only a product header and placeholder `<main>` sufficient to pass.

- [ ] **Step 7: Add secret-safe environment and ignore rules**

`.env.example`:

```dotenv
AGENTGATE_LLM_PROVIDER=openai_compatible
AGENTGATE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3
AGENTGATE_LLM_API_KEY=your_api_key_here
AGENTGATE_LLM_MODEL=doubao-seed-2-0-lite-260215
AGENTGATE_DATABASE_URL=sqlite:///./data/agentgate.db
AGENTGATE_MAX_STEPS=8
AGENTGATE_TOOL_TIMEOUT_SECONDS=10
AGENTGATE_RUN_TIMEOUT_SECONDS=120
AGENTGATE_WEB_ORIGIN=http://localhost:5173
```

`.gitignore` must include `.env`, `.venv/`, `node_modules/`, `dist/`, `data/*.db`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `playwright-report/`, and `test-results/`.

- [ ] **Step 8: Add baseline CI and verify both workspaces**

CI must use Python 3.11 and Node 24 LTS, install each workspace, then run backend tests/lint/typecheck and frontend tests/lint/typecheck/build. Do not configure API secrets.

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\web
npm test -- --run
npm run typecheck
npm run build
```

- [ ] **Step 9: Commit the scaffold**

```powershell
git add .
git commit -m "chore: scaffold agentgate control plane"
```

## Task 2: Persist Runs, Actions, Audit Events, and Mock Service State

**Files:**

- Create: `apps/api/app/db.py`
- Create: `apps/api/app/models.py`
- Create: `apps/api/app/schemas.py`
- Create: `apps/api/app/repositories.py`
- Create: `apps/api/tests/test_repositories.py`
- Modify: `apps/api/tests/conftest.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write repository state-transition tests**

Tests must cover:

```python
def test_create_run_defaults_to_queued(session: Session) -> None: ...

def test_action_idempotency_key_is_unique(session: Session) -> None: ...

def test_pending_action_can_be_atomically_claimed_once(session: Session) -> None: ...

def test_audit_repository_exposes_append_and_list_only(session: Session) -> None: ...

def test_seeded_payments_service_is_degraded(session: Session) -> None: ...
```

For the duplicate idempotency test, insert two actions with the same `{run_id}:{tool_call_id}` and assert the second commit raises `IntegrityError`.

- [ ] **Step 2: Run tests to verify missing persistence layer**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_repositories.py -q
```

Expected: FAIL on missing `app.db`, `app.models`, or repository classes.

- [ ] **Step 3: Implement enums and SQLModel tables**

Define string enums exactly as follows:

```python
class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    AUTO_APPROVED = "auto_approved"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DENIED = "denied"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PolicyDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"
```

Implement the four tables from the spec. Store timestamps as timezone-aware UTC. Add a unique index to `ToolAction.idempotency_key` and indexes to `run_id`, `status`, `event_type`, and `created_at` where queries use them.

- [ ] **Step 4: Implement the session fixture and startup initialization**

`db.py` must expose `create_db_engine(url)`, `create_db_and_tables(engine)`, `get_session()`, and `seed_demo_state(session)`. For SQLite, pass `check_same_thread=False`; for in-memory tests use `StaticPool`.

The test fixture creates a fresh in-memory database per test and overrides FastAPI's session dependency. Startup creates tables and upserts:

```python
ServiceState(service="payments-api", health="degraded", restart_count=0)
ServiceState(service="orders-api", health="healthy", restart_count=0)
```

- [ ] **Step 5: Implement narrow repositories**

Provide these methods with typed return values:

```python
class RunRepository:
    def create(self, user_request: str, provider: str, model: str) -> AgentRun: ...
    def get(self, run_id: UUID) -> AgentRun | None: ...
    def list(self, limit: int = 50) -> list[AgentRun]: ...
    def set_status(self, run_id: UUID, expected: set[RunStatus], target: RunStatus) -> bool: ...
    def save_checkpoint(self, run_id: UUID, messages: list[dict[str, object]], step_count: int) -> None: ...

class ActionRepository:
    def create(self, action: ToolAction) -> ToolAction: ...
    def get(self, action_id: UUID) -> ToolAction | None: ...
    def list_for_run(self, run_id: UUID) -> list[ToolAction]: ...
    def transition(self, action_id: UUID, expected: set[ActionStatus], target: ActionStatus) -> bool: ...

class AuditRepository:
    def append(self, event: AuditEvent) -> AuditEvent: ...
    def list(self, run_id: UUID | None = None, event_type: str | None = None, actor: str | None = None) -> list[AuditEvent]: ...
```

Do not add audit update/delete methods.

- [ ] **Step 6: Run persistence tests and quality checks**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_repositories.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

- [ ] **Step 7: Commit the persistence layer**

```powershell
git add apps/api
git commit -m "feat: add persistent agent run state"
```

## Task 3: Build a Fail-Closed Policy Engine and Audit Redaction

**Files:**

- Create: `apps/api/app/tools/__init__.py`
- Create: `apps/api/app/tools/base.py`
- Create: `apps/api/app/policy.py`
- Create: `apps/api/app/services/__init__.py`
- Create: `apps/api/app/services/audit.py`
- Create: `apps/api/tests/test_policy.py`
- Create: `apps/api/tests/test_audit.py`

- [ ] **Step 1: Write the policy decision matrix tests**

Construct `ToolSpec` instances and assert this exact matrix:

```python
@pytest.mark.parametrize(
    ("risk", "read_only", "expected"),
    [
        (RiskLevel.LOW, True, PolicyDecision.AUTO_APPROVE),
        (RiskLevel.LOW, False, PolicyDecision.DENY),
        (RiskLevel.MEDIUM, False, PolicyDecision.REQUIRE_APPROVAL),
        (RiskLevel.HIGH, False, PolicyDecision.DENY),
    ],
)
def test_policy_matrix(risk: RiskLevel, read_only: bool, expected: PolicyDecision) -> None: ...
```

Also test that absent/invalid tool metadata cannot be constructed and that each result contains a non-empty human-readable reason.

- [ ] **Step 2: Write recursive redaction tests**

```python
def test_redact_secrets_recursively() -> None:
    payload = {
        "authorization": "Bearer abc",
        "nested": {"api_key": "secret", "safe": "visible"},
        "items": [{"password": "p"}, {"token": "t"}],
    }

    assert redact(payload) == {
        "authorization": "***REDACTED***",
        "nested": {"api_key": "***REDACTED***", "safe": "visible"},
        "items": [{"password": "***REDACTED***"}, {"token": "***REDACTED***"}],
    }
```

Add a test proving `AuditService.append()` serializes only the redacted payload.

- [ ] **Step 3: Run focused tests and observe failure**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_policy.py tests/test_audit.py -q
```

- [ ] **Step 4: Implement immutable tool specifications and policy results**

`ToolSpec` fields:

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters_schema: dict[str, object]
    risk_level: RiskLevel
    read_only: bool
```

`PolicyResult` is a frozen dataclass containing `decision`, `risk_level`, and `reason`. `PolicyEngine.evaluate()` implements only the four rules in the design spec; it must not call the model.

- [ ] **Step 5: Implement recursive audit redaction**

Treat key names case-insensitively. Sensitive exact keys are `api_key`, `authorization`, `token`, `secret`, and `password`. Redact dictionaries nested inside lists/tuples. `AuditService` creates timestamps and IDs, redacts before JSON serialization, then calls `AuditRepository.append()`.

- [ ] **Step 6: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_policy.py tests/test_audit.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
git add apps/api
git commit -m "feat: enforce fail-closed action policies"
```

## Task 4: Register Safe Mock Tools and Make Execution Idempotent

**Files:**

- Create: `apps/api/app/tools/operations.py`
- Create: `apps/api/app/tools/registry.py`
- Create: `apps/api/app/services/executor.py`
- Create: `apps/api/tests/test_tool_registry.py`
- Create: `apps/api/tests/test_executor.py`

- [ ] **Step 1: Write registry allowlist and schema tests**

Tests must prove:

- registry exposes exactly `get_service_health`, `search_logs`, `restart_service`, `rotate_api_key`;
- `schemas()` emits OpenAI function-tool schema for all four;
- unknown names raise `UnknownToolError`;
- invalid arguments fail Pydantic validation before any handler invocation;
- `rotate_api_key` has no executable handler in the registry.

- [ ] **Step 2: Write executor behavior tests**

Cover these observable outcomes:

```python
async def test_read_tool_auto_executes_and_is_audited(...) -> None: ...

async def test_restart_requires_approved_state(...) -> None: ...

async def test_denied_action_never_invokes_handler(...) -> None: ...

async def test_duplicate_execution_returns_saved_result_without_second_restart(...) -> None: ...

async def test_tool_timeout_marks_action_failed(...) -> None: ...
```

The duplicate test must assert `ServiceState.restart_count == 1` after two `execute(action_id)` calls.

- [ ] **Step 3: Run tests and observe missing registry/executor failures**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry.py tests/test_executor.py -q
```

- [ ] **Step 4: Implement argument models and deterministic handlers**

Use strict Pydantic models:

```python
class ServiceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: Literal["payments-api", "orders-api"]


class SearchLogsArgs(ServiceArgs):
    severity: Literal["info", "warning", "error"] = "error"
    limit: int = Field(default=20, ge=1, le=100)


class RestartServiceArgs(ServiceArgs):
    reason: str = Field(min_length=5, max_length=240)
```

Handlers return JSON-serializable dictionaries. `search_logs` returns deterministic records keyed by service health. `restart_service` changes health to `healthy`, increments `restart_count`, and sets `last_restart_at`. Do not implement a rotate-key handler.

- [ ] **Step 5: Implement the registry and executor protocol**

```python
@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    arguments_model: type[BaseModel]
    handler: Callable[[BaseModel, Session], Awaitable[dict[str, object]]] | None
```

`ToolExecutor.execute(action_id)` must:

1. Load action; reject missing actions.
2. Return stored result immediately if status is `succeeded`.
3. Permit execution only from `auto_approved` or `approved`.
4. Atomically claim action as `running`; if claim fails, reload and return/raise based on latest state.
5. Revalidate arguments with the registered Pydantic model.
6. Reject a missing handler.
7. Run with `asyncio.timeout(settings.tool_timeout_seconds)`.
8. Persist `succeeded` + result or `failed` + safe error.
9. Append `tool.started`, `tool.succeeded`, or `tool.failed` audit events.

- [ ] **Step 6: Verify race safety with an explicit concurrent test**

Add a test using `asyncio.gather(executor.execute(id), executor.execute(id))`. Assert one persisted success event and one service restart. If SQLite session sharing makes the test flaky, create independent sessions per executor call against a temporary file database; do not weaken the assertion.

- [ ] **Step 7: Verify and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry.py tests/test_executor.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
git add apps/api
git commit -m "feat: add guarded idempotent tool execution"
```

## Task 5: Implement Model Adapters and the Checkpointed Agent Loop

**Files:**

- Create: `apps/api/app/llm/__init__.py`
- Create: `apps/api/app/llm/base.py`
- Create: `apps/api/app/llm/mock.py`
- Create: `apps/api/app/llm/openai_compatible.py`
- Create: `apps/api/app/services/agent_loop.py`
- Create: `apps/api/app/services/runs.py`
- Create: `apps/api/tests/test_mock_llm.py`
- Create: `apps/api/tests/test_agent_loop.py`
- Create: `apps/api/tests/test_openai_adapter.py`

- [ ] **Step 1: Specify the provider-neutral model protocol in tests**

The internal response must not leak SDK objects:

```python
@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ModelTurn:
    assistant_message: dict[str, object]
    text: str | None
    tool_calls: tuple[ToolCall, ...]


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ModelTurn: ...
```

Test that the mock provider creates stable tool-call IDs and follows three scenarios based on request intent and tool results: healthy inspection, degraded restart, and forbidden key rotation.

- [ ] **Step 2: Write state-machine tests before implementation**

Minimum tests:

```python
async def test_healthy_run_completes_without_approval(...) -> None: ...

async def test_degraded_run_pauses_before_restart(...) -> None: ...

async def test_high_risk_tool_is_denied_without_execution(...) -> None: ...

async def test_unknown_tool_fails_closed_and_is_audited(...) -> None: ...

async def test_max_steps_marks_run_failed(...) -> None: ...

async def test_checkpoint_contains_messages_needed_for_resume(...) -> None: ...
```

For degraded service, assert run status `waiting_approval`, restart action status `pending_approval`, checkpoint JSON is non-empty, and restart count remains zero.

- [ ] **Step 3: Run tests and confirm missing implementation**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_mock_llm.py tests/test_agent_loop.py -q
```

- [ ] **Step 4: Implement the deterministic mock provider**

The mock provider must inspect structured tool results, not call counters alone:

- key-rotation intent → propose `rotate_api_key` once, then explain refusal after denied tool result;
- no health result → call `get_service_health`;
- degraded health with no logs → call `search_logs`;
- degraded health and logs but no restart result → call `restart_service`;
- restart success → call `get_service_health` again;
- healthy result → return final text.

Generate tool-call IDs from a deterministic digest of run-visible messages plus tool name so test snapshots remain stable.

- [ ] **Step 5: Implement OpenAI-compatible adapter with mocked HTTP tests**

`OpenAICompatibleProvider` receives `base_url`, `api_key`, and `model` via constructor. It uses `AsyncOpenAI(base_url=..., api_key=...)` and `chat.completions.create(model=..., messages=..., tools=...)`.

Tests replace the SDK client's `create` method with `AsyncMock` and prove:

- configured model/base URL are used;
- JSON tool arguments become dictionaries;
- malformed JSON becomes a typed `ModelProtocolError` without running a tool;
- API exceptions become a safe `ModelProviderError` that excludes the API key.

Do not make a network request in tests.

- [ ] **Step 6: Implement the Agent loop state machine**

`AgentRunner.start_run(user_request)` creates the run and delegates to `resume_run(run_id)`. `resume_run`:

```text
load checkpoint → mark running → call provider → persist assistant turn
    ├─ final text → mark completed → audit run.completed
    └─ tool calls → validate and persist each action
         ├─ auto approve → execute → append tool result → continue
         ├─ require approval → save checkpoint → mark waiting → return
         └─ deny → append denied tool result → continue
```

Process tool calls sequentially in the MVP so that one pending approval produces one unambiguous checkpoint. Increment and persist `step_count` before each provider call. Enforce `max_steps` and overall timeout. Store a structured final answer in the last assistant message; do not add a second final-answer column.

- [ ] **Step 7: Implement provider selection and background run service**

`RunService.create()` chooses provider from settings, creates a run synchronously, and schedules runner work through FastAPI `BackgroundTasks`. Unknown provider configuration raises a startup error. Tests can inject providers directly; no global mock switching inside production code.

- [ ] **Step 8: Run tests and commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_mock_llm.py tests/test_openai_adapter.py tests/test_agent_loop.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
git add apps/api
git commit -m "feat: add checkpointed tool-calling agent loop"
```

## Task 6: Add Atomic Approvals, REST APIs, and SSE Events

**Files:**

- Create: `apps/api/app/services/approvals.py`
- Create: `apps/api/app/services/events.py`
- Create: `apps/api/app/api/runs.py`
- Create: `apps/api/app/api/approvals.py`
- Create: `apps/api/app/api/audit.py`
- Create: `apps/api/app/api/policies.py`
- Create: `apps/api/tests/test_approvals.py`
- Create: `apps/api/tests/test_runs_api.py`
- Create: `apps/api/tests/test_audit_api.py`
- Create: `apps/api/tests/test_sse.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/schemas.py`

- [ ] **Step 1: Write approval transition tests**

Tests must demonstrate:

- approve changes only `pending_approval → approved`;
- deny changes only `pending_approval → denied`;
- approval executes or records denial, then invokes `AgentRunner.resume_run(run_id)`;
- two concurrent approvals result in one success and one `ApprovalConflictError`;
- duplicate requests do not execute the tool twice;
- actor and optional note are present in the audit payload.

- [ ] **Step 2: Write API contract tests**

Use dependency overrides for repositories/services. Verify exact status codes:

```text
POST /api/runs                              202
GET  /api/runs                              200
GET  /api/runs/{known}                      200
GET  /api/runs/{unknown}                    404
POST /api/approvals/{pending}/approve       200
POST /api/approvals/{already-decided}/...   409
POST /api/approvals/{unknown}/...           404
GET  /api/audit                             200
GET  /api/audit/export                      200 application/json attachment
GET  /api/policies                          200
```

Assert errors use `{ "error": { "code": "...", "message": "..." } }`.

- [ ] **Step 3: Write SSE event tests**

Test broker subscription independently from HTTP streaming:

```python
async def test_subscriber_receives_events_for_its_run_only() -> None: ...
async def test_slow_subscriber_does_not_block_publish() -> None: ...
async def test_unsubscribe_removes_queue() -> None: ...
```

Add one HTTP test that opens `/api/runs/{id}/events`, publishes `run.updated`, and asserts an SSE frame with `event: run.updated` and JSON `data:`. Ensure disconnect cleanup runs.

- [ ] **Step 4: Run the new tests and observe failure**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_approvals.py tests/test_runs_api.py tests/test_audit_api.py tests/test_sse.py -q
```

- [ ] **Step 5: Implement atomic approval service**

Approval service algorithm:

1. Load action or raise not found.
2. Conditional transition from `pending_approval` to `approved` or `denied`; if affected row count is zero, raise conflict.
3. Append `approval.approved` or `approval.denied` with actor/note.
4. For approval, call executor; append the saved tool result to checkpoint.
5. For denial, append a structured denied tool result without calling executor.
6. Transition run from `waiting_approval` to `running`.
7. Call `resume_run` outside the transition transaction.

If resume fails, preserve action outcome and mark run `failed`; never roll back an already executed external effect.

- [ ] **Step 6: Implement bounded in-process event broker**

Use one `asyncio.Queue[RunEvent]` per subscriber with max size 100. On full queues, drop the oldest event for that subscriber and enqueue the newest. Publish events after persisted state changes. SSE frames include an event name, JSON data and sequential event ID; send a comment heartbeat every 15 seconds.

Document that this broker is intentionally single-process for a local demo. Do not add Redis in the MVP.

- [ ] **Step 7: Implement routes and response schemas**

Use Pydantic response models rather than returning ORM objects directly. `RunDetailResponse` must include run fields, ordered actions, ordered audit events and derived `final_text`. `CreateRunRequest.user_request` must be 5–2000 characters. Approval body:

```python
class ApprovalRequest(BaseModel):
    actor: str = Field(default="local-user", min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
```

`GET /api/policies` derives its output from `ToolRegistry`; do not duplicate the risk table.

- [ ] **Step 8: Verify all backend behavior**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

- [ ] **Step 9: Commit the API layer**

```powershell
git add apps/api
git commit -m "feat: add approval workflow and live run api"
```

## Task 7: Build the Professional Local Control Console

**Files:**

- Create: `apps/web/src/types.ts`
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/hooks/useRunEvents.ts`
- Create: `apps/web/src/components/AppShell.tsx`
- Create: `apps/web/src/components/StatusBadge.tsx`
- Create: `apps/web/src/components/RunTimeline.tsx`
- Create: `apps/web/src/components/ApprovalCard.tsx`
- Create: `apps/web/src/components/EmptyState.tsx`
- Create: `apps/web/src/pages/RunsPage.tsx`
- Create: `apps/web/src/pages/RunDetailPage.tsx`
- Create: `apps/web/src/pages/PoliciesPage.tsx`
- Create: `apps/web/src/pages/AuditPage.tsx`
- Create: `apps/web/src/test/setup.ts`
- Create: `apps/web/src/components/ApprovalCard.test.tsx`
- Create: `apps/web/src/pages/RunsPage.test.tsx`
- Create: `apps/web/src/pages/RunDetailPage.test.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/vite.config.ts`

- [ ] **Step 1: Define TypeScript contracts matching API schemas**

Use string unions matching backend enum values exactly. Define `AgentRun`, `ToolAction`, `AuditEvent`, `RunDetail`, `PolicyView`, `RunEvent`, `CreateRunRequest`, and `ApprovalRequest`. Do not use `any`; JSON payloads use `unknown` plus narrow rendering helpers.

- [ ] **Step 2: Write API client and component tests first**

Mock `fetch` and cover:

- non-2xx responses become typed `ApiError(code, message, status)`;
- Runs page submits a prompt, displays the created run, and navigates to detail;
- approval card shows tool, risk, reason and formatted arguments;
- approve/deny buttons disable while one request is pending;
- a `409` displays “This action was already decided” and triggers a detail refresh;
- run detail renders states and does not render fields named `api_key` as raw values.

Run:

```powershell
Set-Location apps/web
npm test -- --run
```

Expected: FAIL because pages/components are missing.

- [ ] **Step 3: Implement the typed API client**

Expose:

```typescript
export const api = {
  createRun(input: CreateRunRequest): Promise<AgentRun>,
  listRuns(): Promise<AgentRun[]>,
  getRun(id: string): Promise<RunDetail>,
  approveAction(id: string, input: ApprovalRequest): Promise<ToolAction>,
  denyAction(id: string, input: ApprovalRequest): Promise<ToolAction>,
  listPolicies(): Promise<PolicyView[]>,
  listAudit(filters: AuditFilters): Promise<AuditEvent[]>,
  auditExportUrl(filters: AuditFilters): string,
};
```

Read only `VITE_API_BASE_URL`, defaulting to `http://localhost:8000`. Do not expose backend LLM configuration.

- [ ] **Step 4: Implement routing and the application shell**

Routes:

```text
/                RunsPage
/runs/:runId     RunDetailPage
/policies        PoliciesPage
/audit           AuditPage
```

App shell includes AgentGate wordmark, navigation, `Local Demo` badge, provider label returned from API metadata, and backend connectivity indicator. Use semantic `<nav>`, `<main>`, `<table>`, `<button>` and visible focus states.

- [ ] **Step 5: Implement Runs and Run detail pages**

Runs page contains a professional single-purpose task composer with the two demo prompts available as example chips, followed by a run table. Disable submission until the prompt has at least five characters.

Run detail:

- fetches initial detail;
- connects `EventSource` to the run SSE URL;
- refetches detail on persisted state events;
- backs off and shows a reconnecting state on SSE errors;
- closes EventSource on unmount;
- renders timeline events in chronological order;
- shows the approval card only for `pending_approval` actions;
- shows the final answer when completed and a safe error panel when failed.

- [ ] **Step 6: Implement Policies and Audit pages**

Policies renders a four-row risk table from API data, including readable policy rationale. Audit provides run ID, actor and event type filters, expandable payload, timestamp, and an Export JSON link. Empty and loading states must preserve page layout.

- [ ] **Step 7: Apply the visual system**

In `styles.css`, define CSS custom properties for neutral surfaces, text, border, accent, low/medium/high risk, spacing and radii. Required quality bar:

- desktop layout works at 1440×900;
- responsive layout remains usable at 390×844;
- no horizontal overflow;
- status is communicated by text plus color, never color alone;
- body text contrast meets WCAG AA;
- animations respect `prefers-reduced-motion`;
- approval controls remain visible without opening raw JSON.

Avoid gradients, glassmorphism and generic chat bubbles. The product should read as an operations console.

- [ ] **Step 8: Run frontend verification**

```powershell
npm test -- --run
npm run lint
npm run typecheck
npm run build
```

Expected: all tests pass, zero lint/type errors, production build succeeds.

- [ ] **Step 9: Commit the console**

```powershell
git add apps/web
git commit -m "feat: build agent action control console"
```

## Task 8: Add Deterministic Agent Evals and Browser E2E

**Files:**

- Create: `apps/api/app/evals/__init__.py`
- Create: `apps/api/app/evals/cases.py`
- Create: `apps/api/app/evals/graders.py`
- Create: `apps/api/app/evals/runner.py`
- Create: `apps/api/tests/test_evals.py`
- Create: `apps/web/playwright.config.ts`
- Create: `apps/web/e2e/approval-flow.spec.ts`
- Modify: `apps/web/package.json`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Write grader tests before the eval runner**

Define grader results as `{name, passed, score, message}`. Test four graders:

- `OutcomeGrader`: expected final run/service state;
- `TrajectoryGrader`: required and forbidden tool names in order;
- `PolicyComplianceGrader`: every execution had an allowed policy/action state;
- `IdempotencyGrader`: no idempotency key executed more than once.

Each failing test must assert a useful diagnostic message naming the violated expectation.

- [ ] **Step 2: Define six fixed eval cases**

Use exactly these cases:

```text
healthy_inspection
degraded_waits_for_restart_approval
approved_restart_recovers
denied_restart_has_no_side_effect
rotate_key_is_policy_denied
malformed_arguments_never_execute
```

Each case declares initial `ServiceState`, user request, deterministic approval decision if applicable, expected final status, required tools, forbidden executed tools, and expected restart count.

- [ ] **Step 3: Run tests and confirm the eval layer is missing**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_evals.py -q
```

- [ ] **Step 4: Implement eval runner and machine-readable output**

Runner creates a fresh temporary SQLite database per case, injects the mock provider, applies configured approval decisions, then evaluates persisted outcomes and traces. CLI behavior:

```powershell
.\.venv\Scripts\python.exe -m app.evals.runner
```

It prints a compact table, writes `eval-results.json`, and exits non-zero if any grader fails. Add `eval-results.json` to `.gitignore`.

- [ ] **Step 5: Write the browser approval-flow test first**

Playwright test must:

1. open Runs;
2. submit the degraded-service demo prompt;
3. wait for `Waiting approval`;
4. verify `restart_service`, `Medium risk`, arguments and reason are visible;
5. click Approve once;
6. wait for `Completed`;
7. assert timeline contains approval and successful tool execution;
8. navigate to Audit and find the run;
9. confirm no raw API key appears anywhere.

Use the backend mock provider and seeded database. Configure Playwright `webServer` commands to launch API on port 8000 and Vite on 5173, reusing neither existing server in CI.

- [ ] **Step 6: Run E2E and fix only deterministic synchronization issues**

```powershell
Set-Location apps/web
npx playwright install chromium
npm run test:e2e
```

Use role/text locators and event-driven waits. Do not add fixed sleeps.

- [ ] **Step 7: Add eval and E2E to CI**

CI order:

1. backend lint/typecheck/unit tests;
2. deterministic eval runner;
3. frontend lint/typecheck/unit tests/build;
4. Playwright Chromium E2E with mock provider.

Upload Playwright report only on failure. CI must not require `.env` or live credentials.

- [ ] **Step 8: Verify and commit**

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.evals.runner
Set-Location ..\web
npm test -- --run
npm run test:e2e
git add apps/api apps/web .github .gitignore
git commit -m "test: add deterministic agent evals and e2e"
```

## Task 9: Package, Document, and Rehearse the Interview Demo

**Files:**

- Create: `apps/api/Dockerfile`
- Create: `apps/web/Dockerfile`
- Create: `apps/web/nginx.conf`
- Create: `scripts/start-local.ps1`
- Create: `scripts/stop-local.ps1`
- Create: `scripts/verify.ps1`
- Create: `docs/architecture.md`
- Create: `docs/demo.md`
- Modify: `compose.yaml`
- Modify: `README.md`

- [ ] **Step 1: Write verification-script acceptance tests as executable checks**

`scripts/verify.ps1` must stop on first failure and run, from repository root:

```powershell
$ErrorActionPreference = "Stop"

Push-Location apps/api
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.evals.runner
Pop-Location

Push-Location apps/web
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run test:e2e
Pop-Location
```

Run it once before adding missing packaging and record only actual failures; do not claim success yet.

- [ ] **Step 2: Add Docker packaging**

Backend image runs Uvicorn on `0.0.0.0:8000` as a non-root user and mounts `/app/data` for SQLite. Frontend uses a multi-stage Node build and serves static assets with nginx on port 80; nginx proxies `/api`, `/health`, and SSE requests to `api:8000` with buffering disabled for SSE.

`compose.yaml` defines:

- `api`, with health check and `./data:/app/data`;
- `web`, dependent on healthy API, exposed at `http://localhost:5173`;
- environment loaded from `.env` without embedding defaults that look like secrets.

Validate configuration:

```powershell
docker compose config
docker compose build
docker compose up -d
Invoke-RestMethod http://localhost:8000/health
Invoke-WebRequest http://localhost:5173 -UseBasicParsing
docker compose down
```

- [ ] **Step 3: Add native local scripts**

`start-local.ps1` must:

- verify `.env` exists or copy `.env.example` and print that the user must set a rotated key for live mode;
- accept `-Provider mock|openai_compatible`, default `mock`;
- start API and Web in hidden child processes;
- write only child PIDs to `.agentgate/api.pid` and `.agentgate/web.pid`;
- poll `/health` for up to 30 seconds;
- print `http://localhost:5173` when ready.

`stop-local.ps1` reads only the two known PID files, verifies each process command line belongs to AgentGate before stopping it, then removes those PID files. It must not kill all Python or Node processes.

- [ ] **Step 4: Write architecture documentation**

`docs/architecture.md` must include:

- context and component diagram;
- run and action state machines;
- approval sequence from model proposal through resume;
- transaction/idempotency boundaries;
- why SSE, SQLite, direct OpenAI SDK and a single Agent were selected;
- local-demo limitations and production evolution path.

Use Mermaid diagrams that GitHub renders. The approval sequence must show Browser → API → Policy → DB → Human → Executor → AgentRunner → LLM.

- [ ] **Step 5: Write a deterministic 3–5 minute demo script**

`docs/demo.md` exact flow:

1. 20 seconds: state problem and show policy page.
2. 60 seconds: submit degraded service prompt and narrate read-only auto approvals.
3. 45 seconds: inspect pending restart card and approve.
4. 40 seconds: show resumed run and healthy outcome.
5. 30 seconds: submit rotate-key prompt and show direct denial.
6. 40 seconds: filter audit trail and explain idempotency/secret redaction.
7. 30 seconds: show eval result and architecture diagram.

Include expected visible UI labels and a recovery instruction for every step using the mock provider. The demo must not depend on live model behavior.

- [ ] **Step 6: Rewrite README for interview scanning**

README order:

1. product name + one-sentence value proposition;
2. one polished screenshot or short local GIF;
3. “Why this exists” and three differentiators;
4. architecture diagram;
5. 60-second quick start in mock mode;
6. live OpenAI-compatible configuration;
7. safety model and approval state machine;
8. test/eval commands and sample summary;
9. project structure;
10. production evolution;
11. tradeoffs and limitations.

Do not include unverified benchmark numbers, fabricated users or production claims. Label screenshots as local demo.

- [ ] **Step 7: Run the live provider smoke test without recording secrets**

First rotate the API key that was previously pasted into chat. Put the new value only in `.env`, set `AGENTGATE_LLM_PROVIDER=openai_compatible`, then start locally and submit the healthy inspection prompt.

Verify:

- provider returns a parseable tool call;
- base URL and model configuration are accepted;
- a read-only tool executes;
- run completes or exposes a safe provider error;
- terminal, API responses and audit export do not contain the key.

If the provider endpoint uses a protocol variant not supported by `chat.completions`, document the observed HTTP/status error and add a provider-specific adapter in a separate commit; do not weaken the provider-neutral core or guess request fields.

- [ ] **Step 8: Run final verification matrix**

```powershell
.\scripts\verify.ps1
docker compose config
docker compose build
git diff --check
git status --short
```

Then run the entire `docs/demo.md` script in a clean browser profile using mock mode. Confirm the six eval cases pass and restart count stays one after duplicate approval testing.

- [ ] **Step 9: Scan for secrets and unfinished markers**

```powershell
rg -n --hidden --glob '!.git/**' --glob '!node_modules/**' --glob '!*.db' "ark-[A-Za-z0-9-]+|Bearer\s+[A-Za-z0-9._-]+|TODO|TBD|FIXME|localhost:[0-9]+/.*api_key"
git ls-files .env data
```

Expected: no credential matches, no unfinished markers, `.env` and database files absent from tracked files. The string `your_api_key_here` is permitted only in `.env.example` and documentation that explicitly identifies it as non-secret sample text.

- [ ] **Step 10: Commit the interview-ready packaging**

```powershell
git add README.md docs scripts compose.yaml apps/api/Dockerfile apps/web/Dockerfile apps/web/nginx.conf
git commit -m "docs: package interview-ready local demo"
```

## Final Acceptance Checklist

- [ ] A fresh clone can start in mock mode without any API key.
- [ ] The live provider reads credentials only from backend environment variables.
- [ ] `get_service_health` and `search_logs` auto-execute as low-risk read-only tools.
- [ ] `restart_service` always pauses for approval before execution.
- [ ] `rotate_api_key` is denied and has no handler side effect.
- [ ] Approve and deny both resume the persisted Agent run.
- [ ] Duplicate approval/execution cannot increment restart count more than once.
- [ ] Invalid and unknown tools fail closed.
- [ ] Audit payloads recursively redact sensitive keys.
- [ ] Runs, Run detail, Policies and Audit views work at desktop and mobile widths.
- [ ] SSE updates the run detail without manual refresh and cleans up on disconnect.
- [ ] All six deterministic eval cases pass.
- [ ] Backend unit/API tests, frontend tests and Playwright E2E pass.
- [ ] `docker compose up --build` serves the complete local demo.
- [ ] README and demo script make no fabricated production claims.
- [ ] The repository contains no search, RAG, intelligence collection or report-generation feature.

## Post-MVP Upgrade Route

Keep these as clearly separated future milestones; do not pull them into the 3–5 day build.

### V1.1 — Stronger policy authoring

- Declarative YAML/JSON policies with schema validation and hot reload.
- Argument-aware rules such as service/environment allowlists and business-hour constraints.
- Policy simulation page that explains which rule matched before activation.
- Regression fixtures proving new rules do not silently broaden permissions.

### V1.2 — Production-grade execution

- PostgreSQL with row-level locking and migration tooling.
- Redis Streams or durable queue for multi-process event delivery and resumable workers.
- Outbox pattern for atomic state/event publication.
- Expiring approvals, cancellation, retry budgets and circuit breakers.

### V1.3 — Identity and enterprise controls

- OIDC login, RBAC, approver groups and separation of duties.
- Cryptographically signed approval records and tamper-evident audit export.
- Per-agent/tool/environment policy scopes.
- OpenTelemetry traces correlated across model, policy and tool spans.

### V1.4 — Interoperability and evaluation

- MCP-compatible tool adapter while retaining the allowlist and policy boundary.
- Replay sandbox that reruns historical traces against changed policies without side effects.
- Dataset/version tracking, trajectory diff and cost/latency graders.
- Shadow mode that observes proposed actions before enforcement is enabled.

The upgrade route remains infrastructure-focused. It must not turn AgentGate into another research, intelligence, customer-service or content-generation application.
