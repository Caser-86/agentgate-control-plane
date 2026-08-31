# 阶段 0：可靠底座实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox ('- [ ]') syntax for tracking.

**Goal:** 将当前演示从 SQLite、请求内后台任务和进程内事件代理，升级为可在单台 Windows 主机上恢复运行的 PostgreSQL + 持久化队列 + 认证控制平面，并提供原生 Worker 协议骨架。

**Architecture:** 保留现有 FastAPI/React 技术栈，将 API 变为只负责认证、状态和任务编排的控制平面；PostgreSQL 保存所有领域状态、租约和 Outbox；独立的控制 Worker 处理 AgentRun 等容器内任务；原生 Windows Worker 只负责后续需要宿主机权限的受限连接器。本阶段不增加真实服务重启、文件写入或任意脚本能力。

**Tech Stack:** Python 3.11、FastAPI、SQLModel/SQLAlchemy、Alembic、psycopg 3、PostgreSQL、React/Vite、TypeScript、pytest、Ruff、mypy、Playwright、Windows DPAPI/pywin32。

**Spec:** [docs/superpowers/specs/2026-08-31-agentgate-local-governance-platform-design.md](../specs/2026-08-31-agentgate-local-governance-platform-design.md)

## Global Constraints

- 适用范围：单台 Windows 主机、单用户、仅本机访问。
- Docker Compose 运行 web、api、scheduler、postgres；高权限能力只放在原生 Windows Worker。
- PostgreSQL 是唯一事实来源；不得用 SQLModel.metadata.create_all() 代替生产迁移。
- 所有状态变更必须先持久化；SSE 只负责通知，REST 和数据库负责事实读取。
- 只读检查可自动执行；重启、文件变更和固定脚本必须审批；任意 Shell、任意 PowerShell、任意网络请求和密钥操作永久拒绝。
- 模型、大模型客户端、MCP 和 Codex 都是可选接入端；禁用模型后监控和控制平面仍必须启动。
- API 不直接操作宿主机；Worker 只通过 localhost API 轮询、心跳和回报。
- 任何高风险动作都必须绑定规范化参数摘要、策略版本和有效审批。
- 不覆盖或重置工作区中已有的用户改动；每个任务只暂存自己的文件。
- Windows PowerShell 测试前端时使用 npm.cmd，避免执行策略阻止 npm.ps1。
- 每个任务先写失败测试，再写最小实现；任务完成后运行该任务的专用测试并提交独立 commit。

---

## 文件结构与边界

执行前先按下面的职责创建或修改文件；不要把认证、队列、Worker 协议和旧 AgentRunner 再堆进单一模块。

### 数据库与配置

- Modify: apps/api/pyproject.toml — 增加 Alembic、PostgreSQL 驱动、认证和 Windows Worker 依赖。
- Modify: apps/api/app/config.py — 数据库、认证、租约、Outbox 和本机网络配置。
- Modify: apps/api/app/db.py — engine/session 工厂和迁移检查，不再负责生产建表。
- Modify: apps/api/app/main.py — 启动检查、认证中间件、路由和 CORS。
- Modify: apps/api/Dockerfile — 迁移/服务启动边界和非 root 运行。
- Modify: compose.yaml — PostgreSQL、控制 Worker、健康检查和 localhost 端口。
- Create: apps/api/alembic.ini、apps/api/migrations/env.py、apps/api/migrations/script.py.mako、apps/api/migrations/versions/0001_legacy_schema.py。

### 控制平面领域和可靠队列

- Modify: apps/api/app/models.py — 兼容现有 Run/Action/Audit 模型并注册新模型。
- Create: apps/api/app/control/__init__.py、apps/api/app/control/enums.py、apps/api/app/control/models.py、apps/api/app/control/repositories.py、apps/api/app/control/service.py。
- Modify: apps/api/app/repositories.py — 仅保留旧演示兼容仓储，并复用新事务接口。

### 认证与 API

- Create: apps/api/app/auth/models.py、apps/api/app/auth/security.py、apps/api/app/auth/dependencies.py。
- Create: apps/api/app/api/auth.py、apps/api/app/api/worker.py、apps/api/app/api/v1.py。
- Modify: apps/api/app/schemas.py、apps/api/app/api/runs.py、apps/api/app/api/approvals.py。
- Create: apps/api/app/processes/control_worker.py — 独立进程执行持久化控制任务。
- Modify: apps/api/app/services/runs.py、apps/api/app/services/approvals.py、apps/api/app/services/events.py。

### 原生 Worker

- Create: apps/worker/pyproject.toml、apps/worker/agentgate_worker/__init__.py、apps/worker/agentgate_worker/client.py、apps/worker/agentgate_worker/journal.py、apps/worker/agentgate_worker/vault.py、apps/worker/agentgate_worker/main.py。
- Create: apps/worker/tests/test_client.py、apps/worker/tests/test_journal.py、apps/worker/tests/test_vault.py。
- 阶段 0 只提供控制协议、心跳、租约和安全自检能力；Windows 服务安装器和真实连接器在阶段 3/4 实现。

### 前端与测试

- Create: apps/web/src/auth/AuthProvider.tsx、apps/web/src/pages/LoginPage.tsx。
- Modify: apps/web/src/api/client.ts、apps/web/src/App.tsx、apps/web/src/hooks/useRunEvents.ts。
- Create: apps/web/src/auth/AuthProvider.test.tsx、apps/web/src/pages/LoginPage.test.tsx、apps/web/e2e/auth-and-queue.spec.ts。
- Create/Modify: apps/api/tests/test_migrations.py、test_control_queue.py、test_auth_api.py、test_worker_protocol.py、test_outbox.py、test_durable_runs.py、test_security_regressions.py。
- Modify: README.md、docs/architecture.md、scripts/start-local.ps1、scripts/stop-local.ps1；新增 scripts/migrate-local.ps1、scripts/setup-local.ps1、scripts/verify-foundation.ps1。

