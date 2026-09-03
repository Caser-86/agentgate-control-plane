# AgentGate 本地演示脚本

本演示使用确定性的 `mock` 提供方，预计 3–5 分钟完成，不需要模型 API key，也不依赖真实模型的随机输出。

## 演示前准备

在项目根目录启动：

```powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane'
$env:AGENTGATE_API_PORT = '18230'
$env:AGENTGATE_WEB_PORT = '15173'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider mock
```

打开：<http://127.0.0.1:15173>

如果页面不可访问，先检查：

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:18230/health
```

首次运行需要读取本机 `data/bootstrap-token` 完成管理员初始化；已经初始化过的环境直接使用管理员密码登录。

## 1. 查看策略矩阵

进入“策略”，说明 Agent 的工具调用不是直接执行，而是先经过登记和策略判断。

重点展示：

- `get_service_health`：低风险、只读、自动批准。
- `search_logs`：低风险、只读、自动批准。
- `restart_service`：中风险、修改演示状态、需要人工审批。
- `rotate_api_key`：高风险、直接拒绝、没有执行处理器。
- `platform.self_check`：低风险、只读，仅供原生 Worker 安全自检。

## 2. 提交恢复任务

进入“运行”，选择示例：

```text
恢复降级服务 → 需审批
```

点击“启动运行”。对应的任务文本是：

```text
检查 payments-api 并安全恢复，不要轮换凭据。
```

说明：健康检查和日志查询是只读动作，因此会自动执行；重启动作会暂停，等待人工审批。

## 3. 检查待审批动作

打开运行详情，等待出现审批卡片。应看到：

- 动作：`restart_service`。
- 风险：中风险。
- 目标：`payments-api`。
- 原因：安全恢复降级服务。
- 说明：中风险动作必须明确批准。
- 操作：批准或拒绝。

如果没有出现审批卡片，可能是本地演示服务已经处于健康状态。可以重新启动干净的 mock 环境，或者使用一个全新的测试数据库后再次提交任务。

## 4. 批准并观察恢复

点击一次“批准”。运行应恢复并最终进入“已完成”。时间线应包含：

- `approval.approved`：审批已通过。
- `tool.started`：工具开始执行。
- `tool.succeeded`：工具执行成功。
- `run.completed`：运行完成。

本次演示只会修改数据库中的服务状态：`payments-api.health` 变成 `healthy`，`restart_count` 增加 1。不会重启 Windows 中真实的服务。

如果重复点击审批按钮，应该看到“该动作已经决定”之类的冲突提示；这是为了避免同一个动作被执行两次。

## 5. 观察高风险拒绝

回到“运行”，选择：

```text
轮换 API 密钥 → 直接拒绝
```

对应任务文本是：

```text
请轮换 payments-api 的 API 密钥。
```

预期结果：

- 运行可以结束，但不会出现审批卡片。
- 动作记录为 `rotate_api_key`。
- 风险为高风险。
- 策略决定为拒绝。
- 不会调用任何密钥处理器。

不要在任务文本、截图或审计导出中填写真实密钥。

## 6. 查看审计轨迹

进入“审计”，可以按运行 ID 筛选并展开事件 JSON。重点展示：

- 运行创建。
- 工具提议。
- 策略决定。
- 审批请求、批准或拒绝。
- 工具开始和执行结果。
- 运行完成或失败。

以下类型的字段会被递归脱敏：`api_key`、`authorization`、`token`、`secret`、`password`。

需要保存时点击“导出 JSON”，但不要把包含敏感业务数据的导出文件提交到 Git 或发送到聊天。

## 7. 查看确定性评测

在 API 虚拟环境已准备好的情况下执行：

```powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane\apps\api'
.\.venv\Scripts\python.exe -m app.evals.runner
```

评测包含 6 个场景，每个场景有 4 个评分器，预期为：

```text
6 cases × 4/4 PASS
```

场景包括健康检查、审批暂停、批准恢复、拒绝无副作用、高风险轮换拒绝和错误参数拒绝。

## 演示结论

最后回到 [架构说明](architecture.md)，用下面这条链路总结：

```text
浏览器 → API → PolicyEngine → PostgreSQL → 人工审批
       → ToolExecutor → AgentRunner → 模型提供方
```

本地演示证明的是“提议、判断、审批、执行、恢复和审计”这条控制链路，不证明真实 Windows 服务、密钥或文件已经可以被操作。
