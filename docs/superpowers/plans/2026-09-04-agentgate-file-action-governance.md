# AgentGate 真实文件动作治理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AgentGate 从“记录健康状态”升级为一个 Windows 单机可真实使用的 Agent 动作治理控制平面：外部 Agent 只能提交结构化文件动作，AgentGate 负责确定性策略、人工审批、受限 Worker 执行、隔离/恢复和可追溯审计。

**Architecture:** API 和 PostgreSQL 保存工作区、动作、审批、任务、隔离记录与审计状态；API 不直接接触受管文件。Native Worker 从回环 API 获取带版本的工作区上下文，只执行三个版本化文件能力（检查、隔离、恢复），并在 Worker 侧再次执行路径和文件类型校验。React 前端以“安全演示、动作、审批、工作区、审计、系统”为主流程，健康监控保留在系统页。

**Tech Stack:** Python 3.11、FastAPI、SQLModel、Alembic、PostgreSQL、Pydantic、httpx、pywin32、React 19、Vite、TypeScript、Vitest、Playwright、PowerShell。

**Spec:** `docs/superpowers/specs/2026-09-04-agentgate-file-action-governance-design.md`

## Global Constraints

- 首版只支持 Windows 11、单机、单用户和回环地址；禁止把本轮范围扩展为远程主机、多租户或云端控制台。
- Agent 只能提交 UTF-8 相对路径；API 和 Worker 都必须拒绝盘符、UNC、NUL、冒号/备用数据流、`.`、`..`、空路径段、目录、设备、命名管道、符号链接、junction 和其他 reparse point。
- 只实现 `file.inspect.v1`、`file.quarantine.v1`、`file.restore.v1`；不执行任意 Shell、PowerShell、命令字符串、上传脚本、递归删除或永久删除。
- `file.inspect.v1` 只返回元数据和 SHA-256，不默认返回正文；敏感文件内容不得进入模型、API、数据库、审计或普通日志。
- `file.quarantine.v1` 只允许单个普通文件，必须人工审批；隔离区必须与工作区同一 NTFS 卷、位于工作区之外，操作使用同卷移动，不提供“删除”按钮。
- `file.restore.v1` 只接收已有 `quarantine_entry_id`，目标存在时返回 `destination_conflict`，不覆盖、不改名、不猜测目标。
- 外部动作必须使用 Bearer token、`propose:actions` scope 和 `Idempotency-Key`；外部 Agent 不能提交绝对路径、策略决定、审批人或 Worker 参数。
- API 是控制平面，Worker 是唯一文件系统执行边界；API 重启、Worker 断线、浏览器关闭和重复提交不能制造第二次移动。
- 所有面向用户的界面、错误码解释和 README/演示文档使用中文；`mock` 可离线完成确定性演示，Ark 只作为可选提供方。
- 任何测试只能清理测试自己创建且经过绝对路径确认的专用临时目录；不得读取、输出或提交 `.demo-worker` 内的凭据和 journal。
- 每个任务先写失败测试，再写最小实现；每个任务完成后只提交该任务涉及的文件，不得把现有脏工作区混入提交。

---

## 文件边界总览

| 组件 | 文件 | 职责 |
| --- | --- | --- |
| 文件领域模型 | `apps/api/app/files/models.py` | 工作区、隔离记录、文件动作参数和结果的数据结构 |
| 路径与规则 | `apps/api/app/files/security.py` | 相对路径规范化、保护规则匹配、登记根目录验证 |
| 工作区服务 | `apps/api/app/services/workspaces.py` | 工作区登记、版本递增、启停、隔离区约束 |
| 文件动作服务 | `apps/api/app/services/file_actions.py` | 动作策略、持久化动作、审批/任务编排和状态投影 |
| HTTP 接口 | `apps/api/app/api/workspaces.py`、`apps/api/app/api/v1.py` | 工作区、外部动作、动作状态、隔离记录接口 |
| Worker 协议 | `apps/api/app/services/worker_protocol.py`、`apps/worker/agentgate_worker/client.py` | capability、任务 payload、授权上下文和回报 |
| Windows 执行器 | `apps/worker/agentgate_worker/filesystem.py` | 文件句柄、reparse 检查、哈希、同卷隔离与恢复 |
| 前端 | `apps/web/src/pages/*`、`apps/web/src/api/*` | 中文安全演示、动作、审批、工作区、审计页面 |
| 一键演示 | `scripts/demo.ps1` | 检查依赖、启动服务、准备示例工作区、打开演示页面 |
| 迁移 | `apps/api/migrations/versions/0010_file_action_governance.py` | 为真实动作闭环增加数据库结构 |

---

### Task 1: 建立文件治理领域模型、数据库迁移和路径安全内核

**Files:**
- Create: `apps/api/app/files/__init__.py`
- Create: `apps/api/app/files/models.py`
- Create: `apps/api/app/files/security.py`
- Modify: `apps/api/app/models.py`
- Modify: `apps/api/app/db.py`
- Modify: `apps/api/migrations/env.py`
- Create: `apps/api/migrations/versions/0010_file_action_governance.py`
- Test: `apps/api/tests/test_file_models.py`
- Test: `apps/api/tests/test_file_security.py`
- Modify: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces `normalize_relative_path(raw: str) -> str`, `validate_managed_root(root_path: str, allowed_root: str) -> str`, and `protected_match(relative_path: str, patterns: list[str]) -> str | None`.
- Produces `ManagedWorkspace(id, name, root_path, canonical_root_path, quarantine_root_path, protected_patterns, enabled, version, created_at, updated_at)`.
- Produces `QuarantineEntry(id, workspace_id, action_id, original_relative_path, quarantine_relative_path, content_sha256, size_bytes, status, created_at, restored_at)`.
- Modifies `ToolAction` so `run_id` is nullable and adds `proposer_client_id`, `target_type`, `target_id`, `action_version`, `arguments_digest`, `policy_version`, and `approval_expires_at`.

- [ ] **Step 1: Write failing model and path tests**

