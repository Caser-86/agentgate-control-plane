# 最终集成修复进度

## 文件动作治理交付验收 — 2026-09-04

- [x] 交付已提交并推送到 GitHub `master`；当前 HEAD 为 `2a42959`，工作树干净。
- [x] 中文安全演示页面已接入真实工作区、策略拒绝、审批、Native Worker 隔离、恢复和审计入口；浏览器 E2E `3 passed`，其中安全演示覆盖四个中文闭环状态。
- [x] API 全套测试 `256 passed, 6 skipped`；Worker 全套测试 `57 passed, 2 skipped`；API/Worker Ruff、API mypy、前端 ESLint、TypeScript、生产构建和 Compose 配置检查通过。
- [x] Windows 文件动作契约通过；真实磁盘 1 分钟稳定性测试 `7/7` 成功、5 分钟稳定性测试 `22/22` 成功，失败数均为 `0`。日志分别为 `data/file-action-soak-20260904-144540.log` 和 `data/file-action-soak-20260904-144651.log`。
- [x] 修复真实运行中暴露的两个 Windows 问题：Codex AppContainer 工作区的最终句柄边界解析，以及 `MoveFileEx` 标志从 `win32file` 获取；均增加了回归覆盖。
- [x] 一键演示、Worker 启动、Task Scheduler 契约和完整 `scripts/verify.ps1 -IncludeWindowsFileContract` 均通过；脚本不覆盖 `.env`，不打印令牌，只操作明确的本地演示目录。
- [ ] 60 分钟文件动作稳定性测试已后台启动，进程 PID `24584`；完成前不宣称通过。标准输出日志为 `data/file-action-soak-60m.stdout.log`，结束后需检查对应 `data/file-action-soak-*.log` 的样本和失败数。
- [ ] 24 小时 Windows `EventLog` 监控稳定性测试仍在后台运行，日志为 `data/worker-soak-eventlog-24h.log`；此前观测到的最新样本为 `548`，完成前不宣称最终通过。

# 本机服务登记与稳定性测试 — 2026-09-04

- [x] 选择并登记真实 Windows 内置服务 `EventLog`（Windows 事件日志），目标类型为 `windows_service`，周期 10 秒。
- [x] Native Worker 已完成首轮探测，目标状态为 `healthy`，结果为 `Windows 服务 RUNNING`。
- [x] 短时稳定性校验通过：1 分钟、12 次采样、0 次失败。
- [ ] 24 小时稳定性测试已在后台启动；日志为 `data/worker-soak-eventlog-24h.log`，完成前不能宣称最终通过。

# 原生 Worker 持续监控与登录自启动 — 2026-09-04

- [x] Worker 增加 `--loop` 持续模式、可配置轮询/心跳间隔、journal 恢复、任务处理、信号停止和有界退避。
- [x] Windows `start-worker.ps1` 增加 `-Continuous`，并新增当前用户 `AtLogOn` 计划任务安装/卸载脚本；计划任务不保存令牌，卸载不删除 Worker 状态。
- [x] 中文 Web 侧栏复用 `/api/platform/health`，每 10 秒显示本机 Worker 的在线、需要检查或不可用状态。
- [x] 已增加 Worker 循环、PowerShell 脚本契约、API 客户端和 AppShell 状态测试。
- [x] 已使用现有本地 Worker 凭据执行 `install-worker.ps1`，创建并启动当前用户的 `AtLogOn` 计划任务；任务参数未包含令牌，前端显示 Worker 在线。

## 本机免密模式 — 2026-09-03

- [x] 新增 `AGENTGATE_AUTH_ENABLED` 开关；Compose 和当前本机 `.env` 默认关闭 Web 管理员密码。
- [x] 免密模式下 Web 直接进入控制台，浏览器读取、运行、审批、审计和监控接口均可用；使用固定临时本地操作员身份记录审计，不写入密码。
- [x] 外部 Agent Bearer token、原生 Worker enrollment token 和 Worker token 仍保留；API/Web 继续只绑定回环地址。
- [x] 保留密码认证流程；将 `AGENTGATE_AUTH_ENABLED=true` 后重启 `api web` 即可恢复。
- [x] API `208 passed, 6 skipped`，Web `38 passed`，Ruff/mypy/ESLint/typecheck/build/Compose config 全部通过；正式 Compose 已重建并验证免密模式。

## 真实运行验收与 Ark 配置 — 2026-09-03

- [x] 在隔离的本机 SQLite 实例中完成 HTTP 监控闭环：原生 Worker 注册、健康观测、服务停止后的 `failed`/`down` 与活动事件、服务恢复后的 `healthy`/事件关闭。
- [x] 修复带有效期 enrollment token 的 SQLite 时间类型兼容问题；`start-worker.ps1` 现在会正确向上传递 Worker 失败退出码。
- [x] 当前正式 Compose 已使用 `openai_compatible` 提供方，加载 Ark Base URL 和 `ark-code-latest`；真实请求冒烟返回文本成功。
- [x] 此前修复已推送到公共仓库 `master`，当前远端 HEAD 为 `c859429`；本轮配置、文案和错误处理修复尚未提交。
- [ ] 正式 Postgres 实例尚未添加用户自己的监控目标或 Native Worker 凭据；这一步需要在 Web 中使用已设置的管理员密码创建 Worker enrollment token，不能由脚本读取或绕过。

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
## 真实本机只读监控 MVP — 2026-09-03

- [x] 新增本机 HTTP 与 Windows 服务只读目标、观测、状态和事件持久化模型，迁移版本为 `0009_monitoring_mvp`。
- [x] 增加失败/恢复阈值、活动事件去重，以及 `unknown` 探针结果隔离，避免探针故障造成目标误报。
- [x] 扩展 Native Worker 显式能力白名单：`monitor.http`、`monitor.windows_service`；Windows 服务仅固定调用 `sc.exe query`，禁止任意 Shell/PowerShell。
- [x] 增加中文“监控”页面、目标登记、手动探测、周期调度和监控 API。
- [x] 本轮代码级验证已执行；24 小时稳定性测试仍未执行，不能以短时测试结果替代长期验收。
- [x] 本机 Compose 运行验证已通过：`0009_monitoring_mvp` 迁移成功，API `http://127.0.0.1:18230/health` 返回 `200`，Web `http://127.0.0.1:15173` 返回 `200`；启用认证的回归测试仍验证未登录监控 API 返回 `401`。
- [ ] 本次运行使用 `mock` 提供方；Ark 真实模型请求不在本轮启动链路中重复调用。监控的 24 小时稳定性、真实 Windows 服务探针和原生 Worker 长时间运行仍待单独验收。
