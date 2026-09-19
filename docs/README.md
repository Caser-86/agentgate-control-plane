# 项目文档与文件导航

本页是 AgentGate 的维护者导航。根目录 [README.md](../README.md) 面向第一次安装和使用项目的人；本页面向需要理解代码边界、修改功能或执行验收的人。

当前事实优先级：先看根目录 [CONTEXT.md](../CONTEXT.md) 和 [TODO.md](../TODO.md)，再看本页列出的正式文档；`docs/superpowers/` 下的规格、计划和旧报告主要用于追溯，不自动代表当前实现。

## 目录职责

```text
agentgate-control-plane/
├─ apps/
│  ├─ api/       FastAPI 控制平面、数据库迁移、策略、工具、队列和 AgentRunner
│  ├─ web/       React/Vite 中文控制台、单元测试和 Playwright E2E
│  └─ worker/    原生 Worker 客户端、journal、vault 和 Worker 测试
├─ docs/
│  ├─ assets/    README 和本地验收使用的截图、静态资源
│  ├─ superpowers/
│  │  ├─ specs/  需求与架构规格
│  │  ├─ plans/  实施计划
│  │  ├─ reports/ 验收和任务报告
│  │  └─ progress.md 当前进度摘要
│  ├─ architecture.md 系统架构、状态机和本地安全边界
│  ├─ demo.md        一键准备和五分钟真实文件验收流程
│  ├─ file-action-governance.md 文件动作、审批、隔离和恢复边界
│  ├─ troubleshooting.md 故障排查和恢复入口
│  ├─ backup-and-recovery.md 备份、预检和恢复边界
│  ├─ release-checklist.md 发布前检查清单
│  ├─ security_best_practices_report.md 全面安全审计、清理和验证报告
│  └─ README.md      本文件
├─ scripts/          Windows 本地启动、迁移、Worker 和验收脚本
├─ compose.yaml      本地服务编排
├─ README.md         项目总览、快速开始、配置和测试命令
├─ CONTEXT.md        当前代码、运行态和已知限制快照
├─ TODO.md           只保留尚未完成的任务
├─ .env.example      后端配置模板
└─ .gitignore        本地密钥、环境、缓存和生成物规则
```

## 文档入口

实施入口：[正式本地版本完成计划（2026-09-11）](superpowers/plans/2026-09-11-project-completion.md)，按 T0–T11 列出执行顺序、文件范围、测试和发布门槛。

最新工程评审见 [正式项目审核与后续路线（2026-09-10）](project-review-and-roadmap-2026-09-10.md)，包含已复现问题、发布门槛和工程量估算。

本轮执行证据见 [正式本地版本执行进度与证据](superpowers/reports/2026-09-11-completion-progress.md)，其中明确区分了已验证、未验证和环境阻塞项。

| 文档 | 适合谁 | 内容 |
| --- | --- | --- |
| [README.md](../README.md) | 使用者、部署者 | 项目用途、启动、登录、功能验收、模型配置和测试 |
| [CONTEXT.md](../CONTEXT.md) | 开发者、评审者 | 当前真实状态、技术栈、架构边界和已知限制 |
| [TODO.md](../TODO.md) | 维护者、开发者 | 按 P0–P3 排列的未完成事项 |
| [architecture.md](architecture.md) | 开发者、评审者 | 组件关系、状态机、审批顺序、事务和幂等边界 |
| [demo.md](demo.md) | 使用者、验收者 | 一键准备 Native Worker，完成真实文件检查、审批、隔离、恢复和审计验收 |
| [file-action-governance.md](file-action-governance.md) | 开发者、评审者 | 文件路径、保护规则、幂等、恢复和系统边界 |
| [troubleshooting.md](troubleshooting.md) | 使用者、维护者 | 启动、认证、Worker、迁移、审批和文件冲突排查 |
| [backup-and-recovery.md](backup-and-recovery.md) | 使用者、维护者 | 数据库、journal、隔离文件备份和安全恢复 |
| [release-checklist.md](release-checklist.md) | 维护者、评审者 | 安装、业务、安全、数据和发布门槛 |
| [security_best_practices_report.md](security_best_practices_report.md) | 历史审计追溯 | 2026-09-04 至 2026-09-10 的安全审计、清理记录和当时证据 |
| `superpowers/specs/` | 产品和架构设计者 | 需求规格与设计决策 |
| `superpowers/plans/` | 开发者 | 分阶段实施计划和文件清单 |
| `superpowers/reports/` | 开发者、评审者 | 任务完成报告、测试证据和限制 |
| `superpowers/progress.md` | 历史追溯 | 2026-09-04 前后的阶段性进度，不是当前状态来源 |
| `superpowers/reports/2026-09-11-completion-progress.md` | 开发者、评审者 | 最近一轮计划执行证据；需结合 `CONTEXT.md` 查看最新运行态 |

## 推荐入口

