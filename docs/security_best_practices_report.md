# AgentGate 项目全面审计报告

> 2026-09-10 复核说明：本文保留历史记录，不代表当前正式版本验收。后续发现补报阻塞、恢复日志配对等问题，见[最新工程审核](project-review-and-roadmap-2026-09-10.md)。下文“后续采样恢复”不能涵盖最后一次失败；长时间采样空洞不支持连续 24 小时通过结论。此前两个 Python 进程具有父子关系，不能据此判断存在两个独立 Worker 实例。历史路径安全结论也不覆盖并发目录替换等未验证场景。

当前项目状态、最近运行态和未完成事项不在本历史报告中维护，请查看根目录 [CONTEXT.md](../CONTEXT.md)、[TODO.md](../TODO.md) 和最新执行报告 [2026-09-11-completion-progress.md](superpowers/reports/2026-09-11-completion-progress.md)。

审计周期：2026-09-04 至 2026-09-07（最终复核：2026-09-07）
审计范围：源代码、配置、文档、脚本、测试、依赖、运行数据目录、容器运行态和前端可用性
审计目标：在不做大范围重写的前提下，清理无用产物，降低误操作和配置误用风险，确保项目仍然可运行、可测试、可维护。

## 一、审计结论

项目当前不是“空壳页面”：它已经具备本地控制平面的真实闭环，包括受管工作区、文件检查/隔离/恢复、策略判断、审批、持久化队列、Windows Native Worker、审计记录和本地监控。

本次审计没有发现需要立即推翻架构的高危问题。已完成的主要修复集中在四个边界：

1. 认证边界：免密模式继续只允许 `development`，生产或其他环境不能通过配置误关认证。
2. Web/API 暴露边界：API 交互式文档只在本地开发/测试环境启用；CORS 请求头改为明确白名单。
3. 浏览器安全边界：API 和 Nginx 增加基础安全响应头，统一未知路由和 HTTP 错误的中文错误结构。
4. 前端可用性：表单补充字段名和自动填充语义，工作区加载状态增加屏幕阅读器可感知的状态提示。

当前仍保留三个明确的后续边界：

- 本地开发默认免密是有意设计，只适合回环地址自用，不适合把端口暴露到局域网或公网。
- Python API 和 Worker 虚拟环境均已完成 `pip-audit` 扫描，没有发现已知漏洞；Node 生产依赖审计也没有发现漏洞。
- API 新镜像已经使用 host 网络成功构建并部署；容器内默认网络曾因无法解析 `files.pythonhosted.org` 失败，已确认属于 Docker 构建网络问题，不是项目代码问题。

## 二、已修复的问题

### 1. API 交互式文档默认暴露

- 规则编号：`SEC-API-DOCS-001`
- 风险级别：中
- 位置：`apps/api/app/config.py`、`apps/api/app/main.py`
- 证据：应用现在通过 `Settings.api_docs_enabled` 判断 `/docs`、`/redoc` 和 `/openapi.json` 是否注册；只有 `development` 和 `test` 环境启用。
- 影响：生产环境不再因为忘记显式关闭 FastAPI 文档而暴露接口结构和调试入口。
- 处理：已加入配置属性和回归测试 `test_interactive_api_docs_are_only_enabled_for_local_development`。
- 保留说明：本地开发仍然可以使用文档，便于维护和接口验收。

### 2. CORS 请求头过宽

- 规则编号：`SEC-CORS-001`
- 风险级别：低到中
- 位置：`apps/api/app/main.py`
- 证据：`allow_headers` 现在只允许 `Accept`、`Authorization`、`Content-Type`、`Idempotency-Key` 和 `X-CSRF-Token`。
- 影响：浏览器跨域预检不会无条件接受任意自定义请求头，降低错误配置带来的跨域暴露面。
- 处理：新增预检回归测试，验证未登记请求头会被拒绝。

### 3. API 安全响应头缺失

