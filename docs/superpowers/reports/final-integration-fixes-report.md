# 最终集成修复验证报告

## 当前最终验证 — 2026-09-01

本节是当前结论。如果下文较早的限制说明描述的是尚未重新运行的检查，应以本节为准。

### 审查后的修复

- Worker 注册现在通过原子条件 `UPDATE` 消费注册凭据；并发竞争失败的一方会收到 `invalid_enrollment_token`，注册失败时会同时回滚凭据消费和 Worker 行。
- Operator 现在携带唯一的 `installation_key`；迁移 `0008_operator_installation_key` 拒绝静默迁移多个历史 Operator，初始化会在回滚后把数据库唯一性冲突映射为 `setup_already_completed`。

### 最新验证证据

- API：`175 passed, 6 skipped`；对 `app` 执行 Ruff 通过；mypy 对 53 个源文件检查通过；确定性评测共 6 个场景，全部 `4/4 PASS`。
- Worker：`20 passed`；Worker 源码 Ruff 通过。
- Web：Vitest `28 passed`；lint、typecheck 和生产构建通过。
- Playwright：在临时 API 端口 `18220/18221` 上 `2 passed`，包含中文首次登录以及审批/审计流程。
- Docker：完整 `docker compose build` 通过；`docker compose config --quiet` 和 PowerShell 契约检查通过。
- 使用新的 PostgreSQL 卷，在 loopback 端口 `18390/18391` 上运行的隔离 Compose 栈通过 `verify-foundation.ps1`。数据库报告的迁移头为 `0008_operator_installation_key`，并存在 `ix_operators_installation_key`；容器内双线程注册竞争最终恰好产生一条成功注册和一条 `invalid_enrollment_token`。

6 个跳过的 API 测试是需要 `AGENTGATE_TEST_DATABASE_URL` 的 PostgreSQL fixture 测试。上面的隔离 PostgreSQL Compose 迁移、基础往返流程和注册竞争提供了真实数据库证据；由于未配置一次性测试 URL，标准 fixture 仍按规则跳过。

## Worker loopback 边界与显式 URL 修复 — 2026-09-01

### 变更

- 新增一套共享的原生 Worker URL 策略，在使用默认传输或注入传输之前，由 `HttpTransport` 和 `WorkerClient` 共同执行。该策略接受 HTTP(S) `localhost`、IPv4 loopback 和 IPv6 loopback；拒绝格式错误的 URL、不安全的 scheme/host、URL 凭据、query/fragment、path 以及无效端口。
- 新增 Worker client 和主入口回归测试，证明不安全 URL 会在调用 `httpx.request` 之前失败；同时将进程内故障注入 fixture 更新为使用文档规定的 loopback URL。
- 修改 `start-worker.ps1`：优先解析显式 `-ApiUrl`，并从中推导和校验端口，不再查询 `-ApiPort`、环境变量或 Compose fallback。`verify-foundation.ps1` 现在通过该脚本执行原生往返流程。

### 最新验证证据

- Worker：`19 passed`；Worker Ruff：`All checks passed!`。
- 后端：`171 passed, 5 skipped`；API Ruff：`All checks passed!`；mypy：`Success: no issues found in 53 source files`。
- 前端：lint/typecheck/build 退出码为 `0`；Vitest：`7` 个文件、`14` 个测试通过。
- Compose 默认端口和备用端口（`18000`/`15173`）配置检查退出码为 `0`。
- `start-worker.ps1` 和 `verify-foundation.ps1` 的 PowerShell 解析检查退出码为 `0`；有界脚本执行在 Worker 运行时/网络使用之前拒绝了 `http://example.com:8000`。
- `git diff --check` 退出码为 `0`。

### 限制

- 没有启动或停止 Compose 服务，因此不宣称 live `verify-foundation.ps1`、Docker 镜像构建、有界浏览器 E2E 和 PostgreSQL 运行时测试通过。
- 由于未配置 `AGENTGATE_TEST_DATABASE_URL`，PostgreSQL 测试仍然跳过。

