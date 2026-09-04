# AgentGate 持续本机监控 Worker 设计

## 目标

把当前“一次执行一次”的原生 Windows Worker 扩展为可长期运行的本机监控进程，并提供 Windows 登录后自动启动入口。用户登记的本机 HTTP 地址和 Windows 服务由现有 scheduler 排队，Worker 持续领取任务、执行只读探针、发送心跳并报告结果；控制台能够显示 Worker 是否在线。

## 当前基线

- Compose 中的 API、scheduler、control-worker、PostgreSQL 和 Web 已能持续运行。
- scheduler 会根据 `next_probe_at` 为监控目标创建 `monitor.http` 或 `monitor.windows_service` 任务。
- 原生 Worker 当前由 `apps/worker/agentgate_worker/main.py` 执行一轮 register（必要时）、heartbeat、journal recovery、claim 和 complete 后退出。
- `/api/platform/health` 已提供脱敏的 Worker 心跳检查，90 秒内有心跳为 `ok`，否则为 `degraded`。
- Worker 只能访问 loopback API，HTTP 探针只能访问 loopback 地址，Windows 服务探针只能调用固定的 `sc.exe query`；这些边界保持不变。

## 范围

### 包含

1. Worker 增加可测试的持续循环模式，默认保留现有一次执行模式。
2. 持续模式定期发送 heartbeat、恢复 journal 中的待报告结果、领取并完成监控任务。
3. 网络或 API 暂时不可用时采用有上限的指数退避，不因一次瞬时错误退出。
4. 支持 `SIGINT`、`SIGTERM` 和 Windows 控制台终止事件的干净退出。
5. `start-worker.ps1` 增加连续模式参数，并保持空 enrollment token 不会被传入 Python。
6. 新增 Windows 任务计划安装、启动、卸载脚本；任务不保存或打印 enrollment token，使用已由 DPAPI 保护的 Worker 凭据。
7. 控制台复用 `/api/platform/health` 显示 Worker 在线、过期或检查中状态，并定时刷新。
8. 更新中文 README、目录文档和测试验收命令。

### 不包含

- 不改变 API、Worker 协议字段和数据库表结构。
- 不支持远程监控目标或自动发现其他软件。
- 不执行任意 Shell、PowerShell、文件写入或真实服务重启。
- 不把 enrollment token、Worker token 或 API key 写入任务计划参数、日志或前端。
- 不改变默认的一次执行模式，以保持 `verify-foundation.ps1` 和已有人工验收可控返回。

## 用户流程

首次注册仍然由受信任的本机终端提供一次性 enrollment token：

1. 启动 API、scheduler、control-worker 和 Web。
2. 用 enrollment token 手动运行一次 `start-worker.ps1`，Worker 注册并把凭据保存到本机 DPAPI 文件。
3. 运行 `install-worker.ps1` 创建当前用户登录触发的 Windows 任务计划。
4. Worker 以连续模式运行；API 中的 scheduler 持续排队监控任务。
5. 用户在 Web 的“监控”页查看目标状态，在侧栏查看 Worker 心跳状态。
6. 运行 `uninstall-worker.ps1` 可移除自动启动任务，但不删除已保存的 Worker 凭据或监控数据。

## 运行时设计

### 一次执行模式

现有 `main()` 流程提取为 `run_worker_cycle(client)`，执行一次 heartbeat、journal recovery、claim、start、probe 和 complete。没有任务时正常返回 0；协议错误仍返回 1，便于基础验证发现配置或认证问题。

### 持续模式

新增 `run_worker_loop(...)`，由 `--loop` 触发。循环规则如下：

- 启动时立即 heartbeat；之后默认每 10 秒 heartbeat 一次，不能超过 API 配置的 Worker 租约安全窗口。
- 每轮先恢复 journal，再领取最多一个任务；有任务则按现有 start → probe → complete 流程执行。
- 没有任务时等待默认 1 秒，不产生错误日志。
- `WorkerProtocolError` 进入退避等待，等待时间为 1、2、4、8、16、30 秒，最大 30 秒；成功完成一轮后退避复位。
- 收到停止信号时不再领取新任务，退出循环并返回 0；当前任务由现有 journal 和租约恢复机制负责兜底。
- enrollment token 只用于首次注册，不会写入循环配置；没有已保存凭据且没有 token 时立即返回明确错误。