---

### Task 0: 记录现有基线并保护工作区

**Files:**

- No file changes.
- Read only: current Git status, existing test configuration, and the approved spec.

**Interfaces:**

- Produces: baseline test commands and a clean list of unrelated user changes for later verification.

- [ ] **Step 1: Record the current worktree state**

Run:

~~~powershell
git status --short
git diff --stat
git log -1 --oneline
~~~

Expected: the existing modified frontend/backend files are listed; do not reset, stash, checkout, or delete them.

- [ ] **Step 2: Run the backend baseline**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

Expected: record pass/fail counts. If a baseline failure is caused by an existing user change, keep it documented and do not “fix” unrelated files in this plan.

- [ ] **Step 3: Run the frontend baseline with the Windows-safe npm executable**

Run:

~~~powershell
Set-Location ..\web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
~~~

Expected: record pass/fail counts and keep the prior PowerShell npm.ps1 execution-policy workaround out of the product implementation.

- [ ] **Step 4: Commit no code and preserve the baseline report**

Do not create a generated report in the repository. Put the observed baseline in the implementation task notes and verify at the end that the pre-existing git status entries remain unchanged except for planned files.

---

### Task 1: PostgreSQL、Alembic 和可验证启动

**Files:**

- Modify: apps/api/pyproject.toml
- Modify: apps/api/app/config.py
- Modify: apps/api/app/db.py
- Modify: apps/api/app/main.py
- Modify: apps/api/Dockerfile
- Modify: compose.yaml
- Create: apps/api/alembic.ini
- Create: apps/api/migrations/env.py
- Create: apps/api/migrations/script.py.mako
- Create: apps/api/migrations/versions/0001_legacy_schema.py
- Test: apps/api/tests/test_database_config.py
- Test: apps/api/tests/test_migrations.py

**Interfaces:**

- Consumes: existing SQLModel tables agent_runs, tool_actions, audit_events, service_states.
- Produces: create_db_engine(url: str) -> Engine, get_session() -> Generator[Session, None, None], and an Alembic database with a recorded head revision.

- [ ] **Step 1: Add failing configuration and migration tests**

Create tests with these assertions:

~~~python
def test_postgres_url_is_the_compose_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTGATE_DATABASE_URL", "postgresql+psycopg://agentgate:test@postgres/agentgate")
    assert get_settings().database_url.startswith("postgresql+psycopg://")


def test_migration_head_creates_legacy_tables(postgres_url: str) -> None:
    upgrade_to_head(postgres_url)
    assert inspector.has_table("agent_runs")
    assert inspector.has_table("tool_actions")
    assert inspector.has_table("audit_events")
~~~

The Postgres fixture must run against the Compose database or a disposable test database and must never use the production data volume.

- [ ] **Step 2: Run the focused tests to verify they fail for the old SQLite/create-all path**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_database_config.py tests/test_migrations.py -q
~~~

Expected: FAIL because the current settings default to SQLite and no Alembic environment exists.

- [ ] **Step 3: Add database dependencies and explicit settings**

Add these dependency ranges to pyproject.toml:

~~~toml
"alembic>=1.15,<2",
"psycopg[binary]>=3.2,<4",
"argon2-cffi>=23.1,<26",
~~~

Add settings with these defaults:

~~~python
database_url: str = "postgresql+psycopg://agentgate:agentgate@postgres:5432/agentgate"
database_migration_required: bool = True
worker_lease_seconds: int = 30
outbox_batch_size: int = 100
auth_bootstrap_token_file: str = "/app/data/bootstrap-token"
~~~

Keep a test-only SQLite engine factory for unit tests, but never select it through the production Compose default.

- [ ] **Step 4: Create the baseline Alembic environment and migration**

migrations/env.py must import every SQLModel module present at the current task before reading SQLModel.metadata; Task 2 must extend that import list with the new control models. The baseline migration must create the four existing tables with their current columns, indexes, unique idempotency constraint and enum/string representations. Do not call SQLModel.metadata.create_all() from the API lifespan.

Expose a small helper used by tests and startup checks:

~~~python
def upgrade_to_head(database_url: str) -> None:
    """Run Alembic upgrade head for an explicit database URL."""
~~~

- [ ] **Step 5: Make startup fail clearly when migrations are missing**

Change app.main.lifespan to verify the migration head before seeding any demo-only state. seed_demo_state() must run only when AGENTGATE_ENV=development and AGENTGATE_SEED_DEMO=true; production-like Compose startup must not recreate demo rows.

Use an API startup error with code database_schema_not_ready when the revision is missing. Keep the existing non-root Docker user and add a Compose postgres service with a healthcheck, a named data volume, and no published host port.

- [ ] **Step 6: Run focused tests and static checks**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_database_config.py tests/test_migrations.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

Expected: PASS. Commit:

~~~powershell
git add apps/api/pyproject.toml apps/api/app/config.py apps/api/app/db.py apps/api/app/main.py apps/api/Dockerfile compose.yaml apps/api/alembic.ini apps/api/migrations apps/api/tests/test_database_config.py apps/api/tests/test_migrations.py
git commit -m "feat: add postgres migrations and startup checks"
~~~

---

