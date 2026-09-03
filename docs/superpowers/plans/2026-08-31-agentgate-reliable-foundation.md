# 阶段 0：可靠底座实施计划

> **针对智能体 Worker：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项执行本计划。步骤使用复选框（`- [ ]`）语法跟踪。

**目标：** 将当前演示从 SQLite、请求内后台任务和进程内事件代理，升级为可在单台 Windows 主机上恢复运行的 PostgreSQL + 持久化队列 + 认证控制平面，并提供原生 Worker 协议骨架。

**架构：** 保留现有 FastAPI/React 技术栈，将 API 变为只负责认证、状态和任务编排的控制平面；PostgreSQL 保存所有领域状态、租约和 Outbox；独立的控制 Worker 处理 AgentRun 等容器内任务；原生 Windows Worker 只负责后续需要宿主机权限的受限连接器。本阶段不增加真实服务重启、文件写入或任意脚本能力。

**技术栈：** Python 3.11、FastAPI、SQLModel/SQLAlchemy、Alembic、psycopg 3、PostgreSQL、React/Vite、TypeScript、pytest、Ruff、mypy、Playwright、Windows DPAPI/pywin32。

**规格：** [docs/superpowers/specs/2026-08-31-agentgate-local-governance-platform-design.md](../specs/2026-08-31-agentgate-local-governance-platform-design.md)

## 全局约束

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

- 修改：apps/api/pyproject.toml — 增加 Alembic、PostgreSQL 驱动、认证和 Windows Worker 依赖。
- 修改：apps/api/app/config.py — 数据库、认证、租约、Outbox 和本机网络配置。
- 修改：apps/api/app/db.py — engine/session 工厂和迁移检查，不再负责生产建表。
- 修改：apps/api/app/main.py — 启动检查、认证中间件、路由和 CORS。
- 修改：apps/api/Dockerfile — 迁移/服务启动边界和非 root 运行。
- 修改：compose.yaml — PostgreSQL、控制 Worker、健康检查和 localhost 端口。
- 新建：apps/api/alembic.ini、apps/api/migrations/env.py、apps/api/migrations/script.py.mako、apps/api/migrations/versions/0001_legacy_schema.py。

### 控制平面领域和可靠队列

- 修改：apps/api/app/models.py — 兼容现有 Run/Action/Audit 模型并注册新模型。
- 新建：apps/api/app/control/__init__.py、apps/api/app/control/enums.py、apps/api/app/control/models.py、apps/api/app/control/repositories.py、apps/api/app/control/service.py。
- 修改：apps/api/app/repositories.py — 仅保留旧演示兼容仓储，并复用新事务接口。

### 认证与 API

- 新建：apps/api/app/auth/models.py、apps/api/app/auth/security.py、apps/api/app/auth/dependencies.py。
- 新建：apps/api/app/api/auth.py、apps/api/app/api/worker.py、apps/api/app/api/v1.py。
- 修改：apps/api/app/schemas.py、apps/api/app/api/runs.py、apps/api/app/api/approvals.py。
- 新建：apps/api/app/processes/control_worker.py — 独立进程执行持久化控制任务。
- 修改：apps/api/app/services/runs.py、apps/api/app/services/approvals.py、apps/api/app/services/events.py。

### 原生 Worker

- 新建：apps/worker/pyproject.toml、apps/worker/agentgate_worker/__init__.py、apps/worker/agentgate_worker/client.py、apps/worker/agentgate_worker/journal.py、apps/worker/agentgate_worker/vault.py、apps/worker/agentgate_worker/main.py。
- 新建：apps/worker/tests/test_client.py、apps/worker/tests/test_journal.py、apps/worker/tests/test_vault.py。
- 阶段 0 只提供控制协议、心跳、租约和安全自检能力；Windows 服务安装器和真实连接器在阶段 3/4 实现。

### 前端与测试

- 新建：apps/web/src/auth/AuthProvider.tsx、apps/web/src/pages/LoginPage.tsx。
- 修改：apps/web/src/api/client.ts、apps/web/src/App.tsx、apps/web/src/hooks/useRunEvents.ts。
- 新建：apps/web/src/auth/AuthProvider.test.tsx、apps/web/src/pages/LoginPage.test.tsx、apps/web/e2e/auth-and-queue.spec.ts。
- 新建/修改：apps/api/tests/test_migrations.py、test_control_queue.py、test_auth_api.py、test_worker_protocol.py、test_outbox.py、test_durable_runs.py、test_security_regressions.py。
- 修改：README.md、docs/architecture.md、scripts/start-local.ps1、scripts/stop-local.ps1；新增 scripts/migrate-local.ps1、scripts/setup-local.ps1、scripts/verify-foundation.ps1。

---

### 任务 0：记录现有基线并保护工作区