### 进程参数

- `--loop`：启用持续模式；默认不启用。
- `--poll-seconds`：无任务时的等待时间，范围 0.1–60 秒，默认 1 秒。
- `--heartbeat-seconds`：心跳间隔，范围 1–60 秒，默认 10 秒；运行时必须小于 Worker 租约的三分之一或由服务端返回值推导出更安全的值。
- 现有 `--api-url`、`--state-dir`、`--name`、`--version`、`--enrollment-token` 保持兼容。

## Windows 自动启动

`install-worker.ps1`：

- 只接受 loopback API URL。
- 要求 `state-dir/credentials.bin` 已存在，提示用户先完成一次手动注册。
- 创建或更新当前用户的任务计划，触发条件为用户登录。
- 任务动作调用 `start-worker.ps1 -Continuous`，传入 API URL 和绝对 state directory，不传 enrollment token。
- 使用单实例策略，避免重复 Worker 争抢租约。
- 安装后立即启动任务，并只输出任务名称、状态和日志查看提示，不输出凭据。

`uninstall-worker.ps1` 只删除指定任务计划，不删除 state directory、credentials 或 journal。

## 控制台状态

前端新增一个轻量的 `PlatformHealth` 类型和 `api.getPlatformHealth()` 客户端方法，调用已有 `GET /api/platform/health`。`AppShell` 每 10 秒刷新一次：

- `checks.worker.status === "ok"` 显示“Worker 在线”。
- `checks.worker.status !== "ok"` 显示“Worker 心跳异常”。
- 请求尚未返回显示“检查中”。
- API 请求失败不泄露响应正文或敏感字段，显示“无法检查”。

## 错误处理和安全

- loopback URL 校验继续在 Worker Python 客户端和 PowerShell 启动脚本两侧执行。
- 任务计划参数不得包含任何 token；日志不得打印 HTTP Authorization header、响应正文或 API key。
- 连续模式对网络失败重试，但对协议、能力和任务安全校验仍 fail-closed；不因重试绕过服务端拒绝。
- Worker 状态由服务端心跳决定，不能由前端本地“假装在线”。
- 停止、卸载和 API 暂时不可用都不能删除本地 journal，避免结果丢失。

## 测试验收

### Worker 单元测试

- 空队列持续循环不会报错，并按 poll interval 等待。
- 循环会处理一个任务并调用 start、probe、complete。
- 心跳按间隔发送，不会每一轮重复发送。
- 协议错误触发指数退避，成功后退避复位。
- 停止事件使循环干净退出。
- 默认 CLI 仍执行一次；`--loop` 才进入持续模式。

### PowerShell 契约测试

- `start-worker.ps1 -Continuous` 传递 loop 参数。
- 已有凭据时不传空 enrollment token。
- 安装脚本拒绝缺少 credentials、远程 URL 和重复实例配置错误。
- 卸载脚本不删除 state directory。

### Web/API 测试

- `PlatformHealth` 客户端能解析 worker check。
- AppShell 显示在线、异常、检查中三种状态。
- API 或 worker check 失败时显示中文错误，不显示密钥。
- 现有监控、认证、审批、审计和 E2E 流程保持通过。

### 手工验收

1. 注册一次 Worker 并安装任务计划。
2. 确认任务计划只有一个运行实例，侧栏显示 Worker 在线。
3. 关闭一个本地 HTTP 服务，确认在失败阈值后出现故障事件。
4. 恢复服务，确认在恢复阈值后事件关闭。
5. 停止 Worker，确认 90 秒内控制台显示心跳异常。
6. 重新登录或启动任务，确认 Worker 恢复在线且历史观测仍保留。
