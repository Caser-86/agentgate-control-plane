# AgentGate 故障排查手册

本手册按“先确认现象，再确认组件，最后修改配置”的顺序排查。不要因为登录失败、页面打不开或动作卡住就删除 `data/`、PostgreSQL 数据卷、`.env` 或 Worker 状态目录；这些操作可能丢失账号、审计和对账证据。

## 1. 页面打不开或显示 `ERR_CONNECTION_REFUSED`

在项目根目录检查服务和日志：

```powershell
docker compose ps
docker compose logs --tail 100 postgres migrate api scheduler control-worker web
```

再访问 API 健康检查；如果 `.env` 修改过端口，把 `8000` 换成实际端口：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

重新启动：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

启动脚本会检查 Compose 配置、必需服务和 API 健康状态；任何一项失败都会返回非零退出码。如果 Docker CLI 能运行但 Compose 报 Engine 或 named pipe 不存在，先启动 Docker Desktop，并确认：

```powershell
docker info --format 'server={{.ServerVersion}}'
```

如果 Docker Desktop 窗口已经打开，但仍提示
`dockerDesktopLinuxEngine` 管道不存在，可再检查：

```powershell
wsl.exe -l -v
Get-Service -Name com.docker.service
docker context ls
```

看到 `docker-desktop` 为 `Stopped` 时，先在 Docker Desktop 中切换到 Linux 容器；如果发行版已经是
`Running` 但 `com.docker.service` 仍是 `Stopped`，请用“以管理员身份运行”启动 Docker Desktop 或让系统管理员启动该服务。
服务恢复前不要执行 `docker compose down -v`，也不要删除 PostgreSQL 数据卷；项目代码和数据本身不一定有问题。

## 2. 初始化或登录失败

默认 `.env.example` 使用 `AGENTGATE_ENV=development` 和 `AGENTGATE_AUTH_ENABLED=false`。免密模式下不应出现密码页；修改后重建 API 和 Web：

```powershell
docker compose up -d --build --force-recreate api web
```

启用密码模式后，第一次初始化需要一次性 `data/bootstrap-token` 和至少 6 位管理员密码。初始化成功后 token 会失效，之后登录只填写管理员密码。不要把 token、密码、Cookie 或截图发给别人，也不要在 `localhost` 和 `127.0.0.1` 之间来回切换。

如果提示 token 无效或过期，确认访问的是同一个 `data/` 挂载和同一个 API；不要重复使用已消费的 token。项目当前没有公开密码重置流程，遗忘密码时先保留数据库和备份，不要直接删除数据库卷。

## 3. `npm.ps1` 被 PowerShell 禁止

这是 PowerShell 执行策略阻止脚本入口，不是前端代码故障。使用 `npm.cmd`：

```powershell
npm.cmd ci
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test -- --run
npm.cmd run build
```

本项目不要求永久放宽系统执行策略。

## 4. Worker 未注册、离线或执行受阻

检查 Worker 虚拟环境和原生依赖：

```powershell
Test-Path .\apps\worker\.venv\Scripts\python.exe
& .\apps\worker\.venv\Scripts\python.exe -c "import win32crypt; import agentgate_worker"
```

依赖损坏时运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-worker.ps1 -ApiUrl http://127.0.0.1:18000
```

`register-worker.ps1` 只允许本机回环 API，会申请 10 分钟有效的一次性注册令牌，令牌通过子进程环境变量传递，不打印到终端，也不会写入日志。它不会覆盖已有 `credentials.bin`；如果状态目录已有凭据，直接使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-worker.ps1 `
  -Continuous -ApiUrl http://127.0.0.1:18000
```

启用密码认证时，注册脚本需要当前管理员会话通过 `AGENTGATE_SESSION_COOKIE` 提供，并自动获取或使用 `AGENTGATE_CSRF_TOKEN`；不要把这些值写入脚本或聊天记录。

平台健康页中的“进程在线”和“执行状态”是两件事：

- `unknown`：没有可信的执行状态，不能当作完全正常。
- `blocked`：网络、补报或协议错误使 Worker 暂停领取任务。
- `reconciliation_required`：本地 journal 有结果，但服务端回报存在冲突，需要人工对账；系统不会自动重做可能已有副作用的文件动作。

不要删除 `apps/worker/.agentgate-worker/journal.db` 来解除阻塞，它是防止重复副作用的重要证据。服务端日志：

```powershell
docker compose logs --tail 200 api control-worker scheduler
```

## 5. 动作停在待审批、排队或执行中

先在“动作”确认动作 ID，再在“审批”确认是否真的批准；随后检查系统页中的 Worker 状态和 API 日志。`pending_approval` 是等待管理员决定，`queued` 是已批准但未领取，`running` 是 Worker 已开始，`succeeded` 才表示取得可信执行结果。API 返回 2xx 只代表请求被接受，不代表文件已经变化。

如果任务已经开始但结果不确定，按“待复核”处理，不要提交新幂等键。补报冲突时保留 journal 和审计证据，人工确认不重新执行文件操作。

## 6. 文件动作被拒绝或恢复冲突

命中 `.env`、`.git/**`、密钥文件或 `protected/**` 是预期的策略拒绝；盘符、UNC、`..`、设备名、NUL 或越过工作区根目录也会被拒绝。恢复目标已存在、源/目标摘要不一致、工作区已停用或版本变化时，系统不会覆盖文件，会进入冲突或复核状态。

处理冲突时先保存目标文件和审计信息，再由管理员决定如何整理；不要直接删除冲突文件，也不要用新幂等键绕过原动作。

## 7. 迁移失败或数据库版本不一致

```powershell
docker compose logs --tail 200 postgres migrate api
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\migrate-local.ps1
```

平台自检会区分代码迁移头和已应用版本。迁移失败时不要启动旧 API 假装正常，也不要手工修改 `alembic_version`；先保留日志和数据库备份。

## 8. 模型请求失败

先切回 Mock，确认控制平面本身正常：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Provider mock
```

真实模型只检查 `.env` 中的 provider、Base URL、模型名和 API key。真实 key 只放在本机后端配置，不要放进 README、客户端示例、日志或前端。模型失败不会改变文件治理的路径校验和审批边界。

## 9. 外部客户端调用失败

客户端必须使用客户端 token，而不是管理员密码、Worker token 或引导 token：

```powershell
$env:AGENTGATE_API_URL = "http://127.0.0.1:8000"
$env:AGENTGATE_CLIENT_TOKEN = "从安全位置读取"
$env:AGENTGATE_WORKSPACE_ID = "已登记工作区 UUID"
python .\examples\file-client\client.py inspect --path notes.txt --idempotency-key inspect-notes-001
```

- `authentication_required`：token 缺失、错误、撤销或过期。
- `insufficient_scope`：token 没有 `propose:actions`。
- `idempotency_key_reused`：同一个键提交了不同动作，先查询原动作。
- `pending_approval`：到控制台审批，不要客户端自行批准。
- `network_error`：恢复连接后使用原幂等键查询状态。

## 10. 验证和环境不足

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1 -IncludeWindowsFileContract
```

Docker Server 未运行时，可以执行 Python、Web、Compose 配置解析和静态合约，但不能声称 PostgreSQL、容器构建、浏览器 E2E 或 24 小时稳定性测试通过。当前证据见 [执行进度报告](superpowers/reports/2026-09-11-completion-progress.md)。