**文件：**

- 不修改文件。
- 只读检查：当前 Git 状态、现有测试配置和已批准的规格。

**接口：**

- 输出：基线测试命令，以及供后续验证使用的、与本计划无关的用户改动清单。

- [ ] **步骤 1：记录当前工作区状态**

运行：

~~~powershell
git status --short
git diff --stat
git log -1 --oneline
~~~

预期：列出已有的前端/后端改动文件；不要重置、暂存、检出或删除这些文件。

- [ ] **步骤 2：运行后端基线测试**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

预期：记录通过/失败数量。如果基线失败由已有用户改动导致，应保留记录，不要在本计划中“修复”无关文件。

- [ ] **步骤 3：使用 Windows 安全的 npm 可执行文件运行前端基线测试**

运行：

~~~powershell
Set-Location ..\web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
~~~

预期：记录通过/失败数量，并将之前针对 PowerShell npm.ps1 执行策略的规避方式限定在开发命令层面，不带入产品实现。

- [ ] **步骤 4：不提交代码并保留基线记录**

不要在仓库中创建生成性报告。将观察到的基线写入实现任务记录，并在最后确认：除计划文件外，预先存在的 git status 条目保持不变。

---

### 任务 1：PostgreSQL、Alembic 和可验证启动

**文件：**

- 修改：apps/api/pyproject.toml
- 修改：apps/api/app/config.py
- 修改：apps/api/app/db.py
- 修改：apps/api/app/main.py
- 修改：apps/api/Dockerfile
- 修改：compose.yaml
- 新建：apps/api/alembic.ini
- 新建：apps/api/migrations/env.py
- 新建：apps/api/migrations/script.py.mako
- 新建：apps/api/migrations/versions/0001_legacy_schema.py
- 测试：apps/api/tests/test_database_config.py
- 测试：apps/api/tests/test_migrations.py

**接口：**

- 输入：现有 SQLModel 表 agent_runs、tool_actions、audit_events、service_states。
- 输出：create_db_engine(url: str) -> Engine、get_session() -> Generator[Session, None, None]，以及记录了 head revision 的 Alembic 数据库。

- [ ] **步骤 1：新增失败的配置和迁移测试**

创建测试并包含以下断言：

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

Postgres fixture 必须针对 Compose 数据库或一次性测试数据库运行，绝不能使用生产数据卷。

- [ ] **步骤 2：运行重点测试，确认旧的 SQLite/create-all 路径会失败**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_database_config.py tests/test_migrations.py -q
~~~

预期：FAIL，因为当前设置默认使用 SQLite，且不存在 Alembic 环境。

- [ ] **步骤 3：新增数据库依赖和显式设置**

将以下依赖范围加入 pyproject.toml：

~~~toml
"alembic>=1.15,<2",
"psycopg[binary]>=3.2,<4",
"argon2-cffi>=23.1,<26",
~~~

加入以下默认设置：

~~~python
database_url: str = "postgresql+psycopg://agentgate:agentgate@postgres:5432/agentgate"
database_migration_required: bool = True
worker_lease_seconds: int = 30
outbox_batch_size: int = 100
auth_bootstrap_token_file: str = "/app/data/bootstrap-token"
~~~

保留仅供单元测试使用的 SQLite engine 工厂，但生产 Compose 默认配置绝不能选择它。

- [ ] **步骤 4：创建基础 Alembic 环境和迁移**

migrations/env.py 必须在读取 SQLModel.metadata 之前导入当前任务已有的每个 SQLModel 模块；任务 2 必须将新的控制模型加入该导入列表。基础迁移必须按照当前列、索引、唯一幂等约束以及枚举/字符串表示创建现有四张表。不要在 API lifespan 中调用 SQLModel.metadata.create_all()。

暴露一个供测试和启动检查使用的小型辅助函数：

~~~python
def upgrade_to_head(database_url: str) -> None:
    """Run Alembic upgrade head for an explicit database URL."""
~~~

- [ ] **步骤 5：在缺少迁移时让启动明确失败**

修改 app.main.lifespan：在写入任何仅供演示的状态之前验证 migration head。seed_demo_state() 只能在 AGENTGATE_ENV=development 且 AGENTGATE_SEED_DEMO=true 时运行；类生产 Compose 启动不得重新创建演示数据行。

迁移 revision 缺失时，使用 code 为 database_schema_not_ready 的 API 启动错误。保留现有的非 root Docker 用户，并新增带 healthcheck 的 Compose postgres 服务和命名数据卷，不发布宿主机端口。

- [ ] **步骤 6：运行重点测试和静态检查**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_database_config.py tests/test_migrations.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

预期：PASS。提交：

