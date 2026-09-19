# AgentGate 正式本地版本执行进度与证据

更新时间：2026-09-19 12:55（Asia/Shanghai）

本报告记录“正式本地版本完成计划”的实际执行情况。代码已经写入工作树，但“已验证”只表示对应命令在当前环境真实执行并成功；未运行的 Docker、PostgreSQL、浏览器或长时间测试不会被记为通过。

## 基线

| 项目 | 记录 |
| --- | --- |
| 基线提交 | `94569fd9c137c944bbf63c72969decffd274d8bb` |
| Python | API/Worker 虚拟环境均为 Python 3.14.6；项目支持范围为 3.11+ |
| Node.js | v24.18.0 |
| Docker CLI | 29.7.2 |
| PowerShell | 7.6.5 |
| Docker Server | 29.7.2；当前 Compose Engine 可用 |
| 工作树 | 存在用户已有修改和本轮未提交修改；本轮未执行 reset、清空 data、commit 或 push |

## 本轮已验证

### 2026-09-19 文档同步前复核

- Docker Compose 的 PostgreSQL、API、scheduler、control-worker 和 Web 均在运行；API、数据库、队列和 outbox 正常。
- 当前 `/api/platform/health` 为 `degraded`，原因是 Native Worker 心跳过期；这不是 API 存活检查通过后可以忽略的状态。
- `data/worker-soak-20260916-24h.log` 已有结束记录：预期 2880 个样本，实际 480 个样本，覆盖率 16.67%，连续 3 次失败后结果为 `FAILED_EARLY`。因此 24 小时稳定性测试未通过，需要重新执行。
- 当前没有发现把 enrollment token 留在 `worker-live` 常驻 Worker 参数中的进程；旧状态目录和用户数据未清理或覆盖。
- 文档整理新增根目录 `CONTEXT.md` 和 `TODO.md`，并将当前运行态、长期测试结果与历史报告明确分开。

### 2026-09-16 运行与全量验证（历史证据）

- Docker Engine 已恢复；`docker compose ps` 显示 PostgreSQL、API、scheduler、control-worker、Web 均在运行，API 与 PostgreSQL 为 healthy。
- 真实 HTTP 冒烟通过：API `/health`、`/api/meta`、`/api/auth/status`、`/api/platform/health` 与 Web 首页均返回成功；Native Worker 注册后平台整体恢复为 `ok`，API、数据库、队列、outbox 和 Worker 均正常。
- 当前数据库中的 4 个监控目标仍未直接删除：Windows 事件日志服务为 `healthy`；EchoDesk 后端和历史登记的 AgentGate API 目标为 `down`；其状态由 Native Worker 的真实探测结果更新，未把历史 healthy 当作当前成功。
- 全量验证第一次暴露出 E2E 端口冲突：验证脚本曾固定占用 Compose 的 `18000`。已改为从专用范围动态分配 3 个连续 API 端口和 3 个连续 Web 端口，并增加端口契约测试。
- 通过 `register-worker.ps1` 使用新的本机状态目录完成 Native Worker 配对；注册流程采用一次性短进程注册、无令牌的常驻进程两阶段设计，旧状态目录保持不变；之前遗留的令牌进程已清理。
- 当时启动了 24 小时稳定性采样，目标为 Windows 事件日志服务；该次采样后来因连续失败提前结束，结果见 2026-09-19 复核。

| task | 命令/范围 | 结果 |
| --- | --- | --- |
| 全量项目验证 | `pwsh -NoProfile -File scripts/verify.ps1 -IncludeWindowsFileContract` | 通过；后端 273 passed、6 skipped；Worker 62 passed、2 skipped；Web 53 passed；E2E 3 passed |
| E2E 端口回归 | `scripts/verify-e2e-port.contract.test.ps1` | 通过；会拒绝旧的 Compose API 端口固定配置 |
| 真实 Compose 状态 | `docker info`、`docker compose ps` | Server 29.7.2；5 个服务运行，API/PostgreSQL healthy |
| 真实 HTTP 冒烟 | API 18000、Web 5173 | API/Web 返回成功；平台状态 `ok`，Worker 状态 `ok` |
| Native Worker 真实注册 | `scripts/register-worker.ps1 -ApiUrl http://127.0.0.1:18000 ...` | 注册成功并持续发送心跳；平台状态恢复为 `ok` |
| 稳定性短测 | 1 分钟、15 秒间隔、Windows 事件日志服务 | `PASSED`；4/4、100% 覆盖、0 failures |
| 稳定性长测 | `scripts/soak-worker.ps1`，24 小时、30 秒间隔 | `FAILED_EARLY`；480/2880，覆盖率 16.67%，连续 3 次失败 |