## 修复范围

针对最终审查中的 Worker grant 恢复、check submitter 隔离、check proposal 观测原子性，以及 self-check 安全边界完成修复；本轮补齐了原生 Worker 环境与可变 Compose host 端口集成。未执行真实宿主机动作。

## 验证证据

- 后端重点测试：`33 passed, 4 skipped`（后续包含全部相关回归：`29 passed, 2 skipped`）。
- 后端完整测试：`163 passed, 5 skipped`。
- Ruff：`All checks passed!`。
- mypy：`Success: no issues found in 53 source files`。
- 前端 lint/typecheck/unit/build：lint、typecheck、build 退出码为 0；`7` 个 test files、`13` 个 tests passed。
- 确定性评测：`6` 个 cases，全部 `4/4 PASS`。
- `docker compose config`：成功；loopback API/Web、未发布的 Postgres 端口和迁移依赖均保留。
- `AGENTGATE_API_PORT=18000`、`AGENTGATE_WEB_PORT=15173` 的 Compose 配置覆盖验证成功；三个本地脚本从 `docker compose config --format json` 读取实际 loopback host 端口，健康检查使用推导出的 API 端口。
- 原生 Worker 固定使用本地-only `apps/worker/.venv`，安装 `apps/worker` editable 依赖并验证 `win32crypt`；契约测试证明不会静默使用 API-only `.venv`。
- 首次 Compose 构建完成，但 migrate 因 revision 长度超过 `VARCHAR(32)` 失败；已修正 revision。第二次 Docker 构建在 30 秒有界窗口内仍处于依赖下载阶段，随后终止，未将其记录为通过。
- 未配置可用的 disposable PostgreSQL 测试 URL，因此 PostgreSQL 并发/迁移用例按测试自身规则跳过。

## 限制

本报告不宣称修正后的 Compose migration、有界浏览器 E2E、实时 `verify-foundation.ps1` 或一次性 PostgreSQL 已通过；本轮未启动用户服务，且需要隔离 Postgres 与可控运行态后重新运行。详细任务 8 证据见 [task-8-report.md](task-8-report.md)。

## 最终端口与 Worker 运行时修复轮次 — 2026-09-01

- 新增统一的本地端口契约：`AGENTGATE_API_PORT`/`AGENTGATE_WEB_PORT` 默认值为 `8000`/`5173`；Compose 发布 loopback 端口，API 推导 CORS origins，Vite 推导 dev proxy/API base，构建后的 Web 镜像根据 `AGENTGATE_API_BASE_URL` 写入运行时 API base。
- 备用端口/配置/客户端回归覆盖：`16 passed`；渲染出的 `18000/15173` 值在发布端口、API Web 端口和 Web 运行时 API URL 之间保持一致。
- `start-worker.ps1` 现在使用 `apps/worker/.venv`，校验 `win32crypt`，从渲染后的 Compose 配置推导 API 端口，并拒绝非 loopback URL。Setup 校验相同环境；`verify-foundation.ps1` 使用该脚本且从不打印令牌内容。
- 最新后端：`169 passed, 5 skipped`；Ruff/mypy/evals 通过。最新前端：lint/typecheck/build 通过；Vitest `7 files / 14 tests passed`。Worker：`8 passed`，并通过 `win32crypt` 导入检查。默认/备用 Compose 配置、PowerShell 解析和 `git diff --check` 均通过。

限制：没有启动或停止 Compose 服务。一次只读的 `verify-foundation.ps1` 尝试在 API 健康检查阶段失败，因为栈未运行；不宣称基础流程 live 验证、Docker 镜像构建或 PostgreSQL 运行时测试通过。此前的临时有界 E2E 已在 `18220/18221` 上完成，结果为 `2 passed`。
