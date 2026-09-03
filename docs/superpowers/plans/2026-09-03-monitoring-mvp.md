# 阶段 1：真实本机监控 MVP 实施计划

> **针对智能体 Worker：** 必须先阅读并遵循 `superpowers:test-driven-development`、`superpowers:executing-plans` 和 `superpowers:verification-before-completion`；每个实现任务先补失败测试，再写最小生产代码，完成后运行对应验证。

## 目标

在现有 AgentGate 本地控制平面上增加可真实运行的只读监控闭环：用户可以在中文网页中登记本机 HTTP 地址或 Windows 服务名称，系统通过受限的 Native Worker 周期检查目标，连续失败达到阈值后形成一个活动事件，连续恢复达到阈值后自动关闭事件。监控结果、目标状态和事件都持久化，且不会因为探针自身故障把目标误报为宕机。

本阶段完成后，用户能够：

1. 登录中文控制台并查看监控目标、当前健康状态、最近一次探测和活动事件。
2. 登记本机回环地址上的 HTTP 目标，或登记一个 Windows 服务名。
3. 手动触发探测，并由调度器按间隔自动排队探测。
4. 看到 `healthy`、`degraded`、`down`、`unknown` 状态及中文解释。
5. 通过事件列表确认故障开始、恢复和最近一次失败原因。

## 范围与明确不做的事情

### 本阶段包含

- HTTP 只读探针：仅允许 `http://` 或 `https://`，仅允许本机回环地址（`localhost`、IPv4/IPv6 loopback），限制超时、响应大小和重定向。
- Windows 服务只读探针：只接受安全格式的服务名，固定调用 `sc.exe query <service-name>`，不接受 Shell、PowerShell、路径或任意命令。
- `monitor.http`、`monitor.windows_service` Worker 能力，并保留 `platform.self_check`。
- 目标、探测观测、事件和状态转换的数据库模型及 Alembic 迁移。
- 目标登记、目标查询、手动探测、事件查询 API；全部要求已认证 Operator 会话。
- 调度器对已启用、到期目标排队；任务使用现有 `ControlTask` 租约和幂等机制。
- 中文前端监控页、表单、状态标签、错误提示和刷新操作。
- 单元测试、API 测试、Worker 探针测试、前端测试和迁移/契约验证。

### 本阶段不包含

- 自动重启、停止、启动服务、轮换密钥或任何写入型操作。
- 任意远程主机、远程 Windows 服务、内网扫描或网络发现。
- 接收并保存 HTTP 响应正文、Authorization、Cookie 或 API Key。
- 监控 AgentGate 之外的凭据读取、账号登录或外部平台写入。
- 以当前测试结果冒充 24 小时稳定性验收；只补齐可执行的长期验收说明。

## 设计摘要

```text
中文控制台
    │ 目标登记 / 手动探测 / 查询
    ▼
FastAPI 监控 API ── MonitorTarget / Observation / Event
    │                 状态机：失败阈值、恢复阈值、unknown 隔离
    ▼
ControlTask（只读监控能力、租约、幂等）
    ▲
Native Worker
    ├─ monitor.http           受限 HTTP 客户端
    └─ monitor.windows_service 固定 sc.exe query
```

Worker 只回传结构化、长度受限的结果，不回传响应正文或敏感请求头。API 在同一事务中记录任务完成结果、观测记录、目标状态、事件状态和 outbox/audit 记录；重复完成、过期租约和非法 payload 必须保持幂等或进入人工复核。

状态规则：

- `healthy`：最近一次探测成功；连续失败计数清零。
- `degraded`：已经出现失败，但尚未达到故障阈值。
- `down`：连续失败达到 `failure_threshold`，且目标有一个活动事件。
- `unknown`：探针无法可靠执行或配置无效；不增加失败计数，不创建或关闭目标故障事件。
- 目标处于 `down` 后，连续成功达到 `recovery_threshold` 才关闭活动事件并恢复为 `healthy`。
- 同一目标最多一个活动事件；重复失败只更新事件，不创建重复活动事件。

## 实施顺序

### 任务 1：数据库模型、枚举和迁移

**先写测试：**

- 测试模型默认值、枚举序列化、目标名称/类型/间隔/阈值边界。
- 测试迁移 head 包含新版本，并能在测试数据库建立目标、观测和事件表。

**实现：**

- 新增 `apps/api/app/monitoring/enums.py`、`models.py` 和 `__init__.py`。
- 新增 `MonitorTarget`、`MonitorObservation`、`MonitorEvent`；使用字符串列保存枚举，避免 SQLite/PostgreSQL 枚举迁移差异。
- 在 `apps/api/app/db.py` 注册模型。
- 新增 `apps/api/migrations/versions/0009_monitoring_mvp.py`，包含索引及同一目标活动事件的唯一约束（兼容现有数据库）。

### 任务 2：目标配置校验和状态机

**先写测试：**

- HTTP 仅接受本机回环 URL，拒绝公网地址、非 HTTP(S) scheme、凭据、fragment、过大/过小 timeout 和非法端口。
- Windows 服务名只允许字母、数字、点、下划线、短横线，拒绝空格、斜杠、引号和命令串。
- 连续失败只在达到阈值时创建一个活动事件。
- 连续成功只在达到恢复阈值时关闭活动事件。
- `unknown` 不改变失败/成功计数，不误报目标，不关闭已有活动事件。
- 重复或乱序完成结果不会生成重复活动事件。

**实现：**

