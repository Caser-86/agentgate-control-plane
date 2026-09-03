# 任务 8 最终验证报告

## Worker 边界后续修复 — 2026-09-01

- 原生 Worker URL 校验现在会在客户端两条构造路径和主入口中、使用 bearer/enrollment token 之前执行；直接测试覆盖远程 DNS/IP、非 HTTP(S)、格式错误 URL 以及 IPv6 回环地址的接受行为。
- `start-worker.ps1` 的显式 URL 优先级和 `verify-foundation.ps1` 的委托关系由 API 契约测试覆盖；远程 URL 拒绝测试在未进入 Worker 运行时的情况下完成。
- 最新最终检查：API `171 passed, 5 skipped`；Worker `19 passed`；前端 `7 files / 14 tests passed`；Ruff/mypy、Compose 配置、PowerShell 解析和 diff 检查通过。

限制：没有启动或停止服务；底座实时验证、Docker 构建和 PostgreSQL 运行时测试尚未执行（未设置 `AGENTGATE_TEST_DATABASE_URL`）。

## 验证证据

- 脚本契约覆盖：`10 passed`（`apps/api/tests/test_compose_contract.py`）。它证明三个本地脚本可以解析 Compose 宿主机端口，底座验证选择 `apps/worker/.venv`、检查 `win32crypt`，且不会回退到 `apps/api/.venv`。
- Worker 测试：`8 passed`。本地专用的 `apps/worker/.venv` 已创建，并通过 `pip install -e apps/worker` 安装；`import win32crypt` 成功。
- 后端：`165 passed, 5 skipped`；Ruff：`All checks passed!`；mypy：`Success: no issues found in 53 source files`。
- 前端：lint、typecheck 和 build 退出码为 `0`；单元测试：`7` 个文件、`13` 个测试通过。
- `docker compose config`：退出码为 `0`；Postgres 没有发布端口，API/Web 仍然只绑定回环地址。当 `AGENTGATE_API_PORT=18000`、`AGENTGATE_WEB_PORT=15173` 时，解析出的宿主机端口为 `18000/15173`。
- `start-local.ps1`、`setup-local.ps1`、`verify-foundation.ps1` 的 PowerShell 解析检查以及 `git diff --check` 均退出码为 `0`。

## 限制

- 没有运行有界 E2E 或底座实时验证：这需要启动 Compose 服务，而本任务明确禁止在没有明确有界操作授权时启动/停止用户服务。
- 未配置 `AGENTGATE_TEST_DATABASE_URL`，因此没有可用的 PostgreSQL 运行时测试；现有 PostgreSQL 测试按照各自的 fixture 规则保持跳过。
- 本地 Worker 环境被忽略且只属于本机，不在提交内容中。`setup-local.ps1` 可以幂等地创建或更新该环境，但不会打印 token 内容。

## 最终端口与 Worker 运行时修复轮次 — 2026-09-01

- `AGENTGATE_API_PORT=18000` 和 `AGENTGATE_WEB_PORT=15173` 会生成回环 API/Web 绑定以及匹配的 API CORS/Web 运行时配置；默认端口为 `8000/5173`。
- API 端口/Compose 重点契约：`16 passed`；API 全量：`169 passed, 5 skipped`；Ruff/mypy/evals 通过。Web：lint/typecheck/build 通过，`7 files / 14 tests passed`。Worker：`8 passed`，并成功从 `apps/worker/.venv` 导入 `win32crypt`。
- 未提供 URL/端口时，`start-worker.ps1` 从 `docker compose config --format json` 推导 API 端口，只接受回环 HTTP URL，且不会回退到 `apps/api/.venv`。准备脚本和底座验证使用同一个 Worker 环境，并且不会打印 token 内容。

限制：没有运行 Compose 生命周期。只读底座验证尝试报告 `API health check failed`，因为 Compose API 没有运行；不宣称 Docker 镜像构建、底座实时验证和 PostgreSQL 运行时测试通过。此前的临时有界 E2E 在 `18220/18221` 端口完成，结果为 `2 passed`，结束后端口已清理。