~~~powershell
git add apps/api/pyproject.toml apps/api/app/config.py apps/api/app/db.py apps/api/app/main.py apps/api/Dockerfile compose.yaml apps/api/alembic.ini apps/api/migrations apps/api/tests/test_database_config.py apps/api/tests/test_migrations.py
git commit -m "feat: add postgres migrations and startup checks"
~~~

---

### 任务 2：持久化任务、租约、Outbox 和通用审计实体

**文件：**

- 修改：apps/api/app/models.py
- 新建：apps/api/app/control/__init__.py
- 新建：apps/api/app/control/enums.py
- 新建：apps/api/app/control/models.py
- 新建：apps/api/app/control/repositories.py
- 新建：apps/api/app/control/service.py
- 修改：apps/api/app/repositories.py
- 修改：apps/api/app/services/audit.py
- 新建：apps/api/migrations/versions/0002_control_plane_tables.py
- 测试：apps/api/tests/test_control_queue.py
- 测试：apps/api/tests/test_outbox.py
- 测试：apps/api/tests/test_control_audit.py

**接口：**

- 输入：SQLAlchemy session 工厂和任务 1 的 migration head。
- 为后续任务输出以下稳定操作：

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

- [ ] **步骤 1：编写失败的状态和并发测试**

覆盖以下精确场景：

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

同时覆盖不包含 AgentRun 的通用审计路径：持久化行必须保留 resource_type/resource_id、actor 和脱敏后的 payload，同时让旧版 run_id 保持可空。

- [ ] **步骤 2：运行重点测试，确认新接口尚不存在**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_control_queue.py tests/test_outbox.py -q
~~~

预期：FAIL，因为缺少控制模型/仓储。

- [ ] **步骤 3：新增控制平面模型和迁移**

创建 ControlTask，字段包括：UUID id、TaskKind kind、TaskStatus status、JSON payload、capability、唯一幂等键、attempts、可用时间、租约所有者、租约到期时间、创建/更新/开始/完成时间戳、结果 JSON、错误类别和副作用确定性。

创建 WorkerRegistration，字段包括 UUID id、name、version、capability JSON、token digest、status、最近心跳、创建/更新时间戳。创建 OutboxEvent，包含由数据库生成的单调递增 bigint 序列、资源字段、JSON payload、发布时间戳和创建时间戳。

扩展审计表示，使通用事件支持可空的 run_id、可空的 action_id、resource_type 和 resource_id；现有旧版运行记录仍必须可读。

为 AuditService 新增一个方法：接受运行/动作上下文或通用资源上下文，在持久化前脱敏 payload，在调用方事务中追加一条 AuditEvent 和一条 OutboxEvent，且绝不要求伪造 AgentRun ID。

- [ ] **步骤 4：实现原子队列状态转换**

claim_next_task() 只能选择 available_at <= now 的 queued 任务，或选择类型允许安全重试且租约已过期的任务。使用 PostgreSQL 行锁/条件更新，确保两个 Worker 不能认领同一任务。complete_task() 必须要求当前租约所有者，且只能从 running/leased 状态转换。

对于可能产生副作用的动作，过期租约应转换为 manual_review，而不是回到 queued。对于只读/控制平面任务，过期租约应增加 attempts，并使用有界退避回到 queued。

- [ ] **步骤 5：让业务变更和 Outbox 事件处于同一事务**

新增一个服务辅助函数：

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

任何调用方都不得在该事务提交前发布用户可见的状态事件。

- [ ] **步骤 6：运行 Postgres 并发测试、静态检查并提交**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_control_queue.py tests/test_outbox.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

预期：PASS。提交：

~~~powershell
git add apps/api/app/models.py apps/api/app/control apps/api/app/repositories.py apps/api/migrations/versions/0002_control_plane_tables.py apps/api/tests/test_control_queue.py apps/api/tests/test_outbox.py
git commit -m "feat: add durable control task queue and outbox"
~~~

---

### 任务 3：单用户认证、会话、CSRF 和适配器令牌

**文件：**

- 新建：apps/api/app/auth/models.py
- 新建：apps/api/app/auth/security.py
- 新建：apps/api/app/auth/dependencies.py
- 新建：apps/api/app/api/auth.py
- 修改：apps/api/app/schemas.py
- 修改：apps/api/app/main.py
- 修改：apps/api/app/api/runs.py
- 修改：apps/api/app/api/approvals.py
- 修改：apps/api/app/api/audit.py
- 修改：apps/api/app/api/policies.py
- 新建：apps/api/app/api/v1.py
- 新建：apps/api/migrations/versions/0003_auth_tables.py
- 测试：apps/api/tests/test_auth_api.py
- 测试：apps/api/tests/test_auth_dependencies.py
- 测试：apps/api/tests/test_v1_api.py
- 新建：apps/web/src/auth/AuthProvider.tsx
- 新建：apps/web/src/pages/LoginPage.tsx
- 修改：apps/web/src/api/client.ts
- 修改：apps/web/src/App.tsx
- 新建：apps/web/src/auth/AuthProvider.test.tsx
- 新建：apps/web/src/pages/LoginPage.test.tsx