### Task 2: 持久化任务、租约、Outbox 和通用审计实体

**Files:**

- Modify: apps/api/app/models.py
- Create: apps/api/app/control/__init__.py
- Create: apps/api/app/control/enums.py
- Create: apps/api/app/control/models.py
- Create: apps/api/app/control/repositories.py
- Create: apps/api/app/control/service.py
- Modify: apps/api/app/repositories.py
- Modify: apps/api/app/services/audit.py
- Create: apps/api/migrations/versions/0002_control_plane_tables.py
- Test: apps/api/tests/test_control_queue.py
- Test: apps/api/tests/test_outbox.py
- Test: apps/api/tests/test_control_audit.py

**Interfaces:**

- Consumes: SQLAlchemy session factory and migration head from Task 1.
- Produces these stable operations for later tasks:

~~~python
def enqueue_task(
    session: Session,
    *,
    kind: TaskKind,
    payload: dict[str, object],
    idempotency_key: str,
    capability: str,
    run_id: UUID | None = None,
) -> ControlTask

def claim_next_task(
    session: Session,
    *,
    worker_id: UUID,
    capabilities: set[str],
    now: datetime,
) -> ControlTask | None

def renew_task_lease(
    session: Session,
    *,
    task_id: UUID,
    worker_id: UUID,
    now: datetime,
) -> ControlTask

def complete_task(
    session: Session,
    *,
    task_id: UUID,
    worker_id: UUID,
    outcome: TaskOutcome,
    result: dict[str, object],
) -> ControlTask

def append_outbox_event(
    session: Session,
    *,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    payload: dict[str, object],
) -> OutboxEvent
~~~

- [ ] **Step 1: Write failing state and concurrency tests**

Cover the following exact cases:

~~~python
def test_duplicate_idempotency_key_returns_one_task(session: Session) -> None:
    first = enqueue_task(session, kind=TaskKind.AGENT_RUN, payload={}, idempotency_key="x", capability="control.run")
    second = enqueue_task(session, kind=TaskKind.AGENT_RUN, payload={}, idempotency_key="x", capability="control.run")
    assert second.id == first.id


def test_expired_lease_can_be_reclaimed_by_another_worker(postgres_session_pair) -> None:
    first = claim_next_task(session_a, worker_id=worker_a, capabilities={"control.run"}, now=t0)
    assert first is not None
    reclaimed = claim_next_task(session_b, worker_id=worker_b, capabilities={"control.run"}, now=t0 + lease_delta)
    assert reclaimed is not None
    assert reclaimed.id == first.id


def test_outbox_cursor_is_monotonic(session: Session) -> None:
    append_outbox_event(session, event_type="task.updated", resource_type="task", resource_id=rid, payload={})
    events = list(read_outbox_after(session, cursor=0, limit=10))
    assert events[0].sequence > 0
~~~

Also cover the generic audit path with an event that has no AgentRun: the persisted row must keep resource_type/resource_id, actor and a redacted payload while leaving legacy run_id nullable.

- [ ] **Step 2: Run the focused tests to verify the new interfaces are absent**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_control_queue.py tests/test_outbox.py -q
~~~

Expected: FAIL with missing control models/repositories.

- [ ] **Step 3: Add the control-plane models and migrations**

Create ControlTask with fields: UUID id, TaskKind kind, TaskStatus status, JSON payload, capability, unique idempotency key, attempts, available time, lease owner, lease expiry, created/updated/started/completed timestamps, result JSON, error class and side-effect certainty.

Create WorkerRegistration with UUID id, name, version, capability JSON, token digest, status, last heartbeat, created/updated timestamps. Create OutboxEvent with a database-generated monotonic bigint sequence, resource fields, JSON payload, published timestamp and created timestamp.

Extend the audit representation so generic events can have nullable run_id, nullable action_id, resource_type and resource_id; existing legacy run records remain readable.

Add an AuditService method that accepts either a run/action context or a generic resource context, redacts the payload before persistence, appends one AuditEvent and one OutboxEvent in the caller's transaction, and never requires a fabricated AgentRun ID.

- [ ] **Step 4: Implement atomic queue transitions**

claim_next_task() must select only queued tasks with available_at <= now, or expired leased tasks whose kind is safe to retry. Use a PostgreSQL row lock/conditional update so two workers cannot claim the same task. complete_task() must require the current lease owner and transition only from running/leased.

For an action with possible side effects, an expired lease transitions to manual_review, not back to queued. For read-only/control-plane tasks, an expired lease increments attempts and returns to queued with bounded backoff.

- [ ] **Step 5: Make business changes and Outbox events one transaction**

Add a service helper:

~~~python
def commit_with_outbox(
    session: Session,
    *,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    payload: dict[str, object],
) -> None:
    """Commit the current domain mutation and its notification atomically."""
~~~

No caller may publish a user-visible state event before this transaction commits.

- [ ] **Step 6: Run Postgres concurrency tests, static checks, and commit**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_control_queue.py tests/test_outbox.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

Expected: PASS. Commit:

~~~powershell
git add apps/api/app/models.py apps/api/app/control apps/api/app/repositories.py apps/api/migrations/versions/0002_control_plane_tables.py apps/api/tests/test_control_queue.py apps/api/tests/test_outbox.py
git commit -m "feat: add durable control task queue and outbox"
~~~

---

### Task 3: 单用户认证、会话、CSRF 和适配器令牌

**Files:**

