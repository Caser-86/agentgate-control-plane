# AgentGate 持续本机监控 Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将原生 Windows Worker 扩展为可持续领取本机监控任务的进程，并提供安全的当前用户登录自动启动和控制台 Worker 状态展示。

**Architecture:** 保留默认一次执行模式，用 `--loop` 显式进入持续模式，避免影响现有 foundation 验收。循环复用已有 Worker 协议、DPAPI 凭据、journal 和服务端心跳；Windows 任务计划只启动已完成注册的 Worker，不保存 enrollment token。前端复用已有 `/api/platform/health`，不新增数据库表或 API 协议。

**Tech Stack:** Python 3.11、httpx、pytest、PowerShell、Windows Task Scheduler、React 19、TypeScript、Vitest、Playwright、FastAPI。

**Spec:** `docs/superpowers/specs/2026-09-04-agentgate-worker-autostart-design.md`

## Global Constraints

- Worker 继续只接受 `localhost`、`127.0.0.1` 和 `::1` API 地址。
- HTTP 监控目标必须是本机 loopback URL；Windows 服务探针只能使用固定的 `sc.exe query`。
- 不执行任意 Shell/PowerShell，不读写任意用户文件，不实现真实服务重启。
- enrollment token、Worker token、API key 不得进入任务计划参数、日志、审计 payload 或前端。
- 默认 CLI 行为仍为一次执行；只有 `--loop` 启用持续模式。
- 心跳默认间隔为 10 秒，轮询等待默认为 1 秒，退避最大为 30 秒。
- 测试命令在 Windows 使用 `apps/api/.venv/Scripts/python.exe` 运行 Worker 测试，前端使用 `npm.cmd`。
- 当前工作区包含此前批准的未提交修改，不执行 reset、checkout 或混合提交。

---

### Task 1: 提取 Worker 执行循环并加入持续模式

**Files:**
- Modify: `apps/worker/agentgate_worker/main.py`
- Test: `apps/worker/tests/test_main.py`

**Interfaces:**
- Produces `run_worker_cycle(client) -> None`，执行一次 heartbeat、journal recovery、claim 和可选 task completion。
- Produces `run_worker_loop(client, *, stop_event, poll_seconds, heartbeat_seconds, wait=None, monotonic=None) -> None`，持续执行任务并支持测试注入等待函数和时钟。
- Keeps `main()` default one-shot behavior and adds `--loop`, `--poll-seconds`, `--heartbeat-seconds`.

- [x] **Step 1: Write failing tests for the loop contract**

Add a fake runtime client to `test_main.py` that records method names and can return a `TaskGrant` or `None`. Add tests equivalent to:

~~~python
def test_run_worker_loop_processes_one_task_and_stops_after_wait() -> None:
    client = FakeRuntimeClient(grants=[grant])
    stop_event = threading.Event()

    def wait(seconds: float) -> bool:
        assert seconds == 1.0
        stop_event.set()
        return True

    run_worker_loop(
        client,
        stop_event=stop_event,
        poll_seconds=1.0,
        heartbeat_seconds=10.0,
        wait=wait,
        monotonic=lambda: 0.0,
    )

    assert client.calls == ["heartbeat", "recover", "claim", "start", "probe", "complete"]


def test_run_worker_loop_treats_empty_queue_as_normal() -> None:
    client = FakeRuntimeClient(grants=[None])
    stop_event = threading.Event()

    def wait(seconds: float) -> bool:
        assert seconds == 1.0
        stop_event.set()
        return True

    run_worker_loop(
        client,
        stop_event=stop_event,
        poll_seconds=1.0,
        heartbeat_seconds=10.0,
        wait=wait,
        monotonic=lambda: 0.0,
    )

    assert client.calls == ["heartbeat", "recover", "claim"]


def test_run_worker_loop_uses_bounded_backoff_after_protocol_error() -> None:
    client = FakeRuntimeClient(errors=[WorkerProtocolError("temporary")])
    stop_event = threading.Event()
    waits: list[float] = []

    def wait(seconds: float) -> bool:
        waits.append(seconds)
        stop_event.set()
        return True

    run_worker_loop(
        client,
        stop_event=stop_event,
        poll_seconds=1.0,
        heartbeat_seconds=10.0,
        wait=wait,
        monotonic=lambda: 0.0,
    )

    assert waits == [1.0]
~~~