**接口：**

- 输出后端端点：

~~~text
GET  /api/auth/status
POST /api/auth/setup
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/csrf
POST /api/auth/tokens
DELETE /api/auth/tokens/{token_id}
~~~

- 输出依赖函数 require_operator(request) -> Operator 和 require_client_scope(scope) -> ClientIdentity。
- 外部适配器令牌可以提议 events/checks/actions，但不能审批、注册 Worker 或修改策略。
- 输出与协议无关的提议端点 POST /api/v1/events、POST /api/v1/checks 和 POST /api/v1/actions；这些端点会规范化输入、应用动作注册表，且绝不接受调用方提供的最终决策。

- [ ] **步骤 1：编写失败的后端认证测试**

覆盖首次运行初始化、密码哈希、Cookie 属性、CSRF 拒绝、受保护端点、退出登录失效和作用域令牌拒绝：

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

- [ ] **步骤 2：运行认证测试，确认当前 API 未认证暴露**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_auth_api.py tests/test_auth_dependencies.py -q
~~~

预期：FAIL，因为不存在 Operator/session/token 模型或受保护依赖。

- [ ] **步骤 3：实现 Operator、不可枚举会话和令牌哈希**

创建 Operator、WebSession 和 ClientToken 表。只存储 Argon2id 密码哈希和 SHA-256 令牌摘要。在 HttpOnly、SameSite=Strict Cookie 中存储不可枚举的随机会话 ID；仅在 localhost HTTP 开发环境使用 Secure=false，并将该设置显式配置，而不是从请求推断。

首次启动且不存在 Operator 时，在 auth_bootstrap_token_file 中创建随机引导令牌。POST /api/auth/setup 必须原子地消费该令牌，并拒绝第二次初始化。初始化端点绝不能返回引导令牌。

- [ ] **步骤 4：在 API 边界强制执行认证、作用域和 CSRF**

浏览器读取和所有状态变更都必须要求已认证的 Operator。外部适配器必须使用带有显式作用域的请求头令牌。所有基于 Cookie 认证的 POST、PUT、PATCH 和 DELETE 都必须要求 CSRF 令牌；精确比较已配置的 Origin，并拒绝缺失或不匹配的 Origin。

从已认证身份推导 actor。忽略并移除当前请求体中的 actor，不得将其作为授权来源；迁移期间最多只能将其保留为被拒绝的兼容字段。

- [ ] **步骤 5：新增与协议无关的 v1 提议端点**

在接入前端之前，先新增与协议无关的 v1 端点。event 创建持久化的观测/事件记录；check 创建已注册的只读任务；action 校验动作类型和目标，然后由策略引擎返回 allow_auto、require_approval 或 deny。未知动作和格式错误的参数返回 403/422，且不创建可执行任务。在 test_v1_api.py 中加入有效提议、未知动作、未注册目标和仅提议令牌的用例。

- [ ] **步骤 6：新增中文登录流程**

AuthProvider 必须请求 /api/auth/status，将未认证用户重定向到 LoginPage，在内存中保留 CSRF 令牌，并通过 X-CSRF-Token 发送。LoginPage 必须为引导初始化、登录失败、会话过期和重试显示中文标签。API client 必须将 401、403 和校验错误转换为稳定错误码，不能显示原始敏感信息。

- [ ] **步骤 7：运行后端/前端认证和 v1 测试，然后提交**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_auth_api.py tests/test_auth_dependencies.py tests/test_v1_api.py -q
Set-Location ..\web
npm.cmd test -- --run src/auth/AuthProvider.test.tsx src/pages/LoginPage.test.tsx
npm.cmd run typecheck
npm.cmd run lint
~~~

预期：PASS。提交：

~~~powershell
git add apps/api/app/auth apps/api/app/api/auth.py apps/api/app/api/v1.py apps/api/app/schemas.py apps/api/app/main.py apps/api/app/api/runs.py apps/api/app/api/approvals.py apps/api/app/api/audit.py apps/api/app/api/policies.py apps/api/migrations/versions/0003_auth_tables.py apps/api/tests/test_auth_api.py apps/api/tests/test_auth_dependencies.py apps/api/tests/test_v1_api.py apps/web/src/auth apps/web/src/pages/LoginPage.tsx apps/web/src/api/client.ts apps/web/src/App.tsx
git commit -m "feat: add local operator authentication and csrf"
~~~

---

### 任务 4：原生 Worker 注册、租约协议和本机执行日志