- 规则编号：`SEC-API-HEADERS-001`
- 风险级别：低
- 位置：`apps/api/app/main.py`、`apps/web/nginx.conf`
- 证据：API 中间件和 Web Nginx 现在设置 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer` 和 `Cache-Control: no-store`；Web 还设置了基础 CSP 与 `Permissions-Policy`。
- 影响：减少 MIME 嗅探、页面嵌入、来源信息泄漏和敏感响应缓存风险。
- 处理：新增 API 和 Compose 合约测试；Web 容器实测响应头已生效。
- 限制：CSP 允许回环地址的 HTTP/HTTPS `connect-src`，这是本地 API 端口可配置所需；未允许任意远程域名。

### 4. 未知路由错误格式不统一

- 规则编号：`SEC-ERROR-001`
- 风险级别：低
- 位置：`apps/api/app/main.py`
- 证据：异常处理器现在接管 Starlette 的 HTTP 异常，未知路由统一返回 `error.code` 和中文 `error.message`。
- 影响：前端不会同时面对 FastAPI 默认的 `detail` 格式和项目自己的 `error` 格式，减少错误分支和英文残留。
- 处理：新增未知路由回归测试。

### 5. 前端表单和状态语义不完整

- 规则编号：`WEB-UX-001`
- 风险级别：低
- 位置：`apps/web/src/pages/WorkspacesPage.tsx`、`apps/web/src/pages/FileGovernancePage.tsx`
- 证据：工作区、文件路径、动作和恢复选择控件已补充 `name`/`autocomplete`；工作区读取过程增加 `role="status"` 和 `aria-live="polite"`。
- 影响：浏览器辅助技术可以识别控件用途和加载状态，表单自动填充、测试定位和错误恢复更稳定。
- 处理：新增对应前端回归断言；Web lint、typecheck、单测和 E2E 均通过。

### 6. 已确认的其他安全边界

以下边界在本次审计中复核后未做不必要改写：

- 文件路径只接受相对路径，拒绝盘符、UNC、NUL、不安全片段、超长路径和受保护模式。
- Worker 对根目录、目录层级和目标文件执行 reparse point/符号链接检查，避免越界到工作区之外。
- 监控 HTTP 目标限制为回环主机，拒绝用户信息、查询参数和非 HTTP(S) 地址。
- Windows 服务探测使用参数数组调用 `sc.exe`，不经过 shell，不执行用户提供的任意命令。
- Worker 令牌保存在 Windows DPAPI 保护的凭据文件中；API 侧只保存摘要，不保存明文令牌。
- 审计和 API 响应会递归脱敏 `api_key`、`authorization`、`token`、`secret`、`password` 等敏感字段。
- 任意 `shell.exec` 等未知工具不会进入 Worker 队列，会被拒绝并记录审计，且没有副作用。

## 三、已删除的文件

本次只删除了能够明确判定为旧的、可重建的运行产物，没有删除源码、配置、数据库、Worker 凭据、工作区或用户文件：

- `data/file-action-soak-20260904-144503.log`
- `data/file-action-soak-20260904-144540.log`
- `data/file-action-soak-20260904-144651.log`
- `data/file-action-soak-60m.stderr.log`（空文件）
- `data/worker-soak-eventlog-24h.log`（旧的未完成测试日志，已被当前重启后的 24 小时日志替代）

这些文件已经从磁盘移除，不能通过 Git 恢复；它们只包含可重新运行得到的健康检查/文件动作测试结果，不包含业务源码或项目数据库。保留下列重要产物：60 分钟文件动作通过日志、已完成的 24 小时 EventLog 日志、Worker 状态目录、`data/agentgate.db` 和测试通过证据。

另外清理了本轮验证重新生成的可重建缓存和构建产物：

- `apps/api/.pytest_cache/`、`apps/api/.ruff_cache/`、`apps/api/.mypy_cache/`
- `apps/api/eval-results.json`
- `apps/worker/.pytest_cache/`、`apps/worker/.ruff_cache/`、`apps/worker/.mypy_cache/`
- `apps/web/dist/`、`apps/web/test-results/`
- 根目录 `.playwright-cli/`（当时不存在，已确认无需处理）

这些缓存和产物也不能通过 Git 恢复，但均可由测试或构建命令重新生成。

## 四、已整理的内容

### 源码和命名

- 将生产路径中容易误导使用者的“演示”文案改成“本地验收”“测试工作区”或“示例状态”。
- 保留 `demo.ps1`、`demo.md` 和历史规格/计划中的兼容名称，因为它们是现有本地验收入口或历史设计记录，不是当前 Web 产品页面。
- 将 `seed_demo` 等内部配置命名调整为 `seed_example`，同时保留旧环境变量别名，避免升级时破坏已有本地配置。
- 修复 OpenAI-compatible Provider 在 AgentRunner 结束后未关闭异步 HTTP 客户端的问题，并添加关闭回归测试。

### 文档和项目结构

- 根目录 README、`docs/README.md`、架构文档、文件治理文档和本地验收手册已统一为中文、正式的本地功能描述。
- 本报告加入 `docs/README.md` 文档入口，便于后续维护者定位安全结论和验证证据。
- `.gitignore` 已覆盖环境文件、虚拟环境、Node 依赖、构建产物、测试缓存、数据库、运行日志、Worker 状态和本地助手临时目录。
- 没有发现空的已跟踪文件、临时备份文件或可确认的源码副本。

### 依赖和构建

- Node 生产依赖审计结果：`total vulnerabilities = 0`。
- API 和 Worker 虚拟环境均执行了 `pip-audit --local/--path`，升级易受影响的 `pip 26.1.2` 到 `26.2.1` 后，均返回 `No known vulnerabilities found`；项目本地包因不是 PyPI 包被工具跳过，不影响其余依赖扫描。
- 没有删除依赖。当前依赖仍被应用、Worker、迁移或测试引用，不能仅凭名称判断为无用。

## 五、疑似但保留的内容

以下内容看起来可能是历史、测试或本地状态，但有明确用途或删除风险，因此保留：

| 内容 | 保留原因 |
| --- | --- |
| `docs/superpowers/specs/`、`plans/`、`reports/` | 项目设计依据、实施记录和验证证据，删除会破坏追溯链 |
| `docs/demo.md`、`scripts/demo.ps1` | 当前本地真实功能验收入口，名称保持兼容，页面产品不再显示“演示”导航 |
| `data/agentgate.db` | 本机运行数据，删除会导致登录、登记目标和历史记录丢失 |
| `apps/worker/.agentgate-worker`、`.demo-worker` | Worker 凭据、journal 和运行状态；当前有 Worker 进程使用，不能清理 |
| `.superpowers/`、`.worktrees/` | 本机维护/历史工作状态，当前未证明可以删除 |
| `AGENTGATE_SEED_DEMO` 兼容别名和旧策略翻译 | 兼容已有本地配置与历史审计记录，不影响当前中文界面 |
| 测试中的 `demo`、`mock`、`example` 字样 | 测试数据、Provider 名称或历史兼容标识，不是用户产品宣传文案 |

## 六、潜在问题和后续建议

### 1. 免密模式的部署边界

- 级别：中（仅在错误部署时）
- 位置：`.env.example`、`apps/api/app/config.py`、`compose.yaml`
- 现状：开发环境允许 `AGENTGATE_AUTH_ENABLED=false`，Compose 端口只绑定 `127.0.0.1`。
- 风险：如果用户把端口改为 `0.0.0.0`、通过反向代理转发，或在非本机环境复用开发配置，任何能访问端口的人都可能使用控制台。
- 建议：保持本机自用时的回环绑定；只要需要局域网/远程访问，就启用密码认证、设置 HTTPS/反向代理和独立数据库凭据。

### 2. Compose 默认数据库密码

- 级别：中（只适用于错误暴露数据库或跨环境复用配置）
- 位置：`compose.yaml`
- 现状：未设置 `AGENTGATE_POSTGRES_PASSWORD` 时使用开发默认值；Postgres 当前不发布宿主机端口。
- 建议：本地单机可维持现状；一旦用于共享环境，必须通过环境变量或 Secret 注入随机密码，并避免复用开发卷。

### 3. 外部模型请求的数据边界

- 级别：中（取决于 Provider 配置）
- 位置：`apps/api/app/llm/openai_compatible.py`
- 现状：启用 `openai_compatible` 后，Agent 请求会发送到 `.env` 中配置的 Base URL；这是模型调用的必需行为。
- 建议：只配置可信服务端点，避免把密钥、密码、Worker 凭据和不必要的文件内容放进任务提示；生产环境应增加出口域名白名单和请求审计策略。

### 4. 24 小时稳定性测试出现环境暂停造成的瞬时心跳失败

- 级别：低到中（需要观察，当前未导致测试提前中止）
- 现状：`1227` 次采样中有 `3` 次 `worker=degraded`，异常前采样间隔约为 84 分钟、45 分钟和 6 小时 54 分钟；API、数据库、队列和目标探测保持正常，后续采样恢复。最终结果为 `COMPLETED_WITH_TRANSIENT_FAILURES`。
- 判断：证据更符合运行主机睡眠/唤醒或长时间暂停导致 Worker 心跳暂时过期，而不是连续 Worker 故障；日志没有提供足够信息证明是代码缺陷，因此不做未经证实的代码修复。
- 最终复核：当前发现两个 Windows Native Worker 进程共用 `.demo-worker` 状态目录。未自动终止任何一个，以避免中断现有监控；长期运行前应确认用途并只保留一个实例。
- 建议：如果需要全绿稳定性证据，在电脑保持唤醒、只运行一个直接 Worker 实例且不让多个 Worker 共用状态目录的条件下重新运行 24 小时测试；同时保留失败时刻的 Worker 进程和系统日志。

## 七、验证证据

### 已通过

- API 单元/集成测试：`262 passed, 6 skipped`
- Worker 测试：`57 passed, 2 skipped`
- API `ruff check`：通过
- API `mypy app`：`Success: no issues found in 68 source files`
- Web lint：通过
- Web typecheck：通过
- Web 单元测试：`15 test files / 48 passed`
- Web 构建：Vite 构建成功
- Playwright E2E：`3 passed`
- 确定性 Agent 评估：`6/6`，每个案例 `4/4 PASS`
- Compose 配置检查：通过
- Foundation、文件验收、Worker、Task Scheduler 合约测试：全部通过
- Web 运行态：`http://127.0.0.1:15173/` 返回 `200`，安全响应头已实测存在
- API 运行态：`/health` 和 `/api/platform/health` 均报告正常；数据库、队列、Outbox、Worker 心跳均正常
- 当前 24 小时稳定性测试：已完成 `1227` 次采样；结果为 `COMPLETED_WITH_TRANSIENT_FAILURES`，失败 `3` 次且未连续达到提前终止阈值，不能表述为全绿；异常与长时间采样间隔同步出现
- API 新镜像：使用 `docker build --network=host` 成功构建并部署；运行态 API 已返回新安全响应头和统一中文 404
- Python 依赖：API/Worker `pip-audit` 均返回 `No known vulnerabilities found`
- 60 分钟文件动作稳定性测试：`107/107` 成功，失败数 `0`

### 未通过或无法确认

- 24 小时测试不是全绿，存在 `3` 次短暂 Worker 心跳失败；采样间隔证据指向主机暂停，但如果要获得全绿证据仍需在保持唤醒的环境中重跑。
- 全仓 `ruff format --check`：仓库存在历史混合换行/格式差异；全仓格式化会造成与本次审计无关的大量噪声，因此没有执行大范围格式化。

## 八、审计后的使用建议

当前项目适合以本地控制平面的方式运行：先登记明确的工作区和本地目标，再通过文件治理、审批、Worker 执行和审计页面管理动作；不应把它理解成自动扫描整台电脑或自动拦截所有第三方 Agent 的系统。

如果继续推进，优先级建议为：

1. 把 `pip-audit` 加入 CI，形成 Python/Node 双依赖扫描。
2. 用单一 Worker 状态目录重新跑一轮 24 小时稳定性测试，定位并消除 3 次瞬时心跳失败。
3. 将“开发免密”和“受保护本地模式”做成明显的启动配置提示，避免误把免密配置用于共享环境。
4. 在不扩大权限范围的前提下，再考虑更多 Windows 只读探测器；不要直接加入任意命令执行或全盘自动扫描。