The fake client must implement the existing `heartbeat`, `recover_pending_reports`, `claim`, `start`, `complete`, and `probe_result` signatures without network or filesystem work.

- [x] **Step 2: Run the new tests and verify RED**

Run:

~~~powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane\apps\worker'
..\api\.venv\Scripts\python.exe -m pytest tests/test_main.py -q
~~~

Expected: FAIL because `run_worker_loop` and the loop behavior do not yet exist.

- [x] **Step 3: Implement the minimal runtime loop**

In `main.py`:

1. Add `threading`, `signal`, `time` and callable/protocol imports.
2. Add a small runtime client protocol covering only the methods used by the loop.
3. Extract the existing one-shot body into `run_worker_cycle`.
4. Implement `run_worker_loop` with immediate heartbeat, journal recovery, one claim per successful iteration, task processing, poll wait, bounded exponential backoff, and stop-event exit.
5. Install SIGINT/SIGTERM handlers in `main()` only for loop mode; handlers only set a `threading.Event`.
6. Add parser arguments with defaults `--loop` false, `--poll-seconds 1.0`, and `--heartbeat-seconds 10.0`; reject values outside 0.1–60 and 1–60 respectively.

- [x] **Step 4: Run focused tests and lint**

~~~powershell
..\api\.venv\Scripts\python.exe -m pytest tests/test_main.py -q
..\api\.venv\Scripts\ruff.exe check agentgate_worker tests
~~~

Expected: focused tests pass and ruff reports no errors.

### Task 2: Wire PowerShell continuous startup and Task Scheduler scripts

**Files:**
- Modify: `scripts/start-worker.ps1`
- Modify: `scripts/start-worker.contract.test.ps1`
- Create: `scripts/install-worker.ps1`
- Create: `scripts/uninstall-worker.ps1`
- Create: `scripts/task-scheduler.contract.test.ps1`

**Interfaces:**
- `start-worker.ps1 -Continuous` passes `--loop`, `--poll-seconds`, and `--heartbeat-seconds` only when requested.
- `install-worker.ps1 -ApiUrl http://127.0.0.1:18230 [-StateDir D:\LLM Files\files\agentgate-control-plane\apps\worker\.agentgate-worker] [-TaskName AgentGateNativeWorker]` requires an existing `credentials.bin`, registers a current-user AtLogOn task, and starts it.
- `uninstall-worker.ps1 -TaskName AgentGateNativeWorker` removes only the named scheduled task and never deletes state files.

- [x] **Step 1: Write failing PowerShell contract tests**

Extend `start-worker.contract.test.ps1` to require the continuous arguments. Create `task-scheduler.contract.test.ps1` with these checks:

~~~powershell
$install = Get-Content -Raw (Join-Path $PSScriptRoot "install-worker.ps1")
$uninstall = Get-Content -Raw (Join-Path $PSScriptRoot "uninstall-worker.ps1")
if ($install -notmatch "Register-ScheduledTask") { throw "install script must register a task" }
if ($install -notmatch "New-ScheduledTaskTrigger.*AtLogOn") { throw "install script must use AtLogOn" }
if ($install -notmatch "MultipleInstances.*IgnoreNew") { throw "install script must prevent duplicate instances" }
if ($install -match "EnrollmentToken|enrollment-token") { throw "install script must not persist enrollment token" }
if ($uninstall -notmatch "Unregister-ScheduledTask") { throw "uninstall script must remove the task" }
if ($uninstall -match "Remove-Item.*StateDir|credentials|journal") { throw "uninstall script must preserve worker state" }
~~~

- [x] **Step 2: Run the contract tests and verify RED**

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-worker.contract.test.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\task-scheduler.contract.test.ps1
~~~

Expected: the new assertions fail because the continuous arguments and task scripts are not present.

- [x] **Step 3: Implement continuous start arguments**

Add `-Continuous`, `-PollSeconds` with range 0.1–60 and `-HeartbeatSeconds` with range 1–60 to `start-worker.ps1`. Append the corresponding Python arguments only when `$Continuous` is true. Keep the existing conditional enrollment-token append unchanged.

- [x] **Step 4: Implement safe install and uninstall scripts**

`install-worker.ps1` must resolve the repository and absolute state path, validate a loopback API URL, require `credentials.bin`, create a current-user AtLogOn task with `MultipleInstances IgnoreNew`, pass only API URL and state directory to `start-worker.ps1 -Continuous`, start the task, and print no credentials.