- Create: apps/api/app/auth/models.py
- Create: apps/api/app/auth/security.py
- Create: apps/api/app/auth/dependencies.py
- Create: apps/api/app/api/auth.py
- Modify: apps/api/app/schemas.py
- Modify: apps/api/app/main.py
- Modify: apps/api/app/api/runs.py
- Modify: apps/api/app/api/approvals.py
- Modify: apps/api/app/api/audit.py
- Modify: apps/api/app/api/policies.py
- Create: apps/api/app/api/v1.py
- Create: apps/api/migrations/versions/0003_auth_tables.py
- Test: apps/api/tests/test_auth_api.py
- Test: apps/api/tests/test_auth_dependencies.py
- Test: apps/api/tests/test_v1_api.py
- Create: apps/web/src/auth/AuthProvider.tsx
- Create: apps/web/src/pages/LoginPage.tsx
- Modify: apps/web/src/api/client.ts
- Modify: apps/web/src/App.tsx
- Create: apps/web/src/auth/AuthProvider.test.tsx
- Create: apps/web/src/pages/LoginPage.test.tsx

**Interfaces:**

- Produces backend endpoints:

~~~text
GET  /api/auth/status
POST /api/auth/setup
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/csrf
POST /api/auth/tokens
DELETE /api/auth/tokens/{token_id}
~~~

- Produces dependencies require_operator(request) -> Operator and require_client_scope(scope) -> ClientIdentity.
- External adapter tokens can propose events/checks/actions but cannot approve, register Worker or modify policies.
- Produces protocol-neutral proposal endpoints POST /api/v1/events, POST /api/v1/checks and POST /api/v1/actions; these endpoints normalize input, apply the action registry and never accept a caller-supplied final decision.

- [ ] **Step 1: Write failing backend authentication tests**

Cover first-run setup, password hashing, cookie attributes, CSRF rejection, protected endpoints, logout invalidation and scoped token denial:

~~~python
def test_setup_requires_bootstrap_token_and_creates_one_operator(client, bootstrap_token):
    response = client.post("/api/auth/setup", json={"bootstrap_token": bootstrap_token, "password": "correct horse battery staple"})
    assert response.status_code == 201
    assert client.get("/api/auth/status").json()["authenticated"] is True


def test_state_change_without_csrf_is_rejected(authenticated_client):
    response = authenticated_client.post("/api/approvals/id/deny", json={"note": "no csrf"})
    assert response.status_code == 403


def test_propose_token_cannot_approve(client, propose_only_token):
    response = client.post("/api/approvals/id/approve", headers=propose_only_token, json={})
    assert response.status_code == 403
~~~

- [ ] **Step 2: Run auth tests to verify the unauthenticated current API is exposed**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_auth_api.py tests/test_auth_dependencies.py -q
~~~

Expected: FAIL because no operator/session/token models or protected dependency exists.

- [ ] **Step 3: Implement operator, opaque sessions and token hashes**

Create Operator, WebSession and ClientToken tables. Store only Argon2id password hashes and SHA-256 token digests. Store opaque random session IDs in an HttpOnly, SameSite=Strict cookie with Secure=false only for localhost HTTP development; make the setting explicit rather than inferred from the request.

On first startup with no operator, create a random bootstrap token in auth_bootstrap_token_file. POST /api/auth/setup must atomically consume it and refuse a second setup. The setup endpoint must never return the bootstrap token.

- [ ] **Step 4: Enforce authentication, scope and CSRF at the API boundary**

Require an authenticated operator for browser reads and all state changes. Require a header token with an explicit scope for external adapters. Require a CSRF token for every cookie-authenticated POST, PUT, PATCH and DELETE; compare exact configured Origin and reject missing/mismatched Origin.

Derive actor from the authenticated identity. Ignore and remove the current request-body actor as an authorization source; it may be retained only as a rejected compatibility field during migration.

- [ ] **Step 5: Add protocol-neutral v1 proposal endpoints**

Before wiring the frontend, add the protocol-neutral v1 endpoints. An event creates a durable observation/event record; a check creates a registered read-only task; an action validates the action type and target, then returns allow_auto, require_approval or deny from the policy engine. Unknown actions and malformed parameters return 403/422 without creating an executable task. Add test_v1_api.py cases for a valid proposal, an unknown action, an unregistered target and a propose-only token.

- [ ] **Step 6: Add the Chinese login flow**

AuthProvider must fetch /api/auth/status, redirect unauthenticated users to LoginPage, retain the CSRF token in memory, and send it in X-CSRF-Token. LoginPage must show Chinese labels for bootstrap setup, login failure, expired session and retry. The API client must convert 401, 403, and validation errors into stable error codes without displaying raw secrets.

- [ ] **Step 7: Run backend/frontend auth and v1 tests, then commit**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_auth_api.py tests/test_auth_dependencies.py tests/test_v1_api.py -q
Set-Location ..\web
npm.cmd test -- --run src/auth/AuthProvider.test.tsx src/pages/LoginPage.test.tsx
npm.cmd run typecheck
npm.cmd run lint
~~~

Expected: PASS. Commit:

~~~powershell
git add apps/api/app/auth apps/api/app/api/auth.py apps/api/app/api/v1.py apps/api/app/schemas.py apps/api/app/main.py apps/api/app/api/runs.py apps/api/app/api/approvals.py apps/api/app/api/audit.py apps/api/app/api/policies.py apps/api/migrations/versions/0003_auth_tables.py apps/api/tests/test_auth_api.py apps/api/tests/test_auth_dependencies.py apps/api/tests/test_v1_api.py apps/web/src/auth apps/web/src/pages/LoginPage.tsx apps/web/src/api/client.ts apps/web/src/App.tsx
git commit -m "feat: add local operator authentication and csrf"
~~~

