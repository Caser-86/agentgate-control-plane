# Worker 回环边界与脚本参数修复实施计划

> **面向 Agent Worker：**生产变更前，每项任务都要先用失败的回归测试证明问题，再在提交前执行全新验证。

**目标：**确保每个原生 Worker 入口都会在使用凭据或发起网络请求前拒绝不安全的 API URL，并让显式传入的 `-ApiUrl` 优先于 PowerShell 端口回退逻辑。

**架构：**在 `apps/worker/agentgate_worker/client.py` 中保留一份 URL 策略，由 `HttpTransport` 和 `WorkerClient` 共同调用，避免注入的传输实现绕过校验。让 `start-worker.ps1` 先解析并校验显式 URL，在本地推导端口；`verify-foundation.ps1` 则委托到这条安全脚本路径。

**技术栈：**Python 3.11、httpx、pytest、PowerShell、Docker Compose 契约测试。

## 全局约束

- 只支持 localhost/回环地址 API 目标。
- 接受文档规定的 `http`/`https` 回环 URL，包括 IPv4 和 IPv6 回环地址。
- 在使用 Bearer/enrollment token 前，拒绝格式错误的 URL、非 HTTP(S) 协议、远程 DNS/IP 主机、URL 中的凭据、查询参数/片段以及无效端口。
- 保留队列、授权、认证、脱敏、迁移和 Compose 契约；不增加宿主机动作。
- 有界验证期间不得启动或停止用户服务。

## 任务

- [x] 为不安全的 `HttpTransport`、`WorkerClient` 和 `main()` URL 增加 Worker 回归覆盖，包括不发起网络请求的行为。
- [x] 增加显式 `-ApiUrl` 优先级和端口推导的 PowerShell 契约覆盖，并让基础设施验证通过 `start-worker.ps1` 执行。
- [x] 实现共享的原生 URL 策略和 PowerShell 安全路径，不改变队列、授权、认证、脱敏、迁移或 Compose 行为。
- [ ] 运行重点检查和完整检查，用准确证据与限制更新台账/报告，只提交当前工作树的内容。