### 2026-09-15 环境复核

- 当前工作区仍是共享 `master` 检出，存在本轮和历史未提交修改；没有执行 reset、清理 data、commit 或 push。
- Docker context 仍指向 `desktop-linux`；`docker-desktop` WSL 发行版已被唤起为 `Running`，但 Docker Engine 管道仍不存在。
- Docker Desktop 的 `com.docker.service` 为 `Stopped`，当前权限无法打开该服务；未继续请求管理员权限，也未停止或修改其他项目。
- 因 Docker Engine 不可用，本次没有把 Compose、PostgreSQL、API/Web 运行态或浏览器结果重新记为通过；9 月 12 日成功启动的证据仍保留在下表，代表历史验证，不代表当前在线。

| task | 命令/范围 | 结果 |
| --- | --- | --- |
| T1/T4 API 定向 | `apps/api/.venv/Scripts/python.exe -m pytest -q tests/test_platform_checks.py tests/test_worker_protocol.py tests/test_file_action_lifecycle.py` | 23 passed, 1 skipped |
| API 全量 | `apps/api/.venv/Scripts/python.exe -m pytest -q` | 272 passed, 6 skipped |
| T1–T3 Worker | `apps/worker/.venv/Scripts/python.exe -m pytest -q` | 62 passed, 2 skipped |
| Worker 质量 | Worker ruff、mypy | 通过，无类型错误 |
| Web 局部 | lint、typecheck、`AppShell.test.tsx` | 通过，4 tests passed |
| Web 全量 | `npm.cmd test -- --run`、lint、typecheck、build | 16 个测试文件、53 tests passed；其余通过，Vite 构建成功 |
| Web E2E | `AGENTGATE_E2E_PYTHON=apps/api/.venv/Scripts/python.exe npm.cmd run test:e2e`（隔离 18200–18202 / 15273–15275） | 3/3 通过；审批、认证队列、文件治理 |
| Compose 真实启动 | `$env:AGENTGATE_API_PORT='18000'; pwsh -NoProfile -File scripts/start-local.ps1` | 构建、迁移、API、scheduler、control-worker、Web 均成功启动；API 端口避开其他项目占用的 8000 |
| 真实 HTTP 冒烟 | `http://127.0.0.1:18000/health`、`/api/meta`、`/api/auth/status`、`/api/platform/health`、`http://127.0.0.1:5173/` | API/Web 返回成功；健康接口识别 Worker 心跳陈旧，未误报为正常 |
| Compose 配置 | `docker compose config --quiet` | 通过 |
| Windows 启动合约 | `scripts/start-local.contract.test.ps1` | 通过 |
| 稳定性脚本合约 | `scripts/soak-worker.contract.test.ps1` | 通过 |
| 备份恢复脚本合约 | `scripts/backup-restore.contract.test.ps1` | 通过 |
| PowerShell 语法 | 启动、安装、验证、稳定性及启动合约脚本 | 解析通过 |
| 外部客户端 | 合约测试、Python 编译、lint、回环配置检查和 `--help` | 通过；远程 URL 被拒绝 |
| 备份恢复 | 临时 SQLite 快照生成、manifest 摘要预检 | 通过；无隔离目录时正确标记 `完整性=False` |
| 确定性评测 | `apps/api/.venv/Scripts/python.exe -m app.evals.runner` 单独重跑 | 6/6 场景 4/4 PASS |

说明：一次与 API 全量测试并行的评测曾出现“拒绝后再次进入待审批”的瞬态失败；随后单独运行评测已通过，当前未把并行运行当作稳定性证据，后续 CI 仍按独立 job 执行。

## 已落地的代码改进

