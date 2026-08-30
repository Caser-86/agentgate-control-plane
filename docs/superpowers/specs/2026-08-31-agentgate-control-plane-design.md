# AgentGate — Human-in-the-loop Agent Action Control Plane

**Status:** Approved for planning  
**Date:** 2026-08-31  
**Target repository:** `agentgate-control-plane`（独立新仓库）  
**Target roles:** AI 应用 / Agent 工程师、全栈开发  
**Delivery window:** 3–5 天  
**Deployment target:** 本地演示；允许依赖稳定网络与 OpenAI-compatible 模型 API

## 1. 产品定位

AgentGate 是一个面向自主 Agent 的本地优先操作控制平面。它不负责“替用户搜索更多资料”，而是控制 Agent 在调用真实工具时能做什么、何时必须等待人工批准，以及事后如何完整审计。

演示中的运维 Agent 可以自动读取服务健康状态和日志；提出重启服务时进入人工审批；尝试轮换 API Key 时被策略直接拒绝。批准或拒绝后，Agent 从持久化检查点继续执行，所有决策和结果进入不可变审计时间线。

一句话介绍：

> A local-first control plane that makes autonomous agent actions observable, policy-governed, approval-gated, resumable, and auditable.

## 2. 为什么必须是新项目

该项目应创建为独立仓库，而不是改造 `realtime-ai-intel-warehouse`：

- 当前仓库的产品语义、README、截图和 Git 历史都围绕“行业情报采集与报告”。
- AgentGate 的核心对象是 run、tool action、policy decision、approval 和 audit event，领域模型完全不同。
- 新仓库能形成清晰的面试叙事：这是一个 Agent 基础设施与全栈控制产品，不是原项目换皮。
- 3–5 天内从现有仓库拆除无关业务代码的成本，高于搭建一个边界清晰的新项目。

## 3. 与现有 GitHub 项目的差异边界

| 已有项目类型 | 已覆盖能力 | AgentGate 明确不重复的部分 | AgentGate 新能力 |
|---|---|---|---|
| InsightGraph | 多 Agent 深度研究、证据链、报告、任务观测与评测 | 不做搜索、研究编排和报告生成 | 工具调用治理、人工审批、暂停/恢复、审计 |
| 情报仓 / 公司分析 | 数据采集、行业或公司洞察 | 不做通用采集管线和情报看板 | 面向任意 Agent 的动作控制层 |
| AI 客服平台 | RAG、会话、人工接管、租户后台 | 不做知识库问答和客服工作台 | 针对工具动作而非聊天会话的策略决策 |
| 会议 / 招生 / 故事 Agent | 特定业务 Agent | 不再增加另一个垂直领域助手 | 可复用的 Agent runtime governance 基础设施 |
| 预测 / PPT / 文档工具 | BI 或内容生产 | 不做预测和文档生成 | 运行状态机、审批队列、幂等执行与审计 |

为避免后续范围漂移，MVP 禁止加入通用网页搜索、RAG、知识图谱、深度研究、报告生成、会议助手或客服能力。

## 4. 面试价值

项目同时展示两类岗位所需能力：

- Agent 工程：原生 tool calling 循环、结构化工具协议、风险策略、guardrails、检查点恢复、确定性 eval。
- 后端工程：状态机、事务一致性、幂等键、超时、审计、REST 与 SSE。
- 前端工程：运行控制台、实时事件流、审批交互、策略与审计视图。
- 工程化：类型契约、测试分层、CI、Docker Compose、本地启动脚本和演示剧本。
- 产品判断：在自主性与安全性之间建立明确边界，而不是只做一个聊天框。

设计方向与当前 Agent 工程关注点一致：OpenAI 的 Agent 指南强调工具风险评级、guardrails 和高风险动作的人类介入；Anthropic 的 Agent eval 文章强调任务、轨迹、结果状态和评测 harness。参考资料：

