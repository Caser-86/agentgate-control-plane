# Task 8 Report: Reliable Foundation Safety Boundaries

## 本轮修复

- `apps/api/tests/test_failure_injection.py` 现在以真实 native Worker 协议完成 fake self-check 的 claim、start 和 execution grant；随后用真实 `WorkerJournal` 写入 `unknown` 结果并抛出明确的“connection lost after start”窄 seam，最后在 lease recovery 时断言 `MANUAL_REVIEW`、started 状态和无真实宿主机动作。该 seam 等价于进程在执行授权已持久化、完成回报前崩溃。
- native crash 回归现在通过 `WorkerClient.claim()`/`start()` 和 fake protocol transport 运行真实 Worker client seam；no-op handler 在 started boundary 可观察地到达，journal pending result 和 manual-review recovery 均有断言。
- `apps/api/app/main.py`、`apps/api/app/processes/control_worker.py` 和 `apps/web/playwright.config.ts` 增加仅 `AGENTGATE_ENV=test` 的 SQLite schema 初始化与 durable control-worker E2E 编排；生产 PostgreSQL migration gate 不变。
- E2E 使用两个独立 project 的 API/Worker/Web 端口、SQLite 文件和 bootstrap token；test-only reset/seed 让每个 project 从确定性数据库开始，Worker 在 provider 校验后写入 readiness 标记，global setup 对其做 30 秒有界等待。
- 两个 E2E spec 改用中文测试流程、现有中文文案和稳定 test IDs；拒绝后检查 `status-denied`，刷新详情并检查 `approval.denied` 审计记录。前端增加 `run-status`/`action-status` 稳定契约。
- 按 Task 8 scope 审计，撤回了 `scripts/verify-foundation.ps1` 的 Task 7 Compose 解析修复和 `apps/api/tests/test_compose_contract.py` 的对应断言；保留 ApprovalCard secret-redaction 与 RunsPage stable-ID 单测，因为它们是本轮中文契约/安全回归的必要覆盖。

## Fresh verification

- `apps/api/.venv/Scripts/python.exe -m ruff check app tests` — PASS。
- `apps/api/.venv/Scripts/python.exe -m mypy app` — `Success: no issues found in 53 source files`。
- `apps/api/.venv/Scripts/python.exe -m pytest -q` — `147 passed, 4 skipped in 7.81s`。
- `apps/api/.venv/Scripts/python.exe -m app.evals.runner` — six cases, each `4/4 PASS`。
- Focused `tests/test_failure_injection.py` — `7 passed`。
- Frontend lint/typecheck/Vitest/build — fresh run passed earlier in this turn: `7 files, 11 tests passed`; build produced Vite output.
- `docker compose config --quiet` — PASS。
- `apps/web/npm.cmd run typecheck` — PASS。

## Bounded limitations