| 目的 | 入口 |
| --- | --- |
| 第一次启动 | [`README.md`](../README.md) 的“启动本地项目”和 `scripts/setup-local.ps1` |
| 启动/停止服务 | `scripts/start-local.ps1`、`scripts/stop-local.ps1` |
| 准备本地文件治理验收环境 | `scripts/demo.ps1`（仅准备隔离测试工作区，不是产品页面） |
| 手动执行数据库迁移 | `scripts/migrate-local.ps1` |
| 检查本地基础设施 | `scripts/verify-foundation.ps1` |
| 首次注册原生 Worker | `scripts/register-worker.ps1`（本机申请一次性令牌并安全启动） |
| 已有凭据启动原生 Worker | `scripts/start-worker.ps1`（不需要再次提供令牌） |
| 持续运行原生 Worker | `scripts/start-worker.ps1 -Continuous` |
| 安装登录自启动 | `scripts/install-worker.ps1` |
| 移除登录自启动 | `scripts/uninstall-worker.ps1`（保留 Worker 状态） |
| 长时间稳定性测试 | `scripts/soak-worker.ps1`（只读健康检查与已登记目标） |
| 备份和恢复 | `scripts/backup-local.ps1`、`scripts/restore-local.ps1`（先预检，应用需显式停机确认） |
| 查看行为和审批流程 | [`demo.md`](demo.md) |
| 理解系统边界 | [`architecture.md`](architecture.md) |
| 运行 API 单元测试 | `apps/api/tests/` |
| 运行 Web 单元测试 | `apps/web/src/**/*.test.*` |
| 运行 Web E2E | `apps/web/e2e/` |
| 文件动作 Windows 合约 | `scripts/file-action.contract.test.ps1` |
| 外部程序接入 | [`examples/file-client/README.md`](../examples/file-client/README.md) |

## 当前版本边界

Phase 0 的业务工具仍使用本地示例状态表：`get_service_health` 和 `search_logs` 只读取数据库，`restart_service` 只修改数据库中的示例状态，`rotate_api_key` 没有执行处理器。Phase 1 现在还包含受管工作区文件动作：Native Worker 只允许 `inspect`、`quarantine` 和 `restore`，并在 API 策略、审批、同卷隔离和审计边界内执行。监控仍只支持回环 HTTP、固定 `sc.exe query` 和结构化结果，不执行任意命令、服务写入或远程检查。持续模式只会处理已登记目标，不会自主扫描本机。

监控功能的入口是中文 Web 页“监控”，对应 API 路径为 `/api/monitor/targets` 和 `/api/monitor/events`。目标登记、探测排队和查询都要求管理员会话；目标地址和 Windows 服务名在 API 与 Worker 两侧重复校验。

外部 Agent 可以使用 `/api/v1/events`、`/api/v1/checks` 和 `/api/v1/actions`。文件动作会真实进入统一审批和 Worker 队列；其他业务工具仍可能只返回策略预检决定。扩展动作时，必须同步修改工具登记、策略、Worker capability、迁移、测试和架构文档。

## 本地生成内容

以下内容属于本机运行产物，不是业务源码：

- 根目录 `.env`：本地配置和密钥，不提交到 Git。
- `data/`：本地数据库卷或运行数据。
- `apps/api/.venv/`、`apps/worker/.venv/`：两个独立的 Python 环境。
- `apps/web/node_modules/`、`apps/web/dist/`：前端依赖和构建产物。
- `__pycache__/`、测试缓存、Playwright 报告和 `apps/api/eval-results.json`：测试生成物。
- `.superpowers/`：助手的规划/可视化和早期 SDD 历史产物，不属于项目运行时，也不是当前状态来源；仓库内的历史文件暂不删除以保留追溯链。

这些路径已经由根目录 `.gitignore` 统一排除。不要为了“清空项目”删除 `.env` 或 `data/`，除非明确要重置本地环境；删除它们可能导致登录配置或本地数据丢失。

## 修改时的边界

- API 协议、认证、策略和数据库变更：同时检查 `apps/api/app/`、迁移文件和 `apps/api/tests/`。
- Web 页面或中文文案变更：同时检查 `apps/web/src/`、对应测试和必要的 `apps/web/e2e/` 流程。
- Compose、端口或 Windows 脚本变更：同时检查 `compose.yaml`、`scripts/` 和 `apps/api/tests/test_compose_contract.py`。
- 运行流程和安全边界变更：同步更新 `docs/architecture.md`、`docs/demo.md` 及相关验收报告；当前状态只更新 `CONTEXT.md` 和 `TODO.md`，不要把历史报告改写成最新证据。

## 维护建议

- 先读根目录 README 的“当前能力”和“项目不负责什么”，再判断需求是否超出当前本地只读边界。
- 修改 API 请求/响应时，同时更新 schema、路由测试、Web 客户端和文档中的接口表。
- 修改风险策略时，同时更新工具登记表、策略页面、确定性 eval 和本地验收脚本。
- 修改 Compose 或端口时，执行 `docker compose config --quiet` 和 `apps/api/tests/test_compose_contract.py`。
- 不要把 `.env`、bootstrap token、client token、Worker token 或审计敏感数据写入文档。