---

### Task 4: 原生 Worker 注册、租约协议和本机执行日志

**Files:**

- Create: apps/api/app/api/worker.py
- Create: apps/api/app/services/worker_protocol.py
- Modify: apps/api/app/main.py
- Create: apps/api/migrations/versions/0004_worker_protocol.py
- Create: apps/worker/pyproject.toml
- Create: apps/worker/agentgate_worker/__init__.py
- Create: apps/worker/agentgate_worker/client.py
- Create: apps/worker/agentgate_worker/journal.py
- Create: apps/worker/agentgate_worker/vault.py
- Create: apps/worker/agentgate_worker/main.py
- Create: apps/worker/tests/test_client.py
- Create: apps/worker/tests/test_journal.py
- Create: apps/worker/tests/test_vault.py
- Test: apps/api/tests/test_worker_protocol.py

**Interfaces:**

- Produces API endpoints:

~~~text
POST /api/v1/worker/register
POST /api/v1/worker/heartbeat
POST /api/v1/worker/claim
POST /api/v1/worker/tasks/{task_id}/start
POST /api/v1/worker/tasks/{task_id}/complete
POST /api/v1/worker/tasks/{task_id}/report
~~~

- Produces Worker methods:

~~~python
register() -> WorkerIdentity
claim() -> TaskGrant | None
start(grant: TaskGrant) -> None
complete(grant: TaskGrant, result: dict[str, object]) -> None
recover_pending_reports() -> int
~~~

- [ ] **Step 1: Write failing protocol and journal tests**

Test registration, invalid token, capability filtering, lease owner checks, start authorization, result replay and local journal recovery:

~~~python
def test_worker_cannot_claim_without_registered_capability(api_client):
    response = api_client.post("/api/v1/worker/claim", json={"capabilities": ["host.restart"]})
    assert response.status_code == 403


def test_journal_replays_result_after_api_disconnect(tmp_path):
    journal = WorkerJournal(tmp_path / "journal.db")
    journal.record_started(task_id, request_digest, lease_expires_at)
    journal.record_result(task_id, {"status": "succeeded"})
    assert journal.pending_reports() == [(task_id, {"status": "succeeded"})]
~~~

- [ ] **Step 2: Run focused tests to verify the protocol is missing**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_worker_protocol.py -q
Set-Location ..\..\apps\worker
..\api\.venv\Scripts\python.exe -m pytest tests -q
~~~

Expected: FAIL because no Worker routes, client, journal or vault exists.

- [ ] **Step 3: Implement registration and scoped Worker identity**

Use the one-time enrollment token from Task 3. Store only its digest; after registration issue a distinct Worker token and show it once through the local setup command. Store Worker credentials in a DPAPI-protected file through win32crypt.CryptProtectData; unit-test the vault behind an injectable protector so non-Windows test runners can use a fake implementation.

The API must bind Worker requests to the registered Worker ID, token digest, protocol version and capability set. Worker requests cannot approve actions, change policies or submit arbitrary target paths.

- [ ] **Step 4: Implement claim/start/heartbeat/complete transitions**

claim calls claim_next_task() with the Worker capabilities. start must atomically transition the task and persist an execution grant containing task ID, request digest, Worker ID and expiry before a connector can run. complete must require the same Worker ID, task ID and digest.

Implement the Worker local journal with SQLite from the Python standard library. It stores only task identity, request digest, status, timestamps and already-redacted bounded results. It does not store passwords, API keys, full file contents or arbitrary command strings.

- [ ] **Step 5: Add a safe Worker self-check task**

Register only worker.self_check in this phase. It returns Worker version, protocol version and declared capabilities; it does not invoke a shell, Windows service, Docker, filesystem mutation or network target. Use it to validate the full register → claim → start → complete → report flow.

- [ ] **Step 6: Run protocol tests, type checks and commit**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_worker_protocol.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
Set-Location ..\..\apps\worker
..\api\.venv\Scripts\python.exe -m pytest tests -q
~~~

Expected: PASS. Commit:

~~~powershell
git add apps/api/app/api/worker.py apps/api/app/services/worker_protocol.py apps/api/app/main.py apps/api/migrations/versions/0004_worker_protocol.py apps/worker
git commit -m "feat: add native worker protocol foundation"
~~~

---

### Task 5: 用持久化 Outbox 替换内存事件代理

**Files:**

- Modify: apps/api/app/services/events.py
- Create: apps/api/app/services/outbox.py
- Create: apps/api/app/api/events.py
- Modify: apps/api/app/api/runs.py
- Modify: apps/api/app/main.py
- Modify: apps/web/src/hooks/useRunEvents.ts
- Modify: apps/web/src/api/client.ts
- Test: apps/api/tests/test_outbox_stream.py
- Test: apps/api/tests/test_sse.py
- Test: apps/web/src/api/client.test.ts
- Test: apps/web/src/pages/RunDetailPage.test.tsx

**Interfaces:**

- Produces read_events_after(cursor: int, resource_id: UUID | None, limit: int) -> list[OutboxEvent].
- Produces format_outbox_sse(event: OutboxEvent) -> str with id, event and JSON data.
- Keeps a compatibility endpoint GET /api/runs/{run_id}/events backed by the Outbox during migration.

- [ ] **Step 1: Write failing reconnect and ordering tests**

Test that a client disconnects after event 2 and reconnects with Last-Event-ID: 2, receiving event 3 onward; test that two API processes reading the same Outbox see the same event IDs; test that a missing run returns 404 without creating a subscription.