**文件：**

- 新建：apps/api/app/api/worker.py
- 新建：apps/api/app/services/worker_protocol.py
- 修改：apps/api/app/main.py
- 新建：apps/api/migrations/versions/0004_worker_protocol.py
- 新建：apps/worker/pyproject.toml
- 新建：apps/worker/agentgate_worker/__init__.py
- 新建：apps/worker/agentgate_worker/client.py
- 新建：apps/worker/agentgate_worker/journal.py
- 新建：apps/worker/agentgate_worker/vault.py
- 新建：apps/worker/agentgate_worker/main.py
- 新建：apps/worker/tests/test_client.py
- 新建：apps/worker/tests/test_journal.py
- 新建：apps/worker/tests/test_vault.py
- 测试：apps/api/tests/test_worker_protocol.py

**接口：**

- 输出 API 端点：

~~~text
POST /api/v1/worker/register
POST /api/v1/worker/heartbeat
POST /api/v1/worker/claim
POST /api/v1/worker/tasks/{task_id}/start
POST /api/v1/worker/tasks/{task_id}/complete
POST /api/v1/worker/tasks/{task_id}/report
~~~

- 输出 Worker 方法：

~~~python
register() -> WorkerIdentity
claim() -> TaskGrant | None
start(grant: TaskGrant) -> None
complete(grant: TaskGrant, result: dict[str, object]) -> None
recover_pending_reports() -> int
~~~

- [ ] **步骤 1：编写失败的协议和日志测试**

测试注册、无效令牌、能力过滤、租约所有者检查、启动授权、结果重放和本地日志恢复：

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

- [ ] **步骤 2：运行重点测试，确认协议尚不存在**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_worker_protocol.py -q
Set-Location ..\..\apps\worker
..\api\.venv\Scripts\python.exe -m pytest tests -q
~~~

预期：FAIL，因为不存在 Worker 路由、client、journal 或 vault。

- [ ] **步骤 3：实现注册和带作用域的 Worker 身份**

使用任务 3 生成的一次性注册令牌。只存储其摘要；注册后签发独立的 Worker 令牌，并通过本地初始化命令只显示一次。通过 win32crypt.CryptProtectData 将 Worker 凭据存储在 DPAPI 保护的文件中；为 vault 注入可替换的保护器，以便非 Windows 测试运行器使用伪实现进行单元测试。

API 必须将 Worker 请求绑定到已注册的 Worker ID、令牌摘要、协议版本和能力集合。Worker 请求不能审批动作、修改策略或提交任意目标路径。

- [ ] **步骤 4：实现 claim/start/heartbeat/complete 状态转换**

claim 使用 Worker 能力调用 claim_next_task()。connector 运行前，start 必须原子地转换任务状态，并持久化包含 task ID、request digest、Worker ID 和过期时间的执行授权。complete 必须要求相同的 Worker ID、task ID 和摘要。

使用 Python 标准库中的 SQLite 实现 Worker 本地日志。日志只存储任务身份、request digest、状态、时间戳和已脱敏的有界结果。不存储密码、API key、完整文件内容或任意命令字符串。

- [ ] **步骤 5：新增安全的 Worker self-check 任务**

本阶段只注册 worker.self_check。它返回 Worker 版本、协议版本和声明的能力；不调用 Shell、Windows 服务、Docker，不修改文件系统，也不访问网络目标。使用它验证完整的 register → claim → start → complete → report 流程。

- [ ] **步骤 6：运行协议测试、类型检查并提交**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_worker_protocol.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
Set-Location ..\..\apps\worker
..\api\.venv\Scripts\python.exe -m pytest tests -q
~~~

预期：PASS。提交：

~~~powershell
git add apps/api/app/api/worker.py apps/api/app/services/worker_protocol.py apps/api/app/main.py apps/api/migrations/versions/0004_worker_protocol.py apps/worker
git commit -m "feat: add native worker protocol foundation"
~~~

---

### 任务 5：用持久化 Outbox 替换内存事件代理

**文件：**

- 修改：apps/api/app/services/events.py
- 新建：apps/api/app/services/outbox.py
- 新建：apps/api/app/api/events.py
- 修改：apps/api/app/api/runs.py
- 修改：apps/api/app/main.py
- 修改：apps/web/src/hooks/useRunEvents.ts
- 修改：apps/web/src/api/client.ts
- 测试：apps/api/tests/test_outbox_stream.py
- 测试：apps/api/tests/test_sse.py
- 测试：apps/web/src/api/client.test.ts
- 测试：apps/web/src/pages/RunDetailPage.test.tsx

**接口：**