```python
def test_normalize_relative_path_returns_forward_slashes():
    assert normalize_relative_path(r"docs\notes.txt") == "docs/notes.txt"

@pytest.mark.parametrize("value", ["", ".", "..", r"C:\a.txt", r"\\server\share\a.txt", "a:stream", "a/../b", "a//b", "a\x00b"])
def test_normalize_relative_path_rejects_unsafe_input(value: str):
    with pytest.raises(InvalidRelativePath):
        normalize_relative_path(value)

def test_protected_match_is_case_insensitive_and_uses_relative_path():
    assert protected_match(".GIT/HEAD", [".git/**"]) == ".git/**"

def test_workspace_version_and_quarantine_status_are_persistable(session):
    workspace = ManagedWorkspace(
        id=uuid4(), name="演示工作区", root_path=r"D:\demo",
        canonical_root_path=r"D:\demo", quarantine_root_path=r"D:\demo-quarantine",
        protected_patterns=[".git/**"], enabled=True, version=1,
    )
    entry = QuarantineEntry(
        id=uuid4(), workspace_id=workspace.id, action_id=uuid4(),
        original_relative_path="notes.txt", quarantine_relative_path="entries/notes.txt",
        content_sha256="a" * 64, size_bytes=1, status="quarantined",
    )
    session.add_all([workspace, entry]); session.commit()
    assert session.get(ManagedWorkspace, workspace.id).version == 1
    assert session.get(QuarantineEntry, entry.id).status == "quarantined"
```