~~~python
def test_sse_reconnects_from_last_event_id(api_client, outbox_events):
    response = api_client.get("/api/runs/run-id/events", headers={"Last-Event-ID": "2"})
    assert response.status_code == 200
    assert "id: 3" in response.text
~~~

- [ ] **Step 2: Run event tests to verify the current broker loses history**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_sse.py tests/test_outbox_stream.py -q
~~~

Expected: the new durable-history assertions fail against the process-local EventBroker.

- [ ] **Step 3: Route domain events through the Outbox transaction**

Replace direct event_broker.publish() calls in run, approval and audit paths with append_outbox_event() in the same transaction that changes the run/action state. Keep event_to_sse() only as a serializer for durable events; remove the process-local counter and subscriber map from production code.

- [ ] **Step 4: Implement the durable SSE reader**

The endpoint must read existing rows first, then poll for new rows with a bounded database interval, emit a 15-second heartbeat, and close cleanly on client cancellation. Use Last-Event-ID and an explicit after query parameter; the smaller effective cursor wins only when both are valid integers. Redact payloads before serialization and cap each event payload.

- [ ] **Step 5: Update the frontend reconnect behavior**

useRunEvents must retain the last numeric event ID, reconnect after network errors with exponential backoff capped at 30 seconds, and refetch the run detail after reconnect. A stale or malformed event must not overwrite the REST status.

- [ ] **Step 6: Run backend/frontend event tests and commit**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_outbox_stream.py tests/test_sse.py -q
Set-Location ..\web
npm.cmd test -- --run src/api/client.test.ts src/pages/RunDetailPage.test.tsx
npm.cmd run typecheck
~~~

Expected: PASS. Commit:

~~~powershell
git add apps/api/app/services/events.py apps/api/app/services/outbox.py apps/api/app/api/events.py apps/api/app/api/runs.py apps/api/app/main.py apps/web/src/hooks/useRunEvents.ts apps/web/src/api/client.ts apps/api/tests/test_outbox_stream.py apps/api/tests/test_sse.py apps/web/src/api/client.test.ts apps/web/src/pages/RunDetailPage.test.tsx
git commit -m "feat: make run events durable and reconnectable"
~~~

---

### Task 6: 移除请求内后台任务并接入持久化控制 Worker

**Files:**

- Create: apps/api/app/processes/__init__.py
- Create: apps/api/app/processes/control_worker.py
- Modify: apps/api/app/api/runs.py
- Modify: apps/api/app/services/runs.py
- Modify: apps/api/app/api/approvals.py
- Modify: apps/api/app/services/approvals.py
- Modify: apps/api/app/services/agent_loop.py
- Modify: apps/api/app/services/executor.py
- Modify: compose.yaml
- Test: apps/api/tests/test_durable_runs.py
- Test: apps/api/tests/test_approval_queue.py
- Test: apps/api/tests/test_control_worker.py

**Interfaces:**

- RunService.create(user_request: str, source: ClientIdentity) -> AgentRun returns a queued run and enqueues one agent_run_resume task.
- ApprovalService.decide(action_id: UUID, decision: ApprovalDecision, operator: Operator, note: str | None) -> ToolAction persists the decision and enqueues one resume task; it does not call AgentRunner or ToolExecutor in the request.
- ControlWorker.run_once() -> int claims and executes at most one control-plane task using a fresh database session.
- ControlWorker.run_forever() -> None runs the durable claim loop and exits non-zero on an unrecoverable configuration error.

- [ ] **Step 1: Write failing durable-run and approval tests**

Cover these exact transitions:

~~~python
def test_create_run_returns_queued_and_enqueues_one_resume_task(authenticated_client, session):
    response = authenticated_client.post("/api/runs", json={"user_request": "inspect service health"})
    assert response.status_code == 202
    run_id = response.json()["id"]
    task = only_task(session, kind="agent_run_resume", run_id=run_id)
    assert task.status == "queued"


def test_approval_does_not_execute_inside_http_request(approved_action_client, session, mocker):
    execute = mocker.patch("app.services.executor.ToolExecutor.execute")
    response = approved_action_client.post("/api/approvals/action-id/approve", json={"note": "approved"})
    assert response.status_code == 200
    execute.assert_not_called()
    assert one_task(session, kind="agent_run_resume").status == "queued"
~~~

- [ ] **Step 2: Run the focused tests to verify the current BackgroundTasks/direct-resume behavior**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_durable_runs.py tests/test_approval_queue.py tests/test_control_worker.py -q
~~~

Expected: FAIL because RunService adds BackgroundTasks and ApprovalService directly executes/resumes the agent.

- [ ] **Step 3: Make run creation durable and request-scoped**

Remove BackgroundTasks from POST /api/runs. Create the run, initial checkpoint, audit event and agent_run_resume task in one transaction. Return 202 with queued status. The HTTP dependency session must be closed before any provider call starts.

- [ ] **Step 4: Make approvals conditional and asynchronous**

In one transaction, require pending_approval, bind the authenticated operator, note, action parameter digest and active policy version, transition the action, append the audit event and enqueue one resume task. A duplicate approval returns 409 and creates no second task. A denied action produces a persisted safe result without invoking a handler.

- [ ] **Step 5: Implement the isolated control Worker loop**

control_worker.py must create a new SQLModel session per claimed task, run the existing provider-neutral AgentRunner only for agent_run_resume, and close the session after completion. It must not use FastAPI BackgroundTasks, request objects, process-local event state or a session captured from an API request.

For the legacy simulated ToolExecutor, keep handler injection available to tests. In production-like mode, an unregistered or host-affecting handler must return a safe denied result; real host actions are not added in this phase.