- 输出 read_events_after(cursor: int, resource_id: UUID | None, limit: int) -> list[OutboxEvent]。
- 输出 format_outbox_sse(event: OutboxEvent) -> str，其中包含 id、event 和 JSON data。
- 迁移期间保留由 Outbox 支撑的兼容端点 GET /api/runs/{run_id}/events。

- [ ] **步骤 1：编写失败的重连和顺序测试**

测试客户端在 event 2 后断开，并使用 Last-Event-ID: 2 重连后从 event 3 开始接收；测试两个 API 进程读取同一个 Outbox 时看到相同的事件 ID；测试不存在的运行返回 404 且不创建订阅。

~~~python
def test_sse_reconnects_from_last_event_id(api_client, outbox_events):
    response = api_client.get("/api/runs/run-id/events", headers={"Last-Event-ID": "2"})
    assert response.status_code == 200
    assert "id: 3" in response.text
~~~

- [ ] **步骤 2：运行事件测试，确认当前 broker 会丢失历史**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_sse.py tests/test_outbox_stream.py -q
~~~

预期：新的持久化历史断言在进程内 EventBroker 上失败。

- [ ] **步骤 3：通过 Outbox 事务传递领域事件**

将运行、审批和审计路径中的直接 event_broker.publish() 调用替换为 append_outbox_event()，并放入修改 run/action 状态的同一事务中。保留 event_to_sse() 作为持久化事件的序列化器；从生产代码中移除进程内计数器和订阅者映射。

- [ ] **步骤 4：实现持久化 SSE 读取器**

端点必须先读取已有行，然后以有界数据库间隔轮询新行，每 15 秒发送一次 heartbeat，并在客户端取消时干净关闭。使用 Last-Event-ID 和显式的 after 查询参数；只有两者都是有效整数时，才采用较小的有效游标。序列化前脱敏 payload，并限制每个事件 payload 的大小。

- [ ] **步骤 5：更新前端重连行为**

useRunEvents 必须保留最近的数字事件 ID，在网络错误后使用上限为 30 秒的指数退避重连，并在重连后重新获取运行详情。过期或格式错误的事件不得覆盖 REST 状态。

- [ ] **步骤 6：运行后端/前端事件测试并提交**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_outbox_stream.py tests/test_sse.py -q
Set-Location ..\web
npm.cmd test -- --run src/api/client.test.ts src/pages/RunDetailPage.test.tsx
npm.cmd run typecheck
~~~

预期：PASS。提交：

~~~powershell
git add apps/api/app/services/events.py apps/api/app/services/outbox.py apps/api/app/api/events.py apps/api/app/api/runs.py apps/api/app/main.py apps/web/src/hooks/useRunEvents.ts apps/web/src/api/client.ts apps/api/tests/test_outbox_stream.py apps/api/tests/test_sse.py apps/web/src/api/client.test.ts apps/web/src/pages/RunDetailPage.test.tsx
git commit -m "feat: make run events durable and reconnectable"
~~~

---

### 任务 6：移除请求内后台任务并接入持久化控制 Worker

**文件：**

- 新建：apps/api/app/processes/__init__.py
- 新建：apps/api/app/processes/control_worker.py
- 修改：apps/api/app/api/runs.py
- 修改：apps/api/app/services/runs.py
- 修改：apps/api/app/api/approvals.py
- 修改：apps/api/app/services/approvals.py
- 修改：apps/api/app/services/agent_loop.py
- 修改：apps/api/app/services/executor.py
- 修改：compose.yaml
- 测试：apps/api/tests/test_durable_runs.py
- 测试：apps/api/tests/test_approval_queue.py
- 测试：apps/api/tests/test_control_worker.py

**接口：**

- RunService.create(user_request: str, source: ClientIdentity) -> AgentRun 返回 queued 运行记录，并加入一个 agent_run_resume 任务。
- ApprovalService.decide(action_id: UUID, decision: ApprovalDecision, operator: Operator, note: str | None) -> ToolAction 持久化决策并加入一个 resume 任务；请求中不调用 AgentRunner 或 ToolExecutor。
- ControlWorker.run_once() -> int 使用新的数据库会话认领并执行至多一个控制平面任务。
- ControlWorker.run_forever() -> None 运行持久化认领循环，并在遇到不可恢复的配置错误时以非零状态退出。

- [ ] **步骤 1：编写失败的持久化运行和审批测试**

覆盖以下精确状态转换：

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

- [ ] **步骤 2：运行重点测试，确认当前 BackgroundTasks/direct-resume 行为**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_durable_runs.py tests/test_approval_queue.py tests/test_control_worker.py -q
~~~

预期：FAIL，因为 RunService 添加 BackgroundTasks，ApprovalService 直接执行/恢复 Agent。

- [ ] **步骤 3：让运行创建持久化并限定在请求范围内**