- [OpenAI — A practical guide to building AI agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- [OpenAI — Full Stack Software Engineer, Agent Enablement](https://openai.com/careers/full-stack-software-engineer-agent-enablement-san-francisco/)
- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

## 5. MVP 演示故事

本地系统预置 `payments-api`，初始状态为 `degraded`。用户输入：

> Investigate payments-api and restore it safely. Do not rotate credentials.

期望流程：

1. Agent 调用 `get_service_health`，系统自动批准并返回 `degraded`。
2. Agent 调用 `search_logs`，系统自动批准并返回可解释的模拟错误。
3. Agent 提议 `restart_service`，策略判定为 medium risk，run 进入 `waiting_approval`。
4. UI 实时出现审批卡，显示工具、参数、风险、策略理由和影响。
5. 用户批准，工具只执行一次，run 从检查点恢复。
6. Agent 再次检查健康状态并完成任务。
7. Audit 页面显示从用户请求、模型提议、策略决策、人工批准、工具执行到最终结果的完整时间线。

第二条短演示输入：

> Rotate the API key for payments-api.

`rotate_api_key` 被 high-risk 策略直接拒绝，工具不得执行。

## 6. 范围

### 6.1 MVP 必须完成

- 创建并查看 Agent runs。
- OpenAI-compatible 模型 tool calling；默认支持火山方舟兼容端点。
- 确定性的 `MockLLMProvider`，供测试、CI 和离线演示使用。
- 仅允许注册工具，禁止任意 shell、文件或网络工具。
- 基于工具元数据的低/中/高风险策略。
- 自动批准、等待审批、直接拒绝三种策略结果。
- 审批后持久化恢复 Agent loop。
- REST 写操作与 SSE 运行事件流。
- SQLite 持久化、唯一幂等键、重复审批冲突保护。
- 敏感字段脱敏后的追加式审计日志。
- Runs、Run detail、Policies、Audit 四个 UI 页面。
- 确定性 eval、后端测试、前端组件测试、一个 Playwright 主流程。
- 一条命令启动、本地演示文档、架构说明和 CI。

### 6.2 MVP 明确不做

- 用户登录、RBAC、多租户和团队协作。
- 云部署、Kubernetes、分布式队列和多实例 SSE。
- MCP 市场、任意第三方插件或任意代码执行。
- 可视化策略编辑器；MVP 策略由代码注册并通过 API 只读展示。
- 通用 RAG、网页搜索、知识图谱、长篇报告生成。
- 对真实基础设施执行重启或密钥轮换；所有运维工具只操作本地模拟环境。
- 多 Agent 协作；MVP 只有一个清晰可解释的 tool-calling loop。

## 7. 技术方案

### 7.1 技术栈

- Backend: Python 3.11+、FastAPI、Uvicorn、SQLModel、SQLite、Pydantic v2、pydantic-settings。
- LLM: `openai` Python SDK 的 `AsyncOpenAI`，接入 OpenAI-compatible API；不引入 LangChain/LangGraph。
- Frontend: React 19、TypeScript、Vite、React Router、原生 CSS variables。
- Realtime: FastAPI `StreamingResponse` 实现 SSE；审批使用 REST。
- Tests: pytest、pytest-asyncio、HTTPX、Vitest、React Testing Library、Playwright。
- Quality: Ruff、mypy、ESLint、TypeScript strict mode。
- Local packaging: Docker Compose，同时保留 PowerShell 原生启动脚本。

选用 SSE 而不是 WebSocket，因为事件只需服务端推送，审批本身可由普通 POST 完成。这个选择减少状态同步复杂度，同时保留实时产品体验。

### 7.2 仓库结构

```text
agentgate-control-plane/
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── db.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── repositories.py
│   │   │   ├── policy.py
│   │   │   ├── api/
│   │   │   │   ├── health.py
│   │   │   │   ├── runs.py
│   │   │   │   ├── approvals.py
│   │   │   │   ├── audit.py
│   │   │   │   └── policies.py
│   │   │   ├── llm/
│   │   │   │   ├── base.py
│   │   │   │   ├── mock.py
│   │   │   │   └── openai_compatible.py
│   │   │   ├── services/
│   │   │   │   ├── agent_loop.py
│   │   │   │   ├── approvals.py
│   │   │   │   ├── audit.py
│   │   │   │   ├── events.py
│   │   │   │   ├── executor.py
│   │   │   │   └── runs.py
│   │   │   └── tools/
│   │   │       ├── base.py
│   │   │       ├── operations.py
│   │   │       └── registry.py
│   │   └── tests/
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       ├── src/
│       │   ├── api/client.ts
│       │   ├── components/
│       │   ├── pages/
│       │   ├── App.tsx
│       │   ├── types.ts
│       │   └── styles.css
│       └── e2e/approval-flow.spec.ts
├── docs/
│   ├── architecture.md
│   └── demo.md
├── scripts/
│   ├── start-local.ps1
│   ├── stop-local.ps1
│   └── verify.ps1
├── .env.example
├── .gitignore
├── compose.yaml
├── README.md
└── .github/workflows/ci.yml
```

### 7.3 核心数据模型

`AgentRun`

- `id: UUID`
- `user_request: str`
- `status: queued | running | waiting_approval | completed | failed | cancelled`
- `provider: str`
- `model: str`
- `step_count: int`
- `conversation_json: str`，保存可恢复的模型消息检查点
- `created_at / updated_at: datetime`
- `error_message: str | None`

`ToolAction`

- `id: UUID`
- `run_id: UUID`
- `tool_call_id: str`
- `tool_name: str`
- `risk_level: low | medium | high`
- `policy_decision: auto_approve | require_approval | deny`
- `status: proposed | auto_approved | pending_approval | approved | denied | running | succeeded | failed | expired`
- `arguments_json / result_json: str`
- `reason: str`
- `idempotency_key: str`，唯一约束，格式为 `{run_id}:{tool_call_id}`
- `created_at / decided_at / executed_at: datetime | None`

`AuditEvent`

- `id: UUID`
- `run_id: UUID`
- `action_id: UUID | None`
- `event_type: str`
- `actor: user | agent | policy | tool | system`
- `payload_json: str`，写入前脱敏
- `created_at: datetime`

`ServiceState`

- `service: str`，主键
- `health: healthy | degraded | down`
- `restart_count: int`
- `last_restart_at: datetime | None`

### 7.4 核心接口

```python
class PolicyEngine:
    def evaluate(self, tool: ToolSpec, arguments: dict[str, object]) -> PolicyResult: ...

class ToolRegistry:
    def get(self, name: str) -> RegisteredTool: ...
    def schemas(self) -> list[dict[str, object]]: ...

class ToolExecutor:
    async def execute(self, action_id: UUID) -> ToolAction: ...

class AgentRunner:
    async def start_run(self, user_request: str) -> UUID: ...
    async def resume_run(self, run_id: UUID) -> None: ...

class ApprovalService:
    async def approve(self, action_id: UUID, actor: str, note: str | None = None) -> ToolAction: ...
    async def deny(self, action_id: UUID, actor: str, note: str | None = None) -> ToolAction: ...

class EventBroker:
    async def publish(self, run_id: UUID, event: RunEvent) -> None: ...
    async def subscribe(self, run_id: UUID) -> AsyncIterator[RunEvent]: ...
```

### 7.5 注册工具

| Tool | 行为 | Risk | 策略结果 |
|---|---|---:|---|
| `get_service_health(service)` | 读取模拟服务状态 | low | auto approve |
| `search_logs(service, severity, limit)` | 查询确定性的模拟日志 | low | auto approve |
| `restart_service(service, reason)` | 将模拟服务恢复为 healthy 并增加重启计数 | medium | require approval |
| `rotate_api_key(service)` | 模拟凭据轮换意图，但不得真正执行 | high | deny |

每个工具必须声明名称、用途、JSON Schema、风险、是否只读和异步 handler。未知工具、参数校验失败或策略拒绝时不得调用 handler。

### 7.6 策略规则

MVP 使用确定性的代码策略：

1. `high` 风险一律 `deny`。
2. `medium` 风险一律 `require_approval`。
3. `low` 且 `read_only=True` 才能 `auto_approve`。
4. 未注册工具、缺少风险元数据或低风险写工具按 fail closed 处理为 `deny`。

策略结果必须包含 `decision`、`risk_level` 和用户可读的 `reason`，并在执行前写入审计日志。

### 7.7 Agent loop 与恢复语义

1. 创建 run，保存用户消息，状态改为 `running`。
2. 调用模型并传入注册工具 schemas。
3. 没有 tool call 时，保存最终回答并标记 `completed`。
4. 收到 tool call 后，先校验工具名和参数，再持久化 `ToolAction`。
5. 策略为 `auto_approve`：通过幂等 executor 执行，将结果写回消息并继续 loop。
6. 策略为 `require_approval`：保存当前消息检查点，将 action 设为 `pending_approval`，run 设为 `waiting_approval`，立即退出 loop。
7. 策略为 `deny`：不执行工具，将结构化拒绝结果写回模型并继续；如模型不再请求动作则正常结束。
8. 批准动作时用数据库事务完成 `pending_approval → approved`；事务成功后执行一次工具并恢复 run。
9. 拒绝动作时持久化拒绝结果并恢复 run，让模型解释安全边界。

保护限制：最大 8 个 Agent steps、单工具 10 秒、单 run 120 秒。达到限制时 run 进入 `failed`，错误与轨迹可见。

### 7.8 API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | 进程和数据库健康检查 |
| `POST` | `/api/runs` | 创建 run，返回 `202` 与 run id |
| `GET` | `/api/runs` | 按时间倒序列出 runs |
| `GET` | `/api/runs/{run_id}` | 返回 run、actions 和 audit timeline |
| `GET` | `/api/runs/{run_id}/events` | SSE 事件流，含 heartbeat |
| `POST` | `/api/approvals/{action_id}/approve` | 原子批准并恢复 run |
| `POST` | `/api/approvals/{action_id}/deny` | 原子拒绝并恢复 run |
| `GET` | `/api/audit` | 按 run、event type、actor 过滤审计事件 |
| `GET` | `/api/audit/export` | 下载脱敏 JSON |
| `GET` | `/api/policies` | 返回只读工具风险与决策表 |

重复批准或批准非 pending action 返回 `409 Conflict`。不存在的资源返回 `404`。schema 错误返回 `422`。API 错误体统一为 `{ "error": { "code", "message" } }`。

### 7.9 UI

视觉方向是“专业的基础设施控制台”，而不是通用 AI 聊天页：深色中性背景、单一青绿色强调色、等宽状态标签、清晰的密度和留白。

- Runs：顶部新建任务，下面显示状态、模型、steps、更新时间和待审批数量。
- Run detail：用户目标、当前状态、Agent/tool 时间线、原始参数折叠区、最终结果。
- Approval card：工具名、影响对象、risk badge、策略原因、参数、Approve / Deny；提交期间禁用双击。
- Policies：显示四个工具及其风险、只读属性和决策。
- Audit：可按 run/event/actor 过滤，展开脱敏 payload，并导出 JSON。
- 顶栏明确显示 `Local Demo`、当前 provider 和 backend connectivity。

前端不展示 API Key；不得把 key 写入 localStorage、构建变量或浏览器请求。

## 8. 安全与可靠性约束

- 所有工具从 allowlist registry 获取；模型输出永远不直接映射到任意函数。
- Pydantic 在策略判断和执行前验证工具参数。
- 执行前重新检查 action 状态和策略结果。
- `idempotency_key` 数据库唯一，工具 handler 只在成功获取执行权后调用。
- 审批转换使用条件更新或事务锁，失败者返回 `409`。
- audit 是 append-only：业务代码只提供 `append()` 和查询，不提供 update/delete。
- `api_key`、`authorization`、`token`、`secret`、`password` 字段递归脱敏为 `***REDACTED***`。
- 错误响应不返回堆栈、数据库路径或环境变量。
- CORS 仅允许本地前端地址。
- `.env`、SQLite 数据库、Playwright artifacts 不进入 Git。

## 9. 配置契约

`.env.example` 只包含无密钥示例：

```dotenv
AGENTGATE_LLM_PROVIDER=openai_compatible
AGENTGATE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3
AGENTGATE_LLM_API_KEY=your_api_key_here
AGENTGATE_LLM_MODEL=doubao-seed-2-0-lite-260215
AGENTGATE_DATABASE_URL=sqlite:///./data/agentgate.db
AGENTGATE_MAX_STEPS=8
AGENTGATE_TOOL_TIMEOUT_SECONDS=10
AGENTGATE_RUN_TIMEOUT_SECONDS=120
AGENTGATE_WEB_ORIGIN=http://localhost:5173
```

真实 key 只保存在新仓库本地 `.env`。此前在聊天中发送过的 key 应视为已暴露，建议在控制台轮换后再使用。

## 10. 验收场景

1. **健康服务：** 只调用只读工具，无审批完成。
2. **降级服务：** 读取状态与日志后，提出重启并停在 `waiting_approval`。
3. **批准重启：** action 仅执行一次，服务变为 healthy，run 恢复并完成。
4. **拒绝重启：** handler 未调用，run 恢复并说明未执行。
5. **轮换密钥：** 策略直接拒绝，handler 永不调用。
6. **重复批准：** 第一次成功，第二次返回 `409`，restart count 只增加 1。
7. **非法参数：** schema validation 失败，不产生工具副作用。
8. **敏感参数：** API 和 audit payload 中均为脱敏值。
9. **实时界面：** 两个浏览器视图能通过 SSE 看到相同状态变化。

确定性 eval 至少包含 outcome、trajectory、policy compliance 和 idempotency 四类 grader。Live model smoke test 可手动运行，但不进入默认 CI。

## 11. 完成定义

项目只有同时满足以下条件才算完成：

- `scripts/verify.ps1` 在全新克隆后通过后端、前端和 E2E 测试。
- `docker compose up --build` 能启动 API 和 Web。
- Mock provider 可稳定重现两条主演示路线。
- OpenAI-compatible provider 使用环境变量可完成至少一次手动 smoke test。
- README 首屏能在 30 秒内说明问题、方案、架构、启动方式和演示价值。
- `docs/demo.md` 能在 3–5 分钟内完成演示，不依赖临场输入设计。
- 没有密钥、`.env`、数据库文件或测试 artifacts 被 Git 跟踪。
- 项目职责仍是 Agent action governance，没有扩展成第二个情报、研究、RAG 或垂直业务 Agent。