- [ ] **Step 6: Add crash and duplicate recovery tests**

Test API restart after enqueue, control Worker restart before claim, lease expiry during a read-only run, duplicate approval, provider timeout and malformed payload. Assert that an action with possible side effects enters manual_review rather than executing twice.

- [ ] **Step 7: Run focused and existing run/approval tests, then commit**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_durable_runs.py tests/test_approval_queue.py tests/test_control_worker.py tests/test_runs_api.py tests/test_approvals.py tests/test_agent_loop.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

Expected: PASS. Commit:

~~~powershell
git add apps/api/app/processes apps/api/app/api/runs.py apps/api/app/services/runs.py apps/api/app/api/approvals.py apps/api/app/services/approvals.py apps/api/app/services/agent_loop.py apps/api/app/services/executor.py compose.yaml apps/api/tests/test_durable_runs.py apps/api/tests/test_approval_queue.py apps/api/tests/test_control_worker.py
git commit -m "feat: move runs and approvals onto durable control jobs"
~~~

---

### Task 7: Compose 运行拓扑、Worker 开发启动和平台自检

**Files:**

- Modify: compose.yaml
- Modify: apps/api/Dockerfile
- Modify: scripts/start-local.ps1
- Modify: scripts/stop-local.ps1
- Create: scripts/migrate-local.ps1
- Create: scripts/setup-local.ps1
- Create: scripts/verify-foundation.ps1
- Modify: README.md
- Modify: docs/architecture.md
- Create: apps/api/app/api/platform.py
- Create: apps/api/app/services/platform_checks.py
- Test: apps/api/tests/test_platform_checks.py
- Test: apps/api/tests/test_compose_contract.py

**Interfaces:**

- GET /api/platform/health returns separate API/database/queue/Outbox/Worker checks with Chinese display labels and stable English codes.
- GET /api/platform/self-check returns migration head, queue latency, Worker heartbeat age and configured provider metadata without secrets.
- scripts/setup-local.ps1 prints the bootstrap-token file path, starts required services and opens the Chinese UI only after health checks pass.
- scripts/verify-foundation.ps1 exits non-zero for a missing migration, missing Worker heartbeat, stale queue lease or exposed PostgreSQL port.

- [ ] **Step 1: Write failing Compose and platform-check tests**

Use a YAML parser or explicit text assertions to verify:

~~~python
def test_postgres_has_no_published_host_port(compose_config):
    assert "ports" not in compose_config["services"]["postgres"]


def test_platform_health_distinguishes_worker_and_target_health(client):
    response = client.get("/api/platform/health")
    assert set(response.json()["checks"]) >= {"database", "outbox", "worker"}
~~~

- [ ] **Step 2: Run focused tests to verify the current two-service Compose contract is incomplete**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_platform_checks.py tests/test_compose_contract.py -q
~~~

Expected: FAIL because PostgreSQL, control Worker, migration command and platform checks do not exist.

- [ ] **Step 3: Define the Compose services and safe bindings**

Add postgres, api, scheduler and control-worker using the same API image where appropriate, while retaining web. Bind API and Web to 127.0.0.1; do not publish PostgreSQL. Add healthchecks that use /health and a database readiness query. Make scheduler responsible for due-task enqueueing and lease cleanup; make control-worker responsible for claiming agent_run_resume and control-plane tasks.

- [ ] **Step 4: Add operator setup and verification scripts**

start-local.ps1 must run migrations before services, wait for health, and use npm.cmd only for frontend development commands. setup-local.ps1 must never echo token contents into logs; it may print the protected file path and a command for the operator to read it locally. verify-foundation.ps1 must check localhost-only bindings, migration head, authentication status, Worker heartbeat and a no-op worker.self_check round trip.

- [ ] **Step 5: Add platform self-checks and Chinese documentation**

Return structured check objects with status, code, message_zh, observed_at and bounded details. Update README and architecture docs to remove “SQLite production evolution” wording where the new Compose path is described, document npm.cmd, the migration command, first-run setup and the boundary that no real host action exists before later phases.

- [ ] **Step 6: Run Compose smoke tests and commit**

Run:

~~~powershell
Set-Location .
docker compose config
.\scripts\start-local.ps1 -Provider mock
.\scripts\verify-foundation.ps1
.\scripts\stop-local.ps1
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_platform_checks.py tests/test_compose_contract.py -q
~~~

Expected: the stack starts with PostgreSQL, authenticated API, control Worker and native Worker protocol self-check; verification exits 0. Commit:

~~~powershell
git add compose.yaml apps/api/Dockerfile scripts/start-local.ps1 scripts/stop-local.ps1 scripts/migrate-local.ps1 scripts/setup-local.ps1 scripts/verify-foundation.ps1 README.md docs/architecture.md apps/api/app/api/platform.py apps/api/app/services/platform_checks.py apps/api/tests/test_platform_checks.py apps/api/tests/test_compose_contract.py
git commit -m "feat: package reliable local foundation"
~~~

---

### Task 8: 安全回归、故障注入和阶段 0 验收

**Files:**

- Create: apps/api/tests/test_security_regressions.py
- Create: apps/api/tests/test_failure_injection.py
- Create: apps/web/e2e/auth-and-queue.spec.ts
- Modify: apps/web/e2e/approval-flow.spec.ts
- Modify: apps/api/app/services/audit.py
- Modify: apps/api/app/api/runs.py
- Modify: apps/api/app/api/approvals.py
- Modify: apps/web/src/components/ApprovalCard.tsx
- Modify: apps/web/src/pages/RunDetailPage.tsx
- Modify: apps/web/src/pages/RunsPage.tsx