从 POST /api/runs 移除 BackgroundTasks。在一个事务中创建运行记录、初始 checkpoint、审计事件和 agent_run_resume 任务。返回状态码 202 及 queued 状态。任何 provider 调用开始前，HTTP 依赖使用的 session 必须已关闭。

- [ ] **步骤 4：让审批具备条件约束并异步执行**

在一个事务中，要求 pending_approval，绑定已认证的 Operator、备注、动作参数摘要和生效中的策略版本，转换动作状态，追加审计事件并加入一个 resume 任务。重复审批返回 409，且不创建第二个任务。被拒绝的动作生成持久化的安全结果，不调用 handler。

- [ ] **步骤 5：实现隔离的控制 Worker 循环**

control_worker.py 必须为每个认领的任务创建新的 SQLModel session，仅针对 agent_run_resume 运行现有的 provider-neutral AgentRunner，并在完成后关闭 session。它不得使用 FastAPI BackgroundTasks、request 对象、进程内事件状态，或从 API 请求中捕获的 session。

对于旧版模拟 ToolExecutor，保留供测试使用的 handler 注入。在类生产模式下，未注册或会影响宿主机的 handler 必须返回安全的拒绝结果；本阶段不增加真实宿主机动作。

- [ ] **步骤 6：新增崩溃和重复操作恢复测试**

测试加入任务后的 API 重启、认领前的控制 Worker 重启、只读运行期间的租约过期、重复审批、provider 超时和格式错误的 payload。断言可能产生副作用的动作进入 manual_review，而不是执行两次。

- [ ] **步骤 7：运行重点测试和现有运行/审批测试，然后提交**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_durable_runs.py tests/test_approval_queue.py tests/test_control_worker.py tests/test_runs_api.py tests/test_approvals.py tests/test_agent_loop.py -q
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
~~~

预期：PASS。提交：

~~~powershell
git add apps/api/app/processes apps/api/app/api/runs.py apps/api/app/services/runs.py apps/api/app/api/approvals.py apps/api/app/services/approvals.py apps/api/app/services/agent_loop.py apps/api/app/services/executor.py compose.yaml apps/api/tests/test_durable_runs.py apps/api/tests/test_approval_queue.py apps/api/tests/test_control_worker.py
git commit -m "feat: move runs and approvals onto durable control jobs"
~~~

---

### 任务 7：Compose 运行拓扑、Worker 开发启动和平台自检

**文件：**

- 修改：compose.yaml
- 修改：apps/api/Dockerfile
- 修改：scripts/start-local.ps1
- 修改：scripts/stop-local.ps1
- 新建：scripts/migrate-local.ps1
- 新建：scripts/setup-local.ps1
- 新建：scripts/verify-foundation.ps1
- 修改：README.md
- 修改：docs/architecture.md
- 新建：apps/api/app/api/platform.py
- 新建：apps/api/app/services/platform_checks.py
- 测试：apps/api/tests/test_platform_checks.py
- 测试：apps/api/tests/test_compose_contract.py

**接口：**

- GET /api/platform/health 返回分开的 API/database/queue/Outbox/Worker 检查结果，带中文显示标签和稳定的英文 code。
- GET /api/platform/self-check 返回 migration head、队列延迟、Worker 心跳年龄和已配置的 provider 元数据，但不包含敏感信息。
- scripts/setup-local.ps1 输出 bootstrap-token 文件路径，启动所需服务，并仅在健康检查通过后打开中文界面。
- scripts/verify-foundation.ps1 在迁移缺失、Worker 心跳缺失、队列租约过期或 PostgreSQL 端口暴露时以非零状态退出。

- [ ] **步骤 1：编写失败的 Compose 和平台检查测试**

使用 YAML 解析器或明确的文本断言验证：

~~~python
def test_postgres_has_no_published_host_port(compose_config):
    assert "ports" not in compose_config["services"]["postgres"]


def test_platform_health_distinguishes_worker_and_target_health(client):
    response = client.get("/api/platform/health")
    assert set(response.json()["checks"]) >= {"database", "outbox", "worker"}
~~~

- [ ] **步骤 2：运行重点测试，确认当前双服务 Compose 契约不完整**

运行：

~~~powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_platform_checks.py tests/test_compose_contract.py -q
~~~

预期：FAIL，因为不存在 PostgreSQL、控制 Worker、迁移命令和平台检查。

- [ ] **步骤 3：定义 Compose 服务和安全绑定**

在适当情况下使用同一个 API 镜像新增 postgres、api、scheduler 和 control-worker，同时保留 web。将 API 和 Web 绑定到 127.0.0.1；不要发布 PostgreSQL 端口。新增使用 /health 和数据库就绪查询的 healthcheck。由 scheduler 负责到期任务入队和租约清理；由 control-worker 负责认领 agent_run_resume 和控制平面任务。

