# AgentGate 项目现状

更新时间：2026-09-19（Asia/Shanghai）

本文件是继续开发前的项目上下文快照。它只记录当前代码和最近一次实际检查能够证明的事实；历史设计和过程记录见 `docs/superpowers/`，未完成事项见 `TODO.md`。

## 项目目标

AgentGate 是面向 Windows 本机单用户环境的 AI Agent 操作权限网关。外部 Agent 或控制台提交结构化动作后，系统先做参数校验、策略判断和必要的人工审批，再由受限 Native Worker 执行，并保存动作结果、审计记录和幂等证据。

它不是聊天产品、全机监控器、杀毒软件或内核级防误删工具。只有经过 AgentGate API 的动作受控；绕过网关的程序仍可按当前 Windows 用户权限直接操作文件。

## 当前状态

项目已超过页面原型阶段，具备可运行的本地控制平面和真实文件动作闭环，但还不能称为生产版或长期稳定版。

最近一次完整验证（2026-09-16）通过：API `273 passed, 6 skipped`，Worker `62 passed, 2 skipped`，Web `53 passed`，Playwright E2E `3 passed`，Windows 文件动作合约通过。

当前运行态复核（2026-09-19）显示：Docker Compose 的 PostgreSQL、API、scheduler、control-worker 和 Web 均在运行；API、数据库、持久化队列和 outbox 正常，但本机 Native Worker 心跳已过期，因此平台总体为 `degraded`，不能把当前运行态写成完全健康。

最新一次 24 小时监控采样没有通过：`worker-soak-20260916-24h.log` 在 2880 个预期样本中的第 480 个样本处因连续 3 次失败提前结束，覆盖率约 16.67%。此前历史长测也出现过瞬时失败；因此长时间稳定性仍是未完成事项。

## 已实现并有基本验证的功能

- 中文 React/Vite 控制台：运行、动作、审批、文件治理、工作区、监控、审计和系统页面。
- FastAPI 控制平面、PostgreSQL、Alembic 迁移、持久化队列、租约、scheduler、control-worker 和审计事件。
- Mock 与 OpenAI-compatible 模型适配；真实模型只由后端读取配置，不由前端保存 API key。
- `file.inspect.v1`、`file.quarantine.v1`、`file.restore.v1` 文件动作。
- 工作区边界、保护规则、相对路径校验、幂等键、审批状态机、同卷隔离、恢复冲突保护和 Worker journal。
- Windows Native Worker 的本地注册、心跳、任务领取、结构化结果上报、有限退避和持续运行脚本。
- 只读监控：回环 HTTP 地址和 Windows 服务状态；支持周期探测、失败/恢复阈值和活动事件。
- 外部 Python 客户端示例，使用受限 client token 调用正式 API。
- 备份脚本、恢复预检、稳定性采样脚本和统一验证脚本。

## 当前未完成

- 本机 Native Worker 当前没有新鲜心跳，需要使用单一明确的状态目录重新启动并复核持续运行/登录自启动。
- 24 小时稳定性测试需要在保持 Windows 唤醒、只运行一个 Worker 的条件下重新执行，并记录资源增长和失败原因。
- Windows junction/reparse point、文件占用、并发目录变化等原生场景还未形成完整验收证据。
- PostgreSQL 备份已有生成和预检能力，但完整的独立数据库恢复演练尚未完成。
- 外部客户端的真实 token 撤销、过期、跨工作区、重复请求和审批拒绝全链路尚未完成独立验收。
- GitHub Actions 尚未在远程实际运行；干净环境安装、升级和恢复回归尚未完成。
- 监控目标目前有历史失效登记，项目尚无安全的禁用/归档/删除管理接口；不能直接改数据库清理。

## 技术栈

- API：Python 3.11+、FastAPI、SQLModel、Alembic、PostgreSQL、pytest、Ruff、mypy。
- Native Worker：Python 3.11+、httpx、Windows `pywin32`/DPAPI、本地 journal。
- Web：React 19、Vite、TypeScript、Vitest、Playwright。
- 运行：Windows + Docker Desktop + Docker Compose + PowerShell。
- 模型：默认 `mock`；可选 OpenAI-compatible/Ark；模型不是权限边界。

## 核心架构

浏览器和外部 Agent 只调用 API。API 负责认证、参数校验、策略、审批、队列和审计；PostgreSQL 保存控制平面事实；scheduler 负责到期任务和租约清理；control-worker 处理持久化控制任务；Windows Native Worker 只执行授权的本机探针和受管工作区文件动作。

监控是辅助诊断，不等于权限控制。监控目标必须由管理员登记，Worker 不会自动发现整台电脑，也不会自动重启服务或执行任意命令。

## 关键目录

| 路径 | 用途 |
| --- | --- |
| `apps/api/` | FastAPI、数据库、认证、策略、队列、模型适配和 API 测试 |
| `apps/worker/` | Windows Native Worker、journal、文件边界和 Worker 测试 |
| `apps/web/` | 中文 React 控制台、单元测试和 Playwright E2E |
| `scripts/` | Compose、Worker 注册/启动、备份恢复、稳定性和统一验证脚本 |
| `docs/` | 架构、使用、排障、备份、发布和历史设计资料 |
| `examples/` | 不直接读数据库的外部 API 客户端示例 |
| `data/` | 本机运行数据和测试日志，不属于源码，不应随意删除 |

## 关键技术决策

- 默认只绑定 `127.0.0.1`；开发免密只适用于本机自用，不适用于共享网络或生产环境。
- 所有高风险、未知工具和越界文件路径 fail-closed；不增加任意 Shell/PowerShell 执行能力。
- 文件动作只支持检查、隔离和恢复；恢复不覆盖已有目标，状态不确定时进入人工复核，不盲目重放。
- Worker 注册使用一次性令牌换取本机凭据；常驻 Worker 不应把注册令牌放在长期进程参数中。
- 测试必须使用独立临时数据库、目录和 Worker 状态，不覆盖用户 `.env`、`data/` 或现有凭据。

## 已知限制

- 不能拦截未接入 AgentGate 的程序，也不能提供全机防误删或系统级沙箱。
- 当前监控只支持回环 HTTP 和安全格式的 Windows 服务名。
- Mock 只用于确定性验证，不代表真实模型能力；Ark 请求可能产生外部模型费用和数据出站风险。
- 当前工作树仍有未提交修改；本轮文档整理不得使用 reset、覆盖 `.env`、清空数据库或自动推送。

## 下一步顺序

1. 用单一 `worker-live` 状态目录重新启动 Native Worker，确认平台恢复 `ok`，并明确是否安装登录自启动。
2. 在保持系统唤醒的环境中重跑 24 小时只读稳定性测试，失败时保存脱敏证据并分析资源增长。
3. 完成真实 Windows 文件边界、外部客户端权限和 PostgreSQL 恢复演练。
4. 在干净 Windows/Docker 环境运行安装、升级和恢复回归，并实际运行 GitHub Actions。
5. 只有以上关键证据齐备后，才考虑发布版本或继续扩展监控/告警能力。