**Interfaces:**

- No new public feature is introduced; this task proves the contracts from Tasks 1–7.
- Produces a machine-readable local verification result outside Git or in the existing ignored eval output path.

- [ ] **Step 1: Write the security regression matrix**

Add tests for:

~~~python
def test_unknown_action_is_denied_without_worker_task(client, session):
    response = client.post("/api/v1/actions", json={"action_type": "unknown.action", "target_id": "target-1", "parameters": {}})
    assert response.status_code == 403
    assert list_control_tasks(session) == []


def test_arbitrary_shell_payload_is_denied_and_audited(client, session):
    response = client.post("/api/v1/actions", json={"action_type": "shell.exec", "target_id": "target-1", "parameters": {"command": "echo fake"}})
    assert response.status_code == 403
    assert last_audit_event(session).event_type == "action.denied"


def test_secret_like_keys_are_redacted_at_api_and_audit_boundaries(client, session):
    response = client.post("/api/v1/actions", json={"action_type": "worker.self_check", "parameters": {"api_key": "fake-secret"}})
    assert "fake-secret" not in response.text
    assert "fake-secret" not in last_audit_event(session).payload_json


def test_expired_approval_cannot_be_started(worker_client, expired_action):
    response = worker_client.post(f"/api/v1/worker/tasks/{expired_action.id}/start")
    assert response.status_code == 409


def test_parameter_digest_mismatch_cannot_be_started(worker_client, approved_action):
    response = worker_client.post(f"/api/v1/worker/tasks/{approved_action.id}/start", json={"request_digest": "tampered"})
    assert response.status_code == 409


def test_unscoped_client_token_cannot_approve(client, propose_only_token, pending_action):
    response = client.post(f"/api/approvals/{pending_action.id}/approve", headers=propose_only_token, json={})
    assert response.status_code == 403
~~~

The tests must assert both no system-side effect and an auditable safe result. Test payloads must use fake values, never a real API key or token.

- [ ] **Step 2: Write fault-injection tests for each approved failure behavior**

Inject database disconnect before claim, API disconnect after execution grant, control Worker crash before completion, native Worker crash after start, browser SSE disconnect and duplicate approval. Assert:

- database failure stops claim and state-changing execution;
- a pre-grant disconnect causes no handler call;
- a post-grant disconnect writes and later reports the Worker journal result;
- side-effect-uncertain work becomes manual_review;
- reconnecting the browser reads the Outbox cursor;
- duplicate approval returns conflict and creates no extra task.

- [ ] **Step 3: Add Chinese E2E coverage**

The Playwright flow must start from the login page, complete first-run setup with a test bootstrap token, create a run, show queued/running state, display a pending approval, reject it, refresh the page, and confirm the audit timeline still contains the decision. Use AGENTGATE_E2E_PYTHON and npm.cmd in the documented Windows command.

- [ ] **Step 4: Run the complete stage 0 verification**

Run:

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.evals.runner
Set-Location ..\web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
npx.cmd playwright install chromium
$env:AGENTGATE_E2E_PYTHON = "..\api\.venv\Scripts\python.exe"
npm.cmd run test:e2e
Set-Location ..\..
docker compose config
.\scripts\verify-foundation.ps1
~~~

Expected: all static checks, backend tests, deterministic evals, frontend tests/build, E2E and foundation verification pass. Record the exact output in the release note, not in a tracked secret-bearing file.

- [ ] **Step 5: Verify scope and working tree before the stage commit**

Run:

~~~powershell
git diff --check
git status --short
git diff --stat HEAD~8..HEAD
~~~

Confirm that no task added arbitrary shell execution, remote target support, file mutation, real service restart or model dependency. Confirm pre-existing user modifications remain present and are not part of the stage commits.

- [ ] **Step 6: Commit the stage 0 verification**

~~~powershell
git add apps/api/tests/test_security_regressions.py apps/api/tests/test_failure_injection.py apps/api/app/services/audit.py apps/api/app/api/runs.py apps/api/app/api/approvals.py apps/web/e2e/auth-and-queue.spec.ts apps/web/e2e/approval-flow.spec.ts apps/web/src/components/ApprovalCard.tsx apps/web/src/pages/RunDetailPage.tsx apps/web/src/pages/RunsPage.tsx
git commit -m "test: verify reliable foundation safety boundaries"
~~~

---

## 阶段 0 完成定义

阶段 0 只有在以下条件全部满足后才算完成：

- PostgreSQL 可通过 Alembic 从空卷迁移到当前 head，API 不再依赖生产 create_all()。
- 运行、审批、控制任务和 Outbox 在 API、控制 Worker 和数据库重启后可恢复。
- Web/API 有单用户会话、CSRF、作用域令牌和默认拒绝权限。
- 原生 Worker 可以注册、心跳、认领、获得执行授权、记录本机结果并在断线后补报。
- SSE 断线后可以通过 Outbox 游标补发，浏览器不会把过期事件当作当前事实。
- 数据库、Worker、队列、Outbox 和认证自检在中文界面中可区分显示。
- 没有引入真实宿主机变更；未知动作、任意命令、越界参数和密钥操作都被拒绝并审计。
- 完整后端、前端、E2E、确定性评估和 Compose 验证通过。

阶段 0 完成后，下一份计划才开始阶段 1 的目标/探针注册和 Docker、Windows 服务、HTTP 只读监控；真实重启连接器仍需新的阶段设计验收。