- Stage 0 is **not accepted** because required E2E and foundation runtime checks did not pass.
- Bounded command `$env:AGENTGATE_E2E_PYTHON=(Resolve-Path '..\\api\\.venv\\Scripts\\python.exe').Path; $env:AGENTGATE_E2E_API_PORT='18000'; npm.cmd run test:e2e -- --reporter=list` started both isolated projects and reached `WAITING_APPROVAL`/`PENDING_APPROVAL` in the project SQLite, but both browser specs timed out after 15 seconds without rendering `approval-card`; exact Playwright failures are retained in `apps/web/test-results`. Stage 0 therefore remains not accepted.
- `powershell -NoProfile -File .\scripts\verify-foundation.ps1` could not execute because this host's PowerShell execution policy disabled script loading (`PSSecurityException`, `running scripts is disabled on this system`). No API service was started or restarted for this check. The script itself is back at the approved Task 7 version per scope review.
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\verify-foundation.ps1` executed but failed with `API is not loopback-only.` at line 10 because the Task 7 script expects the fixed Compose mapping while this verification environment/config did not expose the expected text. No service was started or restarted.
- PostgreSQL-dependent tests remain the existing four skips because `AGENTGATE_TEST_DATABASE_URL` is unset. No Postgres container/database initialization was attempted during this bounded cleanup.

## Safety and scope

Existing redaction, error-path, duplicate-approval, SSE cursor, pre-grant no-handler, post-grant journal, and no-host-mutation assertions remain. No arbitrary shell, remote target, file mutation, real restart, or model dependency was added. The only extra non-brief production-file changes are test-environment-only startup hooks strictly required to initialize the E2E disposable SQLite database and run the existing durable control worker.

## Final review follow-up

- 两份 Web E2E spec 现在都断言 POST 返回的 `queued`，通过同一 run 的有界 Outbox SSE 回放确认已记录 `run.updated(status=running)`，再用 `run-status` 确认 `Waiting approval`；审批流额外用稳定 test IDs 断言 `pending_approval`、`denied` 和 `approval.denied` 审计记录。Running 不依赖短暂 DOM 停留，中文流程与现有隔离保持不变。
- Fresh bounded frontend checks: `npm.cmd run typecheck` — PASS; `npm.cmd run lint` — PASS; `npm.cmd test -- --run` — `7 files, 11 tests passed`; `npm.cmd run build` — PASS。
- E2E limitation: per request, the bounded E2E run was interrupted before completion and is not claimed as passing. The prior bounded runs reached the durable queued → running → waiting-approval state, but exposed and were used to correct test-source/selector issues; no final E2E pass is reported here.

## Final review fix

- Both E2E status helpers now reconnect and continue through transient request exceptions, empty heartbeat frames, non-advancing cursors, HTTP failures, and malformed event JSON until their own 15-second deadline. They retain the last five diagnostics and fail only after the deadline, preserving the queued → running → waiting approval → denied → audit assertions and test isolation.
- Fresh bounded E2E attempt: `$env:AGENTGATE_E2E_PYTHON=(Resolve-Path '..\\api\\.venv\\Scripts\\python.exe').Path; $env:AGENTGATE_E2E_API_PORT='18000'; npm.cmd run test:e2e -- --reporter=list` — both isolated projects started and both tests reached the post-approval denial assertion; both then failed after 15 seconds because `[data-testid="action-status"] .status-denied` was not rendered (`2 failed`). No helper timeout or transient SSE/request failure occurred in this run. The E2E suite is therefore not claimed as passing.

## Integration fix pass — 2026-09-01

- Scheduler expiry recovery now uses one guarded conditional update keyed by task id, captured worker, lease version, status, and still-expired lease. Audit/Outbox side effects are emitted only when exactly one row changes; side-effect tasks go to `manual_review`, read-only tasks use bounded retry. SQLite conditional-race coverage passed; the two-session PostgreSQL race test is present but skipped because `AGENTGATE_TEST_DATABASE_URL` is unset.
- Added the Compose `migrate` one-shot gate and `service_completed_successfully` dependencies for API, scheduler, and control-worker. `docker compose config --quiet` and structured configuration inspection passed; no Compose startup was run after the user-requested interruption.
- Audit redaction now normalizes keys by lowercasing and removing non-alphanumeric characters across server/UI paths, with camelCase/compound-key and error-path regression coverage. Platform health/self-check are operator-authenticated; `/health` remains anonymous. The safe `platform.self_check` proposal is explicit and non-executable unless claimed by the existing safe Worker path.
- `verify-foundation.ps1` now derives loopback host ports from structured Compose JSON and performs an authenticated native Worker self-check round trip without printing tokens. The denial UI/E2E fixes were exercised in a prior bounded run on free port `18220`: `2 passed`.

### Bounded local verification after interruption

- API focused pytest: `33 passed, 1 skipped in 1.21s`.
- API Ruff: `All checks passed!`.
- Web focused Vitest: `2 files, 6 tests passed`.
- Web lint and typecheck: PASS.
- PowerShell AST parse for `scripts/verify-foundation.ps1`: PASS.
- The cleanup check found `remaining-port-connections=0`; no Docker/Postgres/E2E process was left running.

### Exact unresolved limitations

- PostgreSQL is not available for this pass: `AGENTGATE_TEST_DATABASE_URL` is unset, so the two-session lease-race test is skipped. No database URL was set and no persistent/user database was used.
- Per the interruption request, no full backend suite, full frontend suite/build, Docker startup smoke, `verify-foundation.ps1` live run, or new E2E run was started after cleanup. The latest valid prior bounded E2E evidence is the free-port `18220` run (`2 passed`).
- `verify-foundation.ps1` previously hit the host's script execution-policy block without `Bypass`, and the prior Bypass attempt failed at the exact check `API is not loopback-only`; the revised script's live authenticated/native-Worker path remains unverified because it requires a running Compose stack, session cookie, and Worker tokens.
- Stage 0 remains evidence-limited rather than accepted as a complete environment qualification; no secrets or token contents were printed.

## Final integration fix pass — 2026-09-01

- `AuditEventResponse.run_id` is now nullable and includes `resource_type`/`resource_id`; list/export regression coverage proves generic Worker events with `run_id=None` return 200, preserve resource context, and redact tokens.
- Unsupported v1 read-only checks now receive a clear `403 unsupported_check`, persist one redacted `check.rejected` audit/Outbox record, and create no orphan task. The existing `platform.self_check` proposal remains the only Phase 0 check capability and keeps its safe payload contract.
- Claim-path expired-lease recovery now calls the same guarded atomic recovery function as scheduler recovery. Successful retry/manual-review recovery appends audit and `task.updated` Outbox evidence in the same caller transaction; a focused claim test proves state/event consistency and existing race tests remain covered.
- `verify-foundation.ps1` now proposes the safe check, creates a temporary native Worker state directory, runs register/heartbeat/claim/start/complete, removes temporary credentials/journal in `finally`, and only then requires the authenticated platform heartbeat/migration gate. Compose ports remain derived from structured JSON and no secrets are printed.

### Fresh final verification

- Backend Ruff — PASS; mypy — `Success: no issues found in 53 source files`; pytest — `156 passed, 5 skipped in 7.33s`; eval runner — six cases, each `4/4 PASS`.
- Focused integration tests — `23 passed, 3 skipped`; PostgreSQL skips are because `AGENTGATE_TEST_DATABASE_URL` is unset. No persistent/user DB was used.
- Frontend lint — PASS; typecheck — PASS; Vitest — `7 files, 12 tests passed`; build — PASS.
- `docker compose config --quiet` — PASS; PowerShell AST parse — PASS.
- Bounded E2E on isolated ports `18220`/`18221` — `2 passed (14.4s)`; both Chinese approval/denial flows rendered the denial state and retained audit evidence after refresh.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-foundation.ps1` — FAIL at line 29 with `API health check failed.` The worktree Compose stack was not running; port inspection showed `8000` held by two unrelated listeners. The script did not start or restart services. Temporary E2E ports had no remaining listeners.

Stage 0 is **not accepted**: live foundation verification and PostgreSQL-specific race coverage remain unavailable in this environment, despite the bounded E2E and all available local checks passing.
