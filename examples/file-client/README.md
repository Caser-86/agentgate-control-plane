# AgentGate 外部文件客户端

这是一个使用 Python 标准库编写的真实接入示例。它代表外部脚本或 Agent，通过正式 API
提交文件动作，不读取 AgentGate 数据库，不直接访问工作区，也不会把客户端令牌写进代码。

## 使用前准备

1. 启动 AgentGate API 和 Worker。
2. 在控制台登记工作区，并记下工作区 ID。
3. 使用管理员会话调用 `POST /api/auth/tokens`，创建只包含 `propose:actions` 的客户端令牌。
   当前控制台没有独立的令牌管理页面；令牌只在创建响应中显示一次，应保存在本机环境变量或凭据管理器中。
4. 确认客户端调用的是本机回环地址，而不是把 API 暴露到公网。

PowerShell 示例：

```powershell
$env:AGENTGATE_API_URL = "http://127.0.0.1:8000"
$env:AGENTGATE_CLIENT_TOKEN = "从安全位置读取的客户端令牌"
$env:AGENTGATE_WORKSPACE_ID = "已登记的工作区 UUID"
```

不要把真实令牌写进 `.py`、README、命令历史或 Git 提交中。

## 一次真实调用

请求使用 `Idempotency-Key` 防止网络重试造成重复动作；同一个键只能对应同一组参数。

命令分别对应正式动作 `file.inspect.v1`、`file.quarantine.v1` 和 `file.restore.v1`。

在仓库根目录执行：

```powershell
python .\examples\file-client\client.py inspect `
  --path notes.txt `
  --idempotency-key inspect-notes-001
```

只读检查会自动执行。隔离是有副作用的动作，必须先提交申请，再到控制台“审批”批准：

```powershell
python .\examples\file-client\client.py quarantine `
  --path notes.txt `
  --reason "整理临时文件" `
  --idempotency-key quarantine-notes-001
```

响应中的 `status` 可能是 `pending_approval`、`queued`、`running`、`succeeded` 或 `failed`。
HTTP 请求成功只代表申请被 API 接收，不代表文件已经移动。查询动作：

```powershell
python .\examples\file-client\client.py status --action-id "动作 UUID"
```

隔离完成后，从工作区的隔离记录中取得 `quarantine_entry_id`，批准恢复申请：

```powershell
python .\examples\file-client\client.py restore `
  --quarantine-entry-id "隔离记录 UUID" `
  --idempotency-key restore-notes-001
```

## 错误和边界

- `protected_path`、`invalid_relative_path` 等策略错误表示没有执行文件变化。
- `pending_approval` 需要管理员在控制台批准；客户端不会自行批准。
- 网络超时应使用原来的幂等键先查询状态，不要盲目提交新键。
- 目标冲突、结果上报失败或状态不确定时，系统会保留待复核状态，不自动重复移动。
- 这个客户端只能约束经过 AgentGate API 的动作；它不会阻止其他程序直接修改或删除文件。
- 客户端令牌不能创建管理员会话、登记工作区或调用审批接口。