- [ ] **Step 2: Run the focused tests and record the expected failures**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_security.py tests/test_file_models.py -q`

Expected: collection or assertion failures because the file domain module and models do not exist yet; no production file is changed by this step.

- [ ] **Step 3: Implement the domain models and deterministic path rules**

Implement `normalize_relative_path` with these exact checks in order: require `str`, reject NUL, reject empty input, convert `\` to `/`, reject a leading `/`, reject a drive prefix or any `:` in a segment, split on `/`, reject empty/`.`/`..` segments, reject segments ending in a dot or space, reject Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, including an extension), reject a segment over 255 characters and a normalized path over 4,000 characters, then return the normalized path. Use `PureWindowsPath` only as an additional syntax check; do not turn an Agent path into an absolute path.

Implement `validate_managed_root` to require an absolute local Windows path, reject UNC/device/remote paths, resolve the path without following a final reparse point, compare case-insensitively with the configured allowed root using `ntpath.commonpath`, and return the canonical string. Define `DEFAULT_PROTECTED_PATTERNS` as `.git/**`, `.agentgate/**`, `.env`, `.env.*`, `*.key`, `*.pem`, `credentials.*`, and `protected/**`. Implement `protected_match` with case-insensitive slash-normalized glob matching and return the matched pattern.

```python
def normalize_relative_path(raw: str) -> str:
    """Return a safe slash-normalized Agent-relative path or raise InvalidRelativePath."""
    raise NotImplementedError

def protected_match(relative_path: str, patterns: list[str]) -> str | None:
    """Return the first case-insensitive protected glob that matches."""
    raise NotImplementedError
```

- [ ] **Step 4: Add SQLModel fields, metadata imports, and Alembic migration**

Add the two new tables with UUID primary keys, foreign keys to the existing action/workspace owner records where applicable, string status checks, timestamps, and indexes on `(workspace_id, status)`, `(action_id)`, and `(workspace_id, original_relative_path)`. Change `ToolAction.run_id` to `UUID | None` and add a check that exactly one of `run_id` and `proposer_client_id` is present. Import the new models from `app.db` so test metadata and Alembic see them. In `0010_file_action_governance.py`, implement `upgrade()` and `downgrade()` for PostgreSQL and SQLite-compatible test metadata; do not edit earlier migrations.

- [ ] **Step 5: Run migration and focused tests, then commit the isolated task**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_security.py tests/test_file_models.py tests/test_migrations.py -q`

Expected: all focused tests pass, with migration head `0010_file_action_governance`. Commit only the files listed in Task 1: `git add apps/api/app/files apps/api/app/models.py apps/api/app/db.py apps/api/migrations/versions/0010_file_action_governance.py apps/api/tests/test_file_models.py apps/api/tests/test_file_security.py apps/api/tests/test_migrations.py; git commit -m "feat: 增加文件治理领域模型和路径安全"`.

### Task 2: 实现工作区登记、版本管理和保护规则接口

**Files:**
- Create: `apps/api/app/services/workspaces.py`
- Create: `apps/api/app/api/workspaces.py`
- Create: `apps/api/app/schemas_workspaces.py`
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_workspaces_api.py`
- Test: `apps/api/tests/test_workspace_service.py`

**Interfaces:**
- Produces `WorkspaceService.create(name: str, root_path: str, protected_patterns: list[str] | None) -> ManagedWorkspace`.
- Produces `WorkspaceService.update(workspace_id: UUID, patch: WorkspacePatch) -> ManagedWorkspace`, `set_enabled(workspace_id: UUID, enabled: bool) -> ManagedWorkspace`, and `list_quarantine_entries(workspace_id: UUID, status: str | None) -> list[QuarantineEntry]`.
- Adds `POST /api/v1/workspaces`, `GET /api/v1/workspaces`, `PATCH /api/v1/workspaces/{workspace_id}`, and `GET /api/v1/workspaces/{workspace_id}/quarantine`.
- All modifying endpoints require the existing local administrator dependency; external Agent tokens cannot call them.

- [ ] **Step 1: Write failing service and API tests**

```python
def test_create_workspace_rejects_root_outside_allowed_root(client, admin_headers, tmp_path):
    response = client.post("/api/v1/workspaces", headers=admin_headers, json={
        "name": "演示工作区", "root_path": str(tmp_path), "protected_patterns": ["protected/**"]
    })
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "workspace_root_not_allowed"

def test_workspace_update_increments_version_and_disable_blocks_actions(client, admin_headers, workspace):
    response = client.patch(f"/api/v1/workspaces/{workspace['id']}", json={"enabled": False}, headers=admin_headers)
    assert response.json()["version"] == workspace["version"] + 1
    assert response.json()["enabled"] is False

def test_workspace_quarantine_endpoint_never_returns_absolute_paths(client, admin_headers, workspace_id):
    response = client.get(f"/api/v1/workspaces/{workspace_id}/quarantine", headers=admin_headers)
    assert all("root_path" not in item and ":\\" not in item["original_relative_path"] for item in response.json()["items"])
```

- [ ] **Step 2: Run the focused tests to verify the new routes are absent**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_workspaces_api.py tests/test_workspace_service.py -q`

Expected: failures with missing route/service symbols.

- [ ] **Step 3: Implement the workspace service with same-volume quarantine validation**

On create, validate the name length and control characters, canonicalize the root with `validate_managed_root`, ensure the directory exists or return `workspace_root_not_found`, require a local NTFS volume, derive a generated quarantine directory outside the workspace root, verify it is on the same volume and not nested under the workspace, create it with restricted local permissions, store only the canonical paths in the administrator-facing database, and initialize `version=1`. On update, apply only the explicit patch, revalidate any changed root/quarantine relationship, increment `version` exactly once, and reject changes while a quarantine entry is in `quarantined` or `failed` state unless the caller first disables the workspace.

```python
class WorkspaceService:
    def create(self, name: str, root_path: str, protected_patterns: list[str] | None) -> ManagedWorkspace:
        raise NotImplementedError

    def update(self, workspace_id: UUID, patch: WorkspacePatch) -> ManagedWorkspace:
        raise NotImplementedError

    def set_enabled(self, workspace_id: UUID, enabled: bool) -> ManagedWorkspace:
        raise NotImplementedError

    def get_context(self, workspace_id: UUID, version: int) -> WorkspaceContext:
        raise NotImplementedError
```

- [ ] **Step 4: Add administrator-only routes and sanitized response schemas**

Expose `root_path` only on local administrator workspace screens; quarantine list and external action responses must contain `workspace_id`, `relative_path`, status, size, digest and timestamps, never absolute paths. Return Chinese `error.code`, `message`, and `details` using the existing error envelope. Register the router in `main.py` under `/api/v1`.

- [ ] **Step 5: Run API, service, and migration tests, then commit**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_workspaces_api.py tests/test_workspace_service.py tests/test_file_security.py -q`

Expected: all tests pass and disabled/nonexistent/version-conflict workspaces return deterministic errors. Commit: `git add apps/api/app/services/workspaces.py apps/api/app/api/workspaces.py apps/api/app/schemas/workspaces.py apps/api/app/main.py apps/api/tests/test_workspaces_api.py apps/api/tests/test_workspace_service.py; git commit -m "feat: 增加受管工作区管理接口"`.

### Task 3: 把文件动作接入统一策略、审批和持久化动作状态机

**Files:**
- Create: `apps/api/app/services/file_actions.py`
- Create: `apps/api/app/schemas_actions.py`
- Create: `apps/api/migrations/versions/0011_scoped_action_idempotency.py`
- Modify: `apps/api/app/models.py`
- Modify: `apps/api/app/policy.py`
- Modify: `apps/api/app/api/v1.py`
- Modify: `apps/api/app/control/repositories.py`
- Modify: `apps/api/app/services/audit.py`
- Test: `apps/api/tests/test_file_action_policy.py`
- Test: `apps/api/tests/test_external_actions.py`
- Test: `apps/api/tests/test_action_idempotency.py`

**Interfaces:**
- Produces `FileActionPolicy.evaluate(action: ActionName, workspace: ManagedWorkspace, arguments: dict, caller: ActionCaller) -> PolicyEvaluation`.
- Produces `ExternalActionService.propose(client_id: UUID, request: ExternalActionRequest, idempotency_key: str) -> ActionStatusResponse`.
- Adds/updates `POST /api/v1/actions` to create a durable action and `GET /api/v1/actions/{action_id}` to read status for the same client; the existing AgentRunner calls the same service.
- Defines action payloads: inspect `{workspace_id, workspace_version, relative_path, arguments_digest, policy_version}`, quarantine with the same fields plus `reason`, and restore `{workspace_id, workspace_version, quarantine_entry_id, arguments_digest, policy_version}`.

- [ ] **Step 1: Write the policy matrix and idempotency tests first**

```python
def test_inspect_is_auto_allowed_for_regular_unprotected_path(workspace, caller):
    decision = FileActionPolicy().evaluate("file.inspect.v1", workspace, {"relative_path": "notes/a.txt"}, caller)
    assert (decision.name, decision.requires_approval) == ("allow_auto", False)

def test_quarantine_protected_path_is_denied_without_task(workspace, caller):
    decision = FileActionPolicy().evaluate("file.quarantine.v1", workspace, {"relative_path": ".env"}, caller)
    assert decision.name == "deny"
    assert decision.code == "protected_path"

def test_same_client_idempotency_key_returns_same_action(client, action_request, token):
    first = propose(client, action_request, token, idempotency_key="demo-1")
    second = propose(client, action_request, token, idempotency_key="demo-1")
    assert second["action_id"] == first["action_id"]
    assert count_tasks_for_action(first["action_id"]) == 1
```

- [ ] **Step 2: Run focused tests and verify the current policy is insufficient**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_action_policy.py tests/test_external_actions.py tests/test_action_idempotency.py -q`

Expected: failures because current policy ignores path/workspace arguments and `/actions` only performs a precheck.

- [ ] **Step 3: Implement deterministic file policy and safe input schemas**

Validate action name against the three exact versions, normalize `relative_path`, enforce the workspace ID and version, reject arguments not in the action schema, calculate canonical JSON SHA-256 `arguments_digest`, and include `policy_version="file-policy.v1"`. Return: inspect → `allow_auto`; quarantine protected/disabled/invalid/not-regular-at-policy-level → `deny`, otherwise `require_approval`; restore unknown entry/disabled workspace → `deny`, otherwise `require_approval`. Never accept `absolute_path`, `policy_decision`, `approver_id`, `worker_id`, `status`, or `retry_count` from an external caller.

```python
class FileActionPolicy:
    def evaluate(self, action: ActionName, workspace: ManagedWorkspace,
                 arguments: dict[str, object], caller: ActionCaller) -> PolicyEvaluation:
        raise NotImplementedError

class ExternalActionService:
    def propose(self, client_id: UUID, request: ExternalActionRequest,
                idempotency_key: str) -> ActionStatusResponse:
        raise NotImplementedError
```

- [ ] **Step 4: Persist deny, approval, auto-allow, audit, and outbox transitions transactionally**

For `deny`, insert a terminal `ToolAction` with `status="denied"`, an audit event with sanitized relative arguments, and no control task. For `require_approval`, insert `status="pending_approval"` and the existing approval record, with a bounded expiry of 30 minutes. For `allow_auto`, in one transaction insert the action, control task, and Outbox event. Reuse the existing proposer-client idempotency uniqueness behavior; if the same key is reused with a different action/version/digest, return `idempotency_key_reused` and do not mutate the original action. Update AgentRunner to call this service rather than a separate policy path.

- [ ] **Step 5: Run policy/API tests and commit only the action layer**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_action_policy.py tests/test_external_actions.py tests/test_action_idempotency.py tests/test_approval_queue.py tests/test_approvals.py tests/test_agent_loop.py -q`

Expected: policy matrix, persisted deny, approval creation, auto task creation, token scope and idempotency tests pass. Commit: `git add apps/api/app/services/file_actions.py apps/api/app/schemas/actions.py apps/api/app/policy.py apps/api/app/api/v1.py apps/api/app/control/repositories.py apps/api/app/services/audit.py apps/api/tests/test_file_action_policy.py apps/api/tests/test_external_actions.py apps/api/tests/test_action_idempotency.py; git commit -m "feat: 将文件动作接入统一策略和审批"`.

### Task 4: 扩展 Worker 协议、执行上下文和断线安全语义

**Files:**
- Create: `apps/api/app/schemas_worker_files.py`
- Modify: `apps/api/app/services/worker_protocol.py`
- Create: `apps/api/app/api/worker.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/worker/agentgate_worker/client.py`
- Modify: `apps/worker/agentgate_worker/main.py`
- Test: `apps/api/tests/test_worker_file_protocol.py`
- Test: `apps/api/tests/test_worker_context_api.py`
- Modify: `apps/worker/tests/test_client.py`
- Modify: `apps/worker/tests/test_main.py`

**Interfaces:**
- Produces `FILE_CAPABILITIES = frozenset({"file.inspect.v1", "file.quarantine.v1", "file.restore.v1"})`.
- Produces strict Pydantic payload models `FileInspectTask`, `FileQuarantineTask`, and `FileRestoreTask` with `extra="forbid"`.
- Adds protected `GET /api/v1/worker/workspaces/{workspace_id}?version={workspace_version}&task_id={task_id}` returning `WorkspaceContext` only to a registered Worker with a valid execution grant.
- Produces Worker client method `get_workspace_context(grant: TaskGrant) -> WorkspaceContext`; the grant carries the task ID used to authorize the context request.

- [ ] **Step 1: Write protocol rejection and context authorization tests**

```python
def test_file_task_rejects_absolute_path_and_unknown_field():
    with pytest.raises(ValidationError):
        FileInspectTask.model_validate({"workspace_id": str(uuid4()), "workspace_version": 1,
            "relative_path": r"C:\secret.txt", "arguments_digest": "a" * 64,
            "policy_version": "file-policy.v1", "worker_root": "C:\\root"})

def test_worker_context_requires_current_grant_and_matching_version(client, worker_headers, workspace_id):
    response = client.get(f"/api/v1/worker/workspaces/{workspace_id}?version=1", headers=worker_headers)
    assert response.status_code == 200
    assert "root_path" in response.json()
    stale = client.get(f"/api/v1/worker/workspaces/{workspace_id}?version=0", headers=worker_headers)
    assert stale.status_code == 409

def test_browser_or_external_client_cannot_read_worker_context(client, admin_headers):
    response = client.get(f"/api/v1/worker/workspaces/{workspace_id}?version=1", headers=admin_headers)
    assert response.status_code == 403
```

- [ ] **Step 2: Run protocol tests and confirm missing capabilities fail**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_worker_file_protocol.py tests/test_worker_context_api.py -q; Set-Location ..\worker; .\.venv\Scripts\python.exe -m pytest tests/test_client.py tests/test_main.py -q`

Expected: new tests fail because file capability schemas, context route, and client dispatch do not exist.

- [ ] **Step 3: Implement strict schemas and capability negotiation**

Use Pydantic `ConfigDict(extra="forbid")`; require UUID strings, positive workspace version, slash-normalized relative paths, 64-character lowercase hex digests, exact policy version, and for quarantine a non-empty bounded reason of at most 500 characters. Add all three capability names to registration validation and reject a task when its capability and payload action disagree. Keep existing health-monitor capabilities unchanged.

- [ ] **Step 4: Implement protected context retrieval and Worker dispatch**

The context endpoint must check Worker registration, active execution grant, capability membership, workspace enabled state, exact version, same-host loopback request, and a short context expiry. The response may contain `root_path`, `quarantine_root_path`, and protected patterns only to the Native Worker; it must never enter action audit or external status responses. Worker client must fetch context immediately before execution, cache it only for that task, validate the returned version, and send a structured result with `result_kind`, `side_effect`, `content_sha256`, `size_bytes`, and bounded `error_code`/`error_message`.

- [ ] **Step 5: Run API and Worker tests plus commit**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_worker_file_protocol.py tests/test_worker_context_api.py tests/test_worker_protocol.py tests/test_control_worker.py -q; Set-Location ..\worker; .\.venv\Scripts\python.exe -m pytest tests/test_client.py tests/test_main.py -q`

Expected: all protocol tests pass; a malformed payload is rejected before any executor call, and Worker offline/lease-expired states remain non-success. Commit: `git add apps/api/app/schemas/worker_files.py apps/api/app/services/worker_protocol.py apps/api/app/api/worker.py apps/api/app/main.py apps/worker/agentgate_worker/client.py apps/worker/agentgate_worker/main.py apps/api/tests/test_worker_file_protocol.py apps/api/tests/test_worker_context_api.py apps/worker/tests/test_client.py apps/worker/tests/test_main.py; git commit -m "feat: 增加文件动作 Worker 协议"`.

### Task 5: 实现 Windows 文件检查、隔离、恢复、journal 和崩溃恢复

**Files:**
- Create: `apps/worker/agentgate_worker/filesystem.py`
- Create: `apps/worker/agentgate_worker/quarantine.py`
- Modify: `apps/worker/agentgate_worker/client.py`
- Modify: `apps/worker/agentgate_worker/main.py`
- Test: `apps/worker/tests/test_filesystem.py`
- Test: `apps/worker/tests/test_quarantine.py`
- Test: `apps/worker/tests/test_file_actions_windows.py`
- Create: `scripts/file-action.contract.test.ps1`

**Interfaces:**
- Produces `FileConnector.inspect(context: WorkspaceContext, relative_path: str) -> FileMetadata`.
- Produces `QuarantineService.quarantine(context: WorkspaceContext, action_id: UUID, relative_path: str, expected_digest: str | None) -> QuarantineResult`.
- Produces `QuarantineService.restore(context: WorkspaceContext, entry: QuarantineEntryView) -> RestoreResult`.
- Produces `recover_incomplete_journal(journal_path: Path) -> list[RecoveryNotice]`; recovery must mark uncertain side effects for manual review rather than blindly retrying a move.

- [x] **Step 1: Write unit and real-NTFS acceptance tests**

```python
def test_inspect_returns_metadata_and_sha256_without_content(temp_workspace):
    path = temp_workspace / "notes.txt"; path.write_bytes(b"hello")
    result = FileConnector().inspect(context_for(temp_workspace), "notes.txt")
    assert result.size_bytes == 5
    assert result.content_sha256 == sha256_bytes(b"hello")
    assert not hasattr(result, "content")

@pytest.mark.parametrize("relative", ["../x", r"C:\x", "a:stream", "link.txt", "folder"])
def test_quarantine_rejects_non_file_or_unsafe_target(temp_workspace, relative):
    with pytest.raises(FileActionError):
        QuarantineService().quarantine(context_for(temp_workspace), uuid4(), relative, None)

def test_quarantine_then_restore_preserves_digest_and_never_overwrites(temp_workspace):
    original = temp_workspace / "report.txt"; original.write_bytes(b"stable")
    context = context_for(temp_workspace)
    result = QuarantineService().quarantine(context, uuid4(), "report.txt", None)
    assert not original.exists(); assert result.quarantine_path.exists()
    restored = QuarantineService().restore(context, result.entry)
    assert restored.status == "restored"
    assert original.read_bytes() == b"stable"
```

- [x] **Step 2: Run Worker tests before implementation**

Run: `Set-Location apps/worker; .\.venv\Scripts\python.exe -m pytest tests/test_filesystem.py tests/test_quarantine.py tests/test_file_actions_windows.py -q`

Expected: failures for missing connector/service and for the unimplemented Windows contract script.

- [x] **Step 3: Implement handle-based path and file-type verification**

Resolve the relative path beneath the Worker-provided canonical root, reject any parent component that is a reparse point, open the final target with a read-only handle and no directory access, obtain the final handle path with the Windows API, compare it case-insensitively against the canonical workspace root, reject directories, device files, named pipes, alternate data streams and all reparse points, and only then read metadata/hash. Do not call a shell or construct a shell command. Keep hashing streaming with a bounded buffer and return only size, timestamps, file type and SHA-256.

- [x] **Step 4: Implement same-volume quarantine, restore, journal and result semantics**

Generate the quarantine relative name from action ID and a sanitized relative-path digest, create parent directories beneath the Worker-provided quarantine root, verify the destination is on the same volume, write a journal record before the side effect containing action ID, workspace version, source relative path, destination relative path, expected digest and phase, perform an atomic same-volume move with write-through semantics, hash and verify the quarantined file, then append the completed journal record. On restore, use only the stored entry ID/context, verify the quarantined digest, require the original target to be absent, move back atomically, and return `destination_conflict` if it exists. A repeated action ID or already-restored entry returns the original success result without moving again. If a process stops between journal phases, recovery records `manual_review_required` unless disk facts prove the move did not start or completed exactly as journaled.

```python
class QuarantineService:
    def quarantine(self, context: WorkspaceContext, action_id: UUID,
                   relative_path: str, expected_digest: str | None) -> QuarantineResult:
        raise NotImplementedError

    def restore(self, context: WorkspaceContext, entry: QuarantineEntryView) -> RestoreResult:
        raise NotImplementedError
```

- [x] **Step 5: Run Windows contract, Worker suite, and commit**

Run: `pwsh -NoProfile -File scripts/file-action.contract.test.ps1`

Expected: the script creates a dedicated temp NTFS workspace, verifies protected/unapproved files remain, verifies approved quarantine changes the real disk, verifies restore returns the original SHA-256, verifies duplicate replay is idempotent, then removes only its own temp directory and exits 0. Also run `Set-Location apps/worker; .\.venv\Scripts\python.exe -m pytest -q`. Commit: `git add apps/worker/agentgate_worker/filesystem.py apps/worker/agentgate_worker/quarantine.py apps/worker/agentgate_worker/client.py apps/worker/agentgate_worker/main.py apps/worker/tests/test_filesystem.py apps/worker/tests/test_quarantine.py apps/worker/tests/test_file_actions_windows.py scripts/file-action.contract.test.ps1; git commit -m "feat: 实现 Windows 文件隔离与恢复"`.

### Task 6: 完成审批执行、状态查询、恢复冲突和重启一致性

**Files:**
- Modify: `apps/api/app/api/approvals.py`
- Modify: `apps/api/app/api/runs.py`
- Modify: `apps/api/app/services/file_actions.py`
- Modify: `apps/api/app/control/repositories.py`
- Modify: `apps/api/app/services/worker_protocol.py`
- Test: `apps/api/tests/test_file_action_lifecycle.py`
- Test: `apps/api/tests/test_file_action_recovery.py`
- Test: `apps/api/tests/test_file_action_e2e.py`

**Interfaces:**
- Produces `approve_action(action_id: UUID, admin_id: UUID, expected_version: int) -> ActionStatusResponse` and `deny_action(action_id: UUID, admin_id: UUID, expected_version: int) -> ActionStatusResponse` with optimistic concurrency.
- Produces `get_action_for_client(action_id: UUID, client_id: UUID) -> ActionStatusResponse` with no absolute paths and bounded result size.
- Produces `reconcile_file_action(action_id: UUID) -> ReconciliationResult` for restart/lease recovery.

- [x] **Step 1: Write lifecycle and failure-injection tests**

```python
def test_approval_creates_one_task_and_worker_success_is_terminal(action_client, worker_client):
    action = propose_quarantine(action_client, "demo.txt")
    approved = approve(action["action_id"], expected_version=action["version"])
    assert approved["status"] == "queued"
    task = claim_one_task()
    complete_task(task, {"status": "success", "side_effect": "quarantined",
                         "result_kind": "file_action", "content_sha256": "a" * 64, "size_bytes": 5})
    status = get_action(action["action_id"])
    assert status["status"] == "succeeded"

@pytest.mark.parametrize("crash_point", ["before_move", "after_move_before_report", "after_report"])
def test_crash_recovery_never_blindly_retries_file_move(crash_point, real_workspace):
    result = run_with_injected_crash(crash_point)
    reconciliation = reconcile(result.action_id)
    assert reconciliation.decision in {"complete", "manual_review_required", "retry_safe"}
    assert count_moves(result.action_id) <= 1

def test_restore_conflict_is_visible_and_does_not_overwrite(action_client, real_workspace):
    create_conflicting_original_file()
    response = restore_action(action_client, real_workspace.entry_id)
    assert response["error"]["code"] == "destination_conflict"
    assert response["status"] == "conflict"
```

- [x] **Step 2: Run lifecycle tests before implementation**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_action_lifecycle.py tests/test_file_action_recovery.py tests/test_file_action_e2e.py -q`

Expected: failures for approval-to-task wiring, terminal file result projection, reconciliation and restore conflict mapping.

- [x] **Step 3: Implement approval and optimistic status transitions**

Allow approval only for `pending_approval` actions whose expiry is in the future and whose workspace version still matches. Insert exactly one task under the existing idempotency key and transition to `queued`; stale approval returns `action_version_conflict`. Denial transitions to terminal `denied` without a task. A Worker result must be accepted only for the leased task/action pair, and side-effect certainty must be stored separately from the user-facing status.

- [x] **Step 4: Implement recovery and bounded result projection**

On API or Worker restart, use the existing lease and journal state: `before_move` is safe to retry once; `after_move_before_report` is reconciled from source/destination hashes and becomes succeeded or manual review; uncertain mismatches become `manual_review_required` and stop retries. Status endpoints expose action ID, action version, status, policy decision, Chinese reason, timestamps, approval expiry, relative target, result summary, and audit cursor; they never expose root paths, file content or raw Worker exceptions. Map all failure codes to stable Chinese messages.

- [x] **Step 5: Run API integration and existing regression suite, then commit**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_action_lifecycle.py tests/test_file_action_recovery.py tests/test_file_action_e2e.py tests/test_control_queue.py tests/test_control_worker.py tests/test_approvals.py tests/test_audit.py -q`

Expected: approval, denial, success, conflict, restart, duplicate, lease expiry and browser disconnect tests pass; no existing monitoring/control tests regress. Commit: `git add apps/api/app/api/approvals.py apps/api/app/api/runs.py apps/api/app/services/file_actions.py apps/api/app/control/repositories.py apps/api/app/services/worker_protocol.py apps/api/tests/test_file_action_lifecycle.py apps/api/tests/test_file_action_recovery.py apps/api/tests/test_file_action_e2e.py; git commit -m "feat: 完成文件动作审批和恢复状态机"`.

### Task 7: 重做中文前端主流程和安全演示

**Files:**
- Create: `apps/web/src/pages/SecurityDemoPage.tsx`
- Create: `apps/web/src/pages/ActionsPage.tsx`
- Create: `apps/web/src/pages/ApprovalsPage.tsx`
- Create: `apps/web/src/pages/WorkspacesPage.tsx`
- Create: `apps/web/src/pages/AuditPage.tsx`
- Create: `apps/web/src/api/workspaces.ts`
- Create: `apps/web/src/api/actions.ts`
- Modify: `apps/web/src/components/AppShell.tsx`
- Modify: `apps/web/src/i18n/zh-CN.ts`
- Modify: `apps/web/src/styles/*`
- Modify: `apps/web/src/router/*`
- Test: `apps/web/src/pages/SecurityDemoPage.test.tsx`
- Test: `apps/web/src/pages/ActionsPage.test.tsx`
- Test: `apps/web/src/pages/WorkspacesPage.test.tsx`
- Modify: `apps/web/e2e/*`

**Interfaces:**
- `workspaces.ts` exports `listWorkspaces`, `createWorkspace`, `updateWorkspace`, and `listQuarantineEntries`.
- `actions.ts` exports `listActions`, `getAction`, `approveAction`, `denyAction`, `restoreQuarantineEntry`, and `runSecurityDemo`.
- All API client functions return typed Chinese-safe view models and map error envelopes without displaying raw stack traces.

- [x] **Step 1: Write component and E2E tests for the user-visible safety contract**

```tsx
it("displays the protected-file denial as 未执行", async () => {
  render(<SecurityDemoPage />)
  await user.click(screen.getByRole("button", { name: "开始安全演示" }))
  expect(await screen.findByText("已拒绝，文件未执行任何变化")).toBeVisible()
})

it("keeps approve disabled while Worker is offline", async () => {
  render(<ApprovalsPage />)
  expect(await screen.findByRole("button", { name: "批准并执行" })).toBeDisabled()
  expect(screen.getByText("Worker 离线，批准不会执行文件操作")).toBeVisible()
})
```

E2E must navigate from `/demo` to the protected denial, ordinary-file approval, real quarantine result, and restore result; it must assert Chinese labels and the final disk-backed status returned by the API.

- [x] **Step 2: Run frontend focused tests before implementation**

Run: `Set-Location apps/web; npm.cmd test -- --run src/pages/SecurityDemoPage.test.tsx src/pages/ActionsPage.test.tsx src/pages/WorkspacesPage.test.tsx`

Expected: failures because the new pages, routes and typed clients are absent.

- [x] **Step 3: Implement the typed client and page states**

Create explicit loading/empty/error/success states. The security demo shows three cards: protected file → red `已拒绝/未执行`, ordinary file → amber `待审批`, approved file → green `已隔离` with relative path and digest prefix, then `恢复文件` → `已恢复`. Actions page filters by source/status/risk; approvals page shows target relative path, rule reason, expected side effect, expiry and Worker readiness; workspace page shows root path only to local admin and lists protected rules/quarantine entries; audit page shows a timeline with no sensitive content.

- [x] **Step 4: Implement restrained visual system and Chinese navigation**

Use a light neutral canvas, dark readable text, one blue primary action, amber for approval, red for deny, green for confirmed side effects, 8px spacing scale, responsive two-column desktop layout that collapses to one column, keyboard-focus rings, button labels that describe side effects, and no English fallback strings. Move health monitoring under `系统 > 运行状态`; set primary navigation exactly to `安全演示`, `动作`, `审批`, `工作区`, `审计`, `系统`.

- [x] **Step 5: Run frontend verification and commit**

Evidence: Vitest `15 files / 48 tests passed`, ESLint, TypeScript typecheck, production build, and Playwright `3 passed`; the added `security-demo` browser flow covers protected denial, approval, quarantine, and restore UI states.

Run: `Set-Location apps/web; npm.cmd test -- --run; npm.cmd run lint; npm.cmd run typecheck; npm.cmd run build; npm.cmd run test:e2e`

Expected: unit tests, lint, typecheck, production build and browser E2E pass; browser must show the real API/Worker status and never say “Mock 成功” when the Worker performed the move. Commit: `git add apps/web/src/pages apps/web/src/api apps/web/src/components/AppShell.tsx apps/web/src/i18n/zh-CN.ts apps/web/src/styles apps/web/src/router apps/web/e2e; git commit -m "feat: 增加中文文件治理安全演示界面"`.

### Task 8: 增加一键本地演示、可重复验收和中文项目文档

**Files:**
- Create: `scripts/demo.ps1`
- Create: `scripts/demo.contract.test.ps1`
- Modify: `scripts/verify.ps1`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/demo.md`
- Modify: `docs/architecture.md`
- Modify: `docs/superpowers/progress.md`
- Create: `docs/file-action-governance.md`

**Interfaces:**
- `scripts/demo.ps1` accepts `-ApiPort`, `-WebPort`, `-ResetDemoData`, and `-NoBrowser`; defaults to current configured ports without overwriting `.env` or user data.
- The demo script creates only `%LOCALAPPDATA%\AgentGate\demo-workspace` and a generated `demo-secret.txt`, registers that workspace through the local administrator API, starts/validates the Native Worker, and opens `/demo`.
- `scripts/verify.ps1` gains `-IncludeWindowsFileContract` and runs API, Worker, frontend, protocol, and optional real-disk checks without printing tokens.

- [x] **Step 1: Write script contract tests and documentation acceptance checks**

```powershell
Describe "demo script" {
  It "does not overwrite an existing env file" {
    & $scriptPath -NoBrowser -ApiPort 18230 -WebPort 15173
    $LASTEXITCODE | Should -Be 0
    (Get-Content $envPath -Raw) | Should -Be $originalEnv
  }
  It "prints only redacted connection instructions" {
    $output = & $scriptPath -NoBrowser 2>&1 | Out-String
    $output | Should -Not -Match "ark-[A-Za-z0-9-]{20,}"
    $output | Should -Match "安全演示"
  }
}
```

Documentation acceptance checks must assert that the root README begins with Chinese, includes purpose, prerequisites, one-command start, five-minute demo, external REST example, safety limits, stop conditions, and troubleshooting for ports/Worker/PowerShell execution policy.

- [x] **Step 2: Run script tests before implementation**

Run: `pwsh -NoProfile -File scripts/demo.contract.test.ps1`

Expected: failures because the deterministic demo command and contract assertions are not present.

- [x] **Step 3: Implement idempotent demo orchestration**

Check Python 3.11, Node/npm, Docker Desktop, PostgreSQL/API/Web health and Native Worker registration before creating data. Start Compose with task-specific `AGENTGATE_API_PORT` and `AGENTGATE_WEB_PORT` variables, wait for health endpoints with a bounded timeout, create or reuse only a named demo workspace, write the demo file only under that workspace, and call the API to register it. Store any local demo credential using the existing DPAPI mechanism; never print or commit it. `-ResetDemoData` may remove only the validated demo workspace and its generated records after confirming the path begins with `%LOCALAPPDATA%\AgentGate\demo-workspace`.

```powershell
param(
  [int]$ApiPort = 18230,
  [int]$WebPort = 15173,
  [switch]$ResetDemoData,
  [switch]$NoBrowser
)
```

- [x] **Step 4: Rewrite user-facing documentation in Chinese and update verification**

Explain the real usage in this order: start script, open `/demo`, observe protected denial, approve ordinary quarantine, verify file moved, restore it, inspect audit, then integrate an external Agent using `POST /api/v1/actions` with a relative path and idempotency key. Document that AgentGate does not monitor or block programs that bypass the gateway, does not provide a Windows kernel driver, and does not permanently delete files. Add exact commands for `npm.cmd` on PowerShell and the current-port override; redact all example tokens as `***`.

- [x] **Step 5: Run full verification, contract checks, and commit the delivery layer**

Evidence: demo, Worker, Task Scheduler contracts passed; `docker compose config --quiet` passed; `scripts/verify.ps1 -IncludeWindowsFileContract` passed; all tracked user-facing additions are Chinese and examples redact credentials.

Run: `pwsh -NoProfile -File scripts/demo.contract.test.ps1`; then `pwsh -NoProfile -File scripts/verify.ps1 -IncludeWindowsFileContract`; then `git diff --check`.

Expected: demo script is idempotent, docs are Chinese and accurate, all API/Worker/frontend tests pass, real Windows file contract passes, and no secret-like token appears in tracked files. Commit: `git add scripts/demo.ps1 scripts/demo.contract.test.ps1 scripts/verify.ps1 README.md docs/README.md docs/demo.md docs/architecture.md docs/superpowers/progress.md docs/file-action-governance.md; git commit -m "docs: 增加真实文件治理演示和验收流程"`.

### Task 9: 端到端验收、长时间稳定性测试和面试交付检查

**Files:**
- Modify: `scripts/verify.ps1`
- Modify: `scripts/soak-worker.ps1`
- Create: `scripts/soak-file-actions.ps1`
- Create: `apps/api/tests/test_file_action_contract.py`
- Create: `apps/worker/tests/test_file_action_stability.py`
- Modify: `docs/superpowers/progress.md`

**Interfaces:**
- `scripts/soak-file-actions.ps1` accepts `-DurationMinutes`, `-IntervalSeconds`, and `-WorkspacePath`; it runs inspect, approval/quarantine, status polling, restore, and duplicate replay only inside a generated test subdirectory.
- Contract tests return nonzero on any disk/status mismatch and write redacted JSONL metrics to `data/file-action-soak-*.log`.

- [x] **Step 1: Add contract assertions for the full product promise**

```python
def test_full_contract_rejects_protected_and_unapproved_and_restores_approved_file(action_client, real_workspace):
    protected = propose("file.quarantine.v1", ".env")
    assert protected.status == "denied"
    assert not protected.task_id
    ordinary = propose("file.quarantine.v1", "demo.txt")
    assert ordinary.status == "pending_approval"
    approve(ordinary.id)
    wait_for("succeeded", ordinary.id)
    assert_disk_state("quarantined", "demo.txt")
    restore(ordinary.quarantine_entry_id)
    assert_disk_state("restored", "demo.txt")
```

- [x] **Step 2: Run the full contract once and fix only evidenced failures**

Run: `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_file_action_contract.py -q; Set-Location ..\worker; .\.venv\Scripts\python.exe -m pytest tests/test_file_action_stability.py -q`

Expected: a clean run proves policy state, task state, Worker result, database projection and actual disk state agree for protected, unapproved, approved, duplicate and restore-conflict cases.

- [x] **Step 3: Run a bounded local soak before the long run**

Evidence: 1-minute soak `7/7` passed; 5-minute soak `22/22` passed with zero failures. The actual sample count is recorded rather than claiming an unobserved target count.

Run: `pwsh -NoProfile -File scripts/soak-file-actions.ps1 -DurationMinutes 5 -IntervalSeconds 10 -WorkspacePath "$env:TEMP\AgentGate-file-soak"`

Expected: at least 30 iterations, zero mismatched disk/status assertions, zero duplicate moves, and a redacted JSONL summary.

- [ ] **Step 4: Run the requested long stability test and inspect its evidence**

Status: the independent 24-hour Windows service monitoring soak remains running at `data/worker-soak-eventlog-24h.log`; this item remains open until a file-action long run exits successfully and its log is inspected.

Run: `pwsh -NoProfile -File scripts/soak-file-actions.ps1 -DurationMinutes 60 -IntervalSeconds 30 -WorkspacePath "$env:TEMP\AgentGate-file-soak"`

Expected: the process exits 0 only if every iteration passes; report sample count, failure count, action latency percentiles, Worker reconnects, and final disk verification. A running soak is not a pass until it exits successfully and its log is inspected.

- [x] **Step 5: Run the interview checklist and record final status**

Evidence: full verification passed, including API `256 passed, 6 skipped`, Worker `57 passed, 2 skipped`, frontend `15 files / 48 tests passed`, Playwright `3 passed`, evals, lint/typecheck/build, Compose config, and Windows file-action contract.

Run: `pwsh -NoProfile -File scripts/verify.ps1 -IncludeWindowsFileContract`; inspect `git status --short`; inspect `git diff --check`; inspect the browser E2E screenshot at `/demo`.

Expected: the five-minute demo can be completed without manually copying a token or editing the database; the screen shows a real protected denial, a real approval gate, a real quarantine, a real restore, and an audit trail. Update `docs/superpowers/progress.md` with exact command output summaries and mark only evidence-backed items complete. Commit: `git add scripts/verify.ps1 scripts/soak-file-actions.ps1 apps/api/tests/test_file_action_contract.py apps/worker/tests/test_file_action_stability.py docs/superpowers/progress.md; git commit -m "test: 增加文件动作端到端和稳定性验收"`.

## 验收门槛与停止条件

只有同时满足以下条件才可对外宣称“真实可用”：

1. Windows 专用临时 NTFS 目录中，受保护文件和未审批文件的字节内容保持不变。
2. 获批普通文件确实离开原路径，隔离记录、SHA-256、数据库状态和审计事件一致。
3. 恢复成功不覆盖目标；目标冲突明确失败；同一动作重放不会第二次移动。
4. API 重启、Worker 重启、浏览器关闭和租约过期后，不出现虚假的成功状态或无界重试。
5. 外部 Agent 与 AgentRunner 走同一动作、策略、审批和 Worker 边界；Bearer scope、幂等键和状态读取权限都有测试。
6. 一键演示不要求用户复制令牌、手工改数据库或手工创建内部目录；所有中文页面、错误提示、README 和演示截图一致。

出现以下任一事实，应停止扩展功能并先修复边界：Worker 无法可靠阻止越界/reparse 路径；崩溃后可能无界重试写操作；演示仍需手工令牌/数据库；必须引入内核驱动才能满足承诺；或三至四周后仍未通过真实磁盘端到端验收。