- [ ] **步骤 4：新增 Operator 初始化和验证脚本**

start-local.ps1 必须在服务启动前运行迁移、等待健康检查，并且前端开发命令只能使用 npm.cmd。setup-local.ps1 绝不能将令牌内容回显到日志；可以输出受保护文件路径和供 Operator 在本地读取它的命令。verify-foundation.ps1 必须检查仅 localhost 绑定、migration head、认证状态、Worker 心跳以及无副作用的 worker.self_check 往返流程。

- [ ] **步骤 5：新增平台自检和中文文档**

返回包含 status、code、message_zh、observed_at 和有界 details 的结构化检查对象。更新 README 和架构文档：在介绍新的 Compose 路径处移除“SQLite production evolution”表述，记录 npm.cmd、迁移命令、首次运行初始化，以及后续阶段之前不存在真实宿主机动作这一边界。

- [ ] **步骤 6：运行 Compose 冒烟测试并提交**

运行：

~~~powershell
Set-Location .
docker compose config
.\scripts\start-local.ps1 -Provider mock
.\scripts\verify-foundation.ps1
.\scripts\stop-local.ps1
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_platform_checks.py tests/test_compose_contract.py -q
~~~

预期：栈启动后包含 PostgreSQL、已认证 API、控制 Worker 和原生 Worker 协议自检；验证以 0 退出。提交：

~~~powershell
git add compose.yaml apps/api/Dockerfile scripts/start-local.ps1 scripts/stop-local.ps1 scripts/migrate-local.ps1 scripts/setup-local.ps1 scripts/verify-foundation.ps1 README.md docs/architecture.md apps/api/app/api/platform.py apps/api/app/services/platform_checks.py apps/api/tests/test_platform_checks.py apps/api/tests/test_compose_contract.py
git commit -m "feat: package reliable local foundation"
~~~

---

### 任务 8：安全回归、故障注入和阶段 0 验收

**文件：**

- 新建：apps/api/tests/test_security_regressions.py
- 新建：apps/api/tests/test_failure_injection.py
- 新建：apps/web/e2e/auth-and-queue.spec.ts
- 修改：apps/web/e2e/approval-flow.spec.ts
- 修改：apps/api/app/services/audit.py
- 修改：apps/api/app/api/runs.py
- 修改：apps/api/app/api/approvals.py
- 修改：apps/web/src/components/ApprovalCard.tsx
- 修改：apps/web/src/pages/RunDetailPage.tsx
- 修改：apps/web/src/pages/RunsPage.tsx

**接口：**

- 不引入新的公开功能；本任务验证任务 1–7 的契约。
- 在 Git 之外或现有被忽略的评测输出路径中生成机器可读的本地验证结果。

- [ ] **步骤 1：编写安全回归矩阵**

新增以下测试：

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

测试必须同时断言没有系统侧副作用，并且生成可审计的安全结果。测试 payload 必须使用伪值，绝不能使用真实 API key 或令牌。

- [ ] **步骤 2：为每种已批准的失败行为编写故障注入测试**

注入以下故障：认领前数据库断开、取得执行授权后 API 断开、完成前控制 Worker 崩溃、启动后原生 Worker 崩溃、浏览器 SSE 断开和重复审批。断言：

- 数据库故障会停止认领和状态变更执行；
- 取得授权前断开不会调用 handler；
- 取得授权后断开会写入 Worker 日志结果，并在之后回报；
- 无法确定副作用的工作会进入 manual_review；
- 浏览器重连会读取 Outbox 游标；
- 重复审批返回冲突，且不创建额外任务。

- [ ] **步骤 3：新增中文 E2E 覆盖**

Playwright 流程必须从登录页开始，使用测试 bootstrap token 完成首次运行初始化，创建一次运行，显示 queued/running 状态，展示待审批动作，拒绝该动作，刷新页面，并确认审计时间线仍包含该决策。按文档中的 Windows 命令使用 AGENTGATE_E2E_PYTHON 和 npm.cmd。

- [ ] **步骤 4：运行完整的阶段 0 验证**

运行：

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

预期：所有静态检查、后端测试、确定性评测、前端测试/构建、E2E 和基础验证均通过。将完整输出记录在发布说明中，不要写入受 Git 跟踪且可能包含敏感信息的文件。

- [ ] **步骤 5：在阶段提交前验证范围和工作区**

运行：

~~~powershell
git diff --check
git status --short
git diff --stat HEAD~8..HEAD
~~~

确认没有任何任务新增任意 Shell 执行、远程目标支持、文件变更、真实服务重启或模型依赖。确认预先存在的用户改动仍然存在，且不属于阶段提交。

- [ ] **步骤 6：提交阶段 0 验证结果**

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
