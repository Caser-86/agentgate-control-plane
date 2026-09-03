# 最终集成修复进度

## 最终本地端口/Worker 修复轮次 — 2026-09-01

- [x] 在 Compose 回环绑定、API CORS、Vite 开发代理和构建后的 Web 运行时配置之间统一 `AGENTGATE_API_PORT`/`AGENTGATE_WEB_PORT`；安全默认值仍然只允许 localhost，远程目标仍不支持。
- [x] 修复原生 Worker 的启动、准备和验证流程，统一使用 `apps/worker/.venv`，并校验 `win32crypt`/pywin32 和 Compose 推导的 API 回环 URL/端口。
- [x] 增加备用端口、过期构建 URL、Worker 运行时和脚本契约覆盖。
- [x] 最新本地证据：后端 `169 passed, 5 skipped`，Ruff/mypy/evals 通过；前端 lint/typecheck/build 通过，`7 files / 14 tests passed`；Worker `8 passed`；Compose 默认/备用配置和 PowerShell 解析通过。
- [ ] 未启动服务时无法完成 Compose 底座实时验证；有界只读尝试因 API 未运行而在健康检查处失败。未配置 `AGENTGATE_TEST_DATABASE_URL`，PostgreSQL 测试仍保持跳过。

基线目标提交：`70df1d7`（隔离工作树 `codex/reliable-foundation-20260831`）。

## Worker 回环边界与显式 URL 修复 — 2026-09-01

- [x] 原生 `HttpTransport`、`WorkerClient`（包括注入的传输实现）和 `agentgate_worker.main` 现在都会在使用凭据或发起网络请求前校验 API URL；只接受 HTTP(S) localhost/IPv4 回环/IPv6 回环来源。
- [x] `start-worker.ps1 -ApiUrl` 会优先解析、推导并校验 URL 端口；显式传入时不会读取 `ApiPort`、环境变量或 Compose 回退值。
- [x] `verify-foundation.ps1` 通过 `start-worker.ps1` 执行原生 Worker 往返验证，保持相同的 URL 校验路径。
- [x] 最新证据：API `171 passed, 5 skipped`；Worker `19 passed`；API/Worker Ruff 和 API mypy 通过；前端 lint/typecheck/build 通过，Vitest `7 files / 14 tests passed`；默认/备用 Compose 配置、PowerShell 解析、远程 URL 提前拒绝和 `git diff --check` 均通过。
- [ ] Compose 底座实时验证、Docker 镜像构建和 PostgreSQL 运行时测试尚未执行；本轮没有启动或停止服务，也未配置 `AGENTGATE_TEST_DATABASE_URL`。

已完成：

- 原生 Worker grant 增加 `lease_version`；恢复过期租约时，按任务、旧 owner 和旧 lease version 原子删除 stale grant。旧 owner/grant 无法启动或完成，新 owner 可以重新启动并完成。
- 已提交的 check 会保存 submitter，幂等键按 submitter 隔离；状态查询也按 submitter 限定，跨客户端统一返回 404。
- 成功的 check proposal 会在同一事务中写入 accepted audit、`task.queued` Outbox 和任务；观测失败时会回滚任务及事件。
- `platform.self_check` 只接受 `target=local` 且禁止 parameters；文档改为持久化队列/control-worker，并明确 `platform.self_check` capability。
- 验收脚本先检查迁移就绪，再启动原生 Worker self-check。

未完成/限制：

- Compose 第一次运行发现迁移 revision 名超过既有 `alembic_version.version_num VARCHAR(32)`；已将 revision 缩短为 `0007_bound_grants_check_owner`。第二次镜像构建因依赖下载超过 30 秒有界窗口而终止，因此本轮没有宣称修正后的容器迁移/E2E 已通过。
- 工作树未提供可用的 `AGENTGATE_TEST_DATABASE_URL`，PostgreSQL pytest 用例保持跳过。

本轮最终集成修复证据：`apps/api/tests/test_compose_contract.py` 为 `10 passed`；Worker `8 passed`；后端 `165 passed, 5 skipped`；前端 `7 files/13 tests passed`，lint/typecheck/build 退出码 0；Compose config、PowerShell 解析和 diff check 均通过。未启动服务，因此有界 E2E 和底座实时验证未执行。详见 `reports/task-8-report.md`。
