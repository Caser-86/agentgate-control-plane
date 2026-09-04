# AgentGate 本地功能验收手册

这份手册面向第一次打开项目的人。它描述真实功能的验收路径；面试时由你自行选择操作顺序，不需要产品内置独立演示页面。

## 一条命令准备本地环境

在 Windows PowerShell 的项目根目录执行：

```powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo.ps1
```

脚本会完成以下工作：

1. 用当前命令的端口启动或复用 PostgreSQL、API、scheduler、control-worker 和 Web。
2. 等待 API 健康检查通过。
3. 检查 Native Worker 心跳；没有在线 Worker 时，临时创建一次性注册凭据并在后台注册 Worker。
4. 在 `%LOCALAPPDATA%\AgentGate\demo-workspace` 创建两个本地测试文件。
5. 登记或复用“AgentGate 文件治理工作区”。
6. 打开 `http://127.0.0.1:15173/files`。

脚本只在进程环境中临时覆盖端口和工作区允许根目录，不修改 `.env`。任何令牌都不会打印到终端、写入 README 或加入 Git。

如果端口不是 `18230/15173`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo.ps1 `
  -ApiPort 18000 -WebPort 18010
```

如果只想准备数据而不自动打开浏览器：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\demo.ps1 -NoBrowser
```

## 五分钟文件治理验收

### 第一步：检查文件

在“文件治理”页面选择工作区和“检查文件”，输入文件相对路径后提交。页面会真实调用 `POST /api/v1/actions`：

- 普通文件：只读返回存在性、大小和 SHA-256 摘要，不返回文件内容。
- `.env` 等保护路径：如果提交隔离动作，会命中保护规则并被拒绝，不创建 Worker 任务。

动作、决策和审计事件都来自 API，不是前端静态状态。

### 第二步：批准并隔离普通文件

1. 回到“文件治理”，选择“隔离文件”，输入普通文件相对路径并提交。
2. 打开“审批”。
3. 检查工作区、相对路径、风险等级、规则原因和预计副作用。
4. 确认 Worker 状态为“在线”。离线时批准按钮保持禁用。
5. 点击“批准并执行”，再到“动作”查看最终状态。

Native Worker 会在同一卷的隔离目录中移动 `demo.txt`，并把 SHA-256 摘要、大小、相对路径和结果回报给 API。页面不显示绝对根路径、文件正文或 Worker 原始异常。

### 第三步：恢复文件

在“文件治理”选择“恢复文件”，从隔离记录中选择目标，再次在“审批”中批准恢复动作。最终应看到“已恢复”。恢复逻辑不会覆盖原位置已有的文件；如果用户在恢复前创建了同名文件，动作会进入明确的冲突失败状态。

### 第四步：检查审计

进入“审计”或“动作”，可以看到：

- 受保护路径拒绝；
- 普通文件待审批；
- 审批通过和任务排队；
- Worker 执行成功；
- 隔离记录和摘要前缀；
- 恢复成功或冲突结果。

审计是追加式证据，不支持通过页面修改。敏感字段会递归脱敏。

## 这套流程验证了什么

它证明 AgentGate 能把“外部 Agent 提议文件动作”放进一个实际可运行的控制边界：

```text
外部 Agent/API client
        ↓  相对路径 + 幂等键
API → PolicyEngine → 审批队列 → Native Worker
        ↓                         ↓
    PostgreSQL 审计          Windows 同卷隔离/恢复
```

它不证明以下事情：

- 不接入 AgentGate 的程序会被自动拦截；
- 有 Windows 内核驱动级别的全局防护；
- 可以远程管理任意电脑；
- 可以执行任意 Shell、PowerShell 或删除命令；
- 会永久删除文件。

## 外部 Agent 如何接入

管理员先通过 Web 或管理员 API 创建只包含所需 scope 的 client token。原始 token 只在创建响应中出现一次，实际项目应放入外部 Agent 自己的安全存储；示例中统一使用 `***`。

文件动作提交示例：

```powershell
$headers = @{
  Authorization = "Bearer ***"
  "Idempotency-Key" = "interview-demo-001"
}
$body = @{
  action = "file.quarantine.v1"
  workspace_id = "00000000-0000-0000-0000-000000000000"
  relative_path = "demo.txt"
  reason = "请人工确认后隔离"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:18230/api/v1/actions" `
  -Headers $headers -ContentType "application/json" -Body $body
```

常见返回状态：

| 状态 | 含义 |
| --- | --- |
| `denied` | 策略拒绝，没有执行任务 |
| `pending_approval` | 等待管理员决定，没有移动文件 |
| `queued` / `running` | 已批准，正在等待或执行 |
| `succeeded` | Worker 已回报可靠的结果 |
| `failed` | 明确失败或恢复冲突，不会无界重试 |

查询动作状态：

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:18230/api/v1/actions/<action-id>" `
  -Headers @{ Authorization = "Bearer ***" }
```

相同 client 使用相同幂等键重放，会得到原动作结果，不会再次移动同一个文件。

## 原有 Agent 运行演示

如果要查看模型编排而非真实磁盘动作：

1. 打开“运行”。
2. 选择“恢复降级服务 → 需审批”。
3. 查看只读检查自动执行。
4. 在“审批”中批准或拒绝 `restart_service`。
5. 回到运行详情查看时间线和审计。

这个分支只修改数据库里的示例服务状态，不会重启 Windows 服务。高风险“轮换 API 密钥”会被拒绝，不会调用密钥处理器。

## 失败排查

### 浏览器提示 `ERR_CONNECTION_REFUSED`

```powershell
docker compose ps
Invoke-RestMethod http://127.0.0.1:18230/health
```

API 没有返回 `status: ok` 前不要刷新 Web。端口被占用时给 `demo.ps1` 传入新的 `-ApiPort` 和 `-WebPort`。

### PowerShell 找不到 npm 或提示 npm.ps1 被禁止

本项目在 Windows 下统一使用 `npm.cmd`，例如：

```powershell
Set-Location apps\web
npm.cmd test -- --run
```

启动脚本使用 `-ExecutionPolicy Bypass` 只影响本次脚本进程，不要求永久修改系统执行策略。

### Worker 离线

先确认：

```powershell
Test-Path .\apps\worker\.venv\Scripts\python.exe
Invoke-RestMethod http://127.0.0.1:18230/api/platform/health | ConvertTo-Json -Depth 6
```

如果运行环境不存在，执行 `..\scripts\setup-local.ps1`。不要把 enrollment token、Worker token 或管理员密码复制到聊天中。

## 停止本地服务

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

停止项目不会删除 PostgreSQL 数据卷、`.env`、审计记录或 Worker 的 DPAPI 状态。`-ResetDemoData` 也只会删除演示工作区中脚本生成的两个文件，不会删除数据库或其他用户目录。
