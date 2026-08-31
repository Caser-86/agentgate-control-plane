# Task 6 Report — Durable Control Worker

## Outcome

Run creation and approval decisions now persist a durable `agent_run_resume`
ControlTask and return without executing a provider or tool in the HTTP request.
`ControlWorker` claims tasks with the existing lease/recovery queue, opens its
own SQLModel sessions, and resumes only scoped local control-plane run tasks.
The Task 4 remote Worker protocol remains limited to self-check work.

Approval decisions are conditional on `pending_approval`, record the authenticated
operator actor, note, argument digest, and policy version in audit data, and enqueue
one idempotent resume task. Approval denial produces a persisted safe result without
calling a handler. Task status is queryable at `GET /api/runs/{run_id}/tasks`.

## Coverage added or updated

- Durable API run enqueue, HTTP restart recovery, no `BackgroundTasks`, rollback,
  task-status query, and persisted SSE `task.queued` event.
- Approval request does not invoke `ToolExecutor`, duplicate approval has one task,
  and approved/denied runs resume only through `ControlWorker`.
- Malformed control payload manual review, possible-side-effect lease expiry manual
  review, provider timeout run/task failure, and lease timezone normalization.
- Existing run, approval, eval, and executor paths updated for the asynchronous
  continuation contract.

## Commands and observed output

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m pytest -q -rs
```

Output: `116 passed, 4 skipped in 7.39s`.

Skipped tests (environmental, not suppressed failures):

- `tests/test_control_queue.py:110` and `:136` require
  `AGENTGATE_TEST_DATABASE_URL` for isolated PostgreSQL queue tests.
- `tests/test_migrations.py:72` and `:111` require
  `AGENTGATE_TEST_DATABASE_URL` for isolated PostgreSQL migration tests.

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m ruff check app tests
```

Output: `All checks passed!`

```powershell
Set-Location apps/api
.\.venv\Scripts\python.exe -m mypy app
```

Output: `Success: no issues found in 50 source files`.

```powershell
Set-Location apps/web
npm run lint
npm run typecheck
npm test -- --run
```

Output: ESLint and TypeScript completed with exit code 0; Vitest reported
`7 passed` files and `10 passed` tests.

Playwright/browser E2E and Compose runtime checks were not run: this task made no
web UI change, and Task 7 owns the complete Compose topology and platform self-check.

## Self-review

- No `BackgroundTasks.add_task` remains in run/approval API or service paths.
- API mutations enqueue durable tasks and emit outbox/audit records in their mutation
  transaction; the worker uses fresh sessions and lease-aware completion.
- The worker rejects malformed/unscoped tasks and does not expose host-action
  capability through the remote Worker protocol.
- No credentials, tokens, or provider exception text are recorded in this report.

## Follow-up review fixes

- Added an atomic worker-owned, unexpired lease check for `LEASED` -> `RUNNING`.
- Added a per-claim `lease_version`; lease renewal preserves the version, while
  start and completion require the captured version to prevent stale completion.
- Added a worker heartbeat using independent sessions and a final atomic
  owner/lease renewal immediately before a possible-side-effect handler. Lost
  leases do not complete the task and are recorded as `manual_review`.
- Added focused race and lease-loss tests; the lease-loss test verifies the
  possible-side-effect handler is invoked once and is not retried.
- Denial now persists the safe result and checkpoint before emitting one
  consolidated `action.updated` event for the decision.

Follow-up verification:

```text
pytest tests/test_durable_runs.py tests/test_approval_queue.py tests/test_control_worker.py tests/test_runs_api.py tests/test_approvals.py tests/test_agent_loop.py -q
28 passed
ruff check app tests
All checks passed!
mypy app
Success: no issues found in 50 source files
```