- Worker HTTP 错误保留状态码和安全错误码；补报拒绝时保留本地结果并进入 `reconciliation_required`，不静默丢弃、不盲目重放。
- 隔离和恢复日志使用独立操作标识；恢复中断记录不会被同一动作的隔离完成记录抵消。
- Worker 心跳上报执行状态、待补报数量和最后错误码；平台健康检查和控制台可以区分“在线”与“可执行”。旧 Worker 未上报新字段时显示 `unknown`。
- 系统页展示 API、数据库、队列、事件箱和 Worker 的中文运行诊断，区分心跳状态、执行状态、待补报数量和对账阻塞，并提供手动刷新与失败提示。
- 前端客户端和外部提议接口的常见拒绝错误统一为中文；保留稳定错误码，避免把后端英文内部文案直接显示给使用者。
- Windows 文件边界增加根目录、隔离目录和祖先目录的重解析点检查；现有路径治理仍不承诺对绕过网关的进程提供全机拦截。
- Compose 服务增加自动重启；启动脚本检查 Compose 配置、启动退出码、必需服务和 API 健康状态。
- API/Worker 增加运行时和开发依赖锁；Docker API 镜像和本地 Worker 安装使用锁文件。
- 增加不读数据库、只通过正式 API 的 `examples/file-client` 外部客户端。
- 稳定性脚本现在使用单调时钟、覆盖率、最大间隔、探测新鲜度和区分退出码，不再把不连续样本误判为通过。
- 全量验证脚本的 E2E 服务改用动态空闲端口范围，避免项目已启动时因复用 `18000` 业务端口而无法测试；对应契约测试已加入工作树。
- 增加 `scripts/register-worker.ps1`，把本机 Worker 首次注册封装为回环 API、本地环境变量传递和不覆盖旧凭据的安全流程。
- 修复稳定性脚本对带 `Z` 时间的 UTC 解析，以及短时长采样的覆盖率基准；避免把新鲜探测误报为陈旧或把完整短测误判为证据不足。
- E2E API 使用独立启动器过滤 Windows 下预期的 `10054` 客户端断开异常，保留其他未预期异常；新增评测隔离回归，确保评测恢复路径不读取 Ark 运行时配置而产生非确定性结果。

## 尚未验证或未完成

### 当前仍需补齐

- Docker Server 当前可用并完成 Compose/HTTP/E2E 验证；最近一次长时间稳定性观察提前失败，不能记为通过。
- 初次真实启动使用默认 `8000` 时被机器上其他项目的 `sales-backend` 占用而失败；未停止该项目，改用空闲 `18000` 后启动成功。默认端口冲突处理仍需在正式文档中提示。
- CI YAML 已增加 PostgreSQL 和 Windows Worker job，但尚未在 GitHub Actions 远程运行，不能把 YAML 存在当作 CI 通过。
- Windows junction/reparse point、文件占用和真实 Native Worker 文件动作还需要在支持的 Windows 工作区执行；单元测试通过不等同于这些原生场景已验收。
- 旧 `.demo-worker` 和默认 `worker` 状态目录仍未清理或覆盖；本次使用独立 `worker-live` 状态目录完成了真实注册。当前复核时没有新鲜 Worker 心跳；重新启动前应明确只使用一个状态目录，不能让两个 Worker 共用或盲目替换凭据。

### 计划中的后续工作

- T7：脚本和预检基础已落地；仍需 PostgreSQL 恢复流程、含隔离目录/journal 的独立恢复演练和完整性通过证据。
- T8：外部客户端代码和安全合约已落地；仍需有效的 Worker 注册凭据和受限客户端凭据，完成真实外部动作全链路，并验证撤销令牌、跨工作区、审批拒绝和重复请求。
- T9：故障排查手册和系统运行状态页已落地；仍需逐页检查加载、空、失败和权限状态，并走查首次使用流程。
- T10：短时实际稳定性已通过，但最近一次 24 小时观察 `FAILED_EARLY`；仍需分析失败原因、保持系统唤醒后重跑，并核对完整覆盖率和资源增长记录。
- T11：干净环境安装、升级/恢复回归、发布清单和变更日志。许可证及远程发布仍需单独授权。

## 证据格式

后续每项验证继续记录：

```text
task_id / commit / command / exit_code / result / skipped_reason / artifact_path
```

当前生成的测试报告、缓存、token、数据库和日志不应加入 Git；本报告不包含令牌、密码、API key、绝对凭据路径或工作区文件内容。
