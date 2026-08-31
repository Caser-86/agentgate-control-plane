# Task 8 Report: Reliable Foundation Safety Boundaries

## 本轮修复

- `apps/api/tests/test_failure_injection.py` 现在以真实 native Worker 协议完成 fake self-check 的 claim、start 和 execution grant；随后用真实 `WorkerJournal` 写入 `unknown` 结果并抛出明确的“connection lost after start”窄 seam，最后在 lease recovery 时断言 `MANUAL_REVIEW`、started 状态和无宿主机 handler 调用。该 seam 等价于进程在执行授权已持久化、完成回报前崩溃。
- `apps/api/app/main.py`、`apps/api/app/processes/control_worker.py` 和 `apps/web/playwright.config.ts` 增加仅 `AGENTGATE_ENV=test` 的 SQLite schema 初始化与 durable control-worker E2E 编排；生产 PostgreSQL migration gate 不变。
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

## Bounded limitations

- Stage 0 is **not accepted** because required E2E and foundation runtime checks did not pass.
- Bounded Playwright on free loopback ports `18000`–`18007` started API/Web. After test-only SQLite initialization and control-worker wiring, the latest bounded single-spec run returned in about 15 seconds with the exact state: run detail remained `Queued`, timeline contained only `run.created`, and no `approval-card` appeared within the 5-second assertion. Earlier runs also exposed exact setup failures: missing `operators` table, per-worker bootstrap-token path mismatch, and a 30-second login selector race; those were corrected where possible. No process was forcibly stopped or restarted by the verification commands.
- `powershell -NoProfile -File .\scripts\verify-foundation.ps1` could not execute because this host's PowerShell execution policy disabled script loading (`PSSecurityException`, `running scripts is disabled on this system`). No API service was started or restarted for this check. The script itself is back at the approved Task 7 version per scope review.
- PostgreSQL-dependent tests remain the existing four skips because `AGENTGATE_TEST_DATABASE_URL` is unset. No Postgres container/database initialization was attempted during this bounded cleanup.

## Safety and scope

Existing redaction, error-path, duplicate-approval, SSE cursor, pre-grant no-handler, post-grant journal, and no-host-mutation assertions remain. No arbitrary shell, remote target, file mutation, real restart, or model dependency was added. The only extra non-brief production-file changes are test-environment-only startup hooks strictly required to initialize the E2E disposable SQLite database and run the existing durable control worker.