`uninstall-worker.ps1` must unregister only the selected task with `-Confirm:$false`; it must not delete the state directory, credentials, or journal.

- [x] **Step 5: Run contracts and a real existing-credentials start**

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-worker.contract.test.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\task-scheduler.contract.test.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-worker.ps1 -ApiUrl http://127.0.0.1:18230 -StateDir .demo-worker
~~~

Expected: contract tests pass and the one-shot Worker exits 0 without printing credentials. Do not install the scheduled task during automated verification; installation remains an explicit user-run command because it changes Windows user state.

### Task 3: Show Worker health in the Chinese console

**Files:**
- Modify: `apps/web/src/types.ts`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/components/AppShell.tsx`
- Create: `apps/web/src/components/AppShell.test.tsx`
- Modify: `apps/web/src/App.test.tsx`
- Modify: `apps/web/src/api/client.test.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:**
- Produces `PlatformHealthCheck` and `PlatformHealth` matching `/api/platform/health`.
- Produces `api.getPlatformHealth(): Promise<PlatformHealth>`.
- Extends `RuntimeState` with `workerStatus: "checking" | "online" | "degraded" | "unavailable"`.

- [x] **Step 1: Add failing frontend tests**

Add a client test for `/api/platform/health` and an AppShell test covering `Worker 在线`, `Worker 心跳异常`, and `无法检查`.

- [x] **Step 2: Run focused frontend tests and verify RED**

~~~powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane\apps\web'
npm.cmd test -- --run src/api/client.test.ts src/components/AppShell.test.tsx
~~~

Expected: FAIL because `getPlatformHealth` and the Worker status UI do not yet exist.

- [x] **Step 3: Implement the health client and polling UI**

Add the typed client method. In `AppShell`, request platform health on mount and every 10 seconds, cancel updates after unmount, and map only `checks.worker.status` to the four local UI states. Keep model/API metadata loading independent. Render a sidebar row labelled `本机 Worker` with Chinese status text and never render raw error bodies or secret fields.

- [x] **Step 4: Run focused tests, lint, typecheck, and build**

~~~powershell
npm.cmd test -- --run src/api/client.test.ts src/components/AppShell.test.tsx src/App.test.tsx
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
~~~

Expected: all focused tests and static checks pass.

### Task 4: Document the operational workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/superpowers/progress.md`

- [x] **Step 1: Document registration and automatic startup**

Add exact commands using an environment-held enrollment token for the first registration, then `install-worker.ps1 -ApiUrl http://127.0.0.1:18230` and `uninstall-worker.ps1`. Explain that the token is used only once, the scheduled task contains no token, and uninstall preserves monitoring data.

- [x] **Step 2: Document retry and safety boundaries**

State that the Worker monitors only registered local HTTP/Windows-service targets, retries transient API failures with bounded backoff, uses journal recovery, and does not discover processes or perform automatic remediation.

- [x] **Step 3: Check documentation for secrets and stale claims**

~~~powershell
rg -n "AGENTGATE_LLM_API_KEY|enrollment-token|Worker token|密码|自动启动|--loop|install-worker|uninstall-worker" README.md docs
~~~

Confirm no literal secret is added and every claim matches the implementation.

### Task 5: Full verification and handoff

**Files:**
- Modify only files required by Tasks 1–4.

- [x] **Step 1: Run all checks**

~~~powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify.ps1
Set-Location .\apps\worker
..\api\.venv\Scripts\python.exe -m pytest tests -q
..\api\.venv\Scripts\ruff.exe check agentgate_worker tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ..\..\scripts\start-worker.contract.test.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ..\..\scripts\task-scheduler.contract.test.ps1
~~~

Expected: verification exits 0, API tests include the new contract test, Worker tests pass, ruff passes, and both PowerShell contracts pass.

- [x] **Step 2: Verify live Compose and monitoring state**

~~~powershell
Set-Location 'D:\LLM Files\files\agentgate-control-plane'
docker compose config --quiet
docker compose ps
Invoke-RestMethod http://127.0.0.1:18230/health
Invoke-WebRequest http://127.0.0.1:15173/ -UseBasicParsing
~~~

Confirm existing monitor targets remain healthy and no credentials appear in output.

- [x] **Step 3: Review the mixed worktree**

~~~powershell
git diff --check
git status --short
git diff --stat
~~~

Do not reset or commit the mixed worktree. Report feature files separately from pre-existing modified files, and state whether the scheduled task was installed.