- 新增 `apps/api/app/services/monitoring.py`，集中放置目标配置校验、结果归一化和状态转换。
- 所有阈值、间隔和详情长度设置硬上限；日志和 API 响应不包含密钥、正文、Cookie 或完整异常堆栈。
- 把状态更新、观测、事件和审计/outbox 写入置于同一个数据库事务。

### 任务 3：监控 API 和调度器

**先写测试：**

- 未登录访问监控 API 返回 401。
- Operator 可以创建、列表查询、查看单个目标和查询事件。
- 手动探测会创建带正确能力、目标 ID 和幂等键的 `ControlTask`。
- 非法目标配置返回中文 422；不存在目标返回 404；禁用目标不排队探测。
- 调度器只为到期且启用目标排队，并避免同一目标已有未完成任务时重复排队。
- Worker 完成监控任务会记录观测和更新状态；非法结果进入失败/人工复核路径，不改变目标健康状态。

**实现：**

- 新增 `apps/api/app/api/monitoring.py`，提供：
  - `GET /api/monitor/targets`
  - `POST /api/monitor/targets`
  - `GET /api/monitor/targets/{target_id}`
  - `POST /api/monitor/targets/{target_id}/probe`
  - `GET /api/monitor/events`
- 在 `apps/api/app/main.py` 注册路由。
- 扩展 Worker 任务完成流程，在完成事务内调用监控状态机。
- 扩展 `apps/api/app/processes/scheduler.py`，按 `next_probe_at` 和安全的间隔排队任务。
- 对调度任务使用确定性幂等键，确保重试不会重复创建活动事件或任务。

### 任务 4：Native Worker 探针能力

**先写测试：**

- HTTP 探针测试健康响应、非 2xx、超时、连接错误、重定向、非回环地址和结果长度限制。
- Windows 探针测试 `RUNNING`、`STOPPED`、服务不存在和命令失败；测试确认调用参数为固定 `sc.exe query` 且 `shell=False`。
- Worker 注册支持三个能力；非法能力、非法任务类型、缺少目标字段和跨能力 payload 必须拒绝。
- Worker 完成结果只保留白名单字段，不能把响应正文、token 或环境变量上传。

**实现：**

- 新增 `apps/worker/agentgate_worker/probes.py`，提供可注入 HTTP transport 和 Windows service runner，便于测试。
- 扩展 `client.py`、`main.py`、Worker 协议能力白名单和 payload 校验。
- 生产 Windows runner 使用 `subprocess.run([...], shell=False, capture_output=True, timeout=...)`；不拼接 Shell 命令。
- Linux/Docker 控制 Worker 不宣称 Windows 服务能力；本机 Windows Worker 通过启动脚本注册完整能力。
- 更新 Worker 依赖清单，使用已有 HTTP 客户端依赖或添加最小、锁定范围的依赖。

### 任务 5：中文前端监控页

**先写测试：**

- API client 为目标列表、创建目标、手动探测和事件查询生成正确请求。
- 监控页默认中文，能显示空状态、加载、错误、目标状态、最近探测和活动事件。
- 创建表单按 HTTP/Windows 服务切换字段，并展示本机限制和只读说明。
- 手动探测成功后刷新目标状态；按钮在请求期间禁用。
- 未认证时沿用现有登录跳转逻辑。

**实现：**

- 新增 `apps/web/src/pages/TargetsPage.tsx` 与测试。
- 扩展 `types.ts`、`api/client.ts`、`App.tsx` 和 `AppShell.tsx`，加入“监控”导航。
- 在 `styles.css` 增加与现有深色控制台一致的状态卡片、表单和响应式布局；所有用户可见文案使用 `zh-CN`。
- 不在前端保存或展示 API Key、Worker token 或响应正文。

### 任务 6：文档、脚本和最终验证

**先写测试/检查：**

- 文档链接、中文文案、Compose/启动脚本、迁移 head 和 API 路由契约检查。
- 后端全量测试、Worker 全量测试、前端 lint/typecheck/Vitest/build。
- 按现有方式运行评估场景，并记录真实输出。

**实现：**

- 更新根目录 `README.md`、`docs/README.md`、`docs/architecture.md` 和 `docs/superpowers/progress.md`，补充中文监控使用说明、限制和故障排查。
- 增加本地监控验证步骤和 24 小时稳定性验收命令/指标说明，但不伪造尚未执行的长期结果。
- 检查敏感信息未进入 Git；提交本地变更前确认 `git diff --check` 和工作区范围。

## 验收标准

1. 迁移可从现有 `0008_operator_installation_key` 升级到监控版本，且 SQLite 测试数据库能建表。
2. 未认证不能访问监控 API；认证用户能登记一个回环 HTTP 目标和一个安全格式的 Windows 服务名。
3. 手动探测能排队并由 Native Worker 完成，结果能在网页中看到。
4. 连续失败达到阈值只产生一个活动事件；继续失败不会重复创建。
5. 连续恢复达到阈值自动关闭活动事件。
6. `unknown` 探针结果不会改变目标健康计数，也不会造成误报。
7. API、Worker 和前端测试全部通过；所有失败都必须有真实错误记录和修复后复测证据。
8. 不执行、不实现任何自动重启或任意命令能力。

## 风险与回滚

- 新迁移只新增表和索引；若监控功能出现问题，可停止调度/Worker，现有运行、策略、审计和登录功能仍应可用。
- 监控任务能力采用显式白名单；如果协议改动导致旧 Worker 不兼容，应先让旧 Worker 继续只宣称 `platform.self_check`，再升级本机 Worker。
- HTTP 探针默认只允许 loopback，任何放开公网或远程地址的需求都必须另行评审，不在本计划内隐式放宽。
- 本阶段不推送 GitHub；完成并复核后再根据用户指示提交或推送。

