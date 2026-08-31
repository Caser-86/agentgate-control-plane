# Task 8 Report: Reliable Foundation Safety Boundaries

## Changed files

- `apps/api/app/services/audit.py` — server redaction normalizes hyphen, underscore, and space variants for fake secret keys.
- `apps/api/tests/test_security_regressions.py` — fake-secret redaction, unknown/shell denial, expired lease, digest mismatch, and unscoped client-token approval matrix.
- `apps/api/tests/test_failure_injection.py` — database disconnect before claim, pre-grant callable-handler guard, post-grant reconnect/journal result, control/native worker crash recovery, HTTP SSE cursor reconnect, and duplicate approval conflict/task-count coverage.
- `apps/api/tests/test_compose_contract.py` — focused contract assertion for structured Compose bindings and the foundation parser.
- `apps/web/src/components/ApprovalCard.tsx` — matching client redaction and safe generic error rendering, with stable test IDs and Chinese labels.
- `apps/web/src/components/ApprovalCard.test.tsx` — focused client secret-leak regression test.
- `apps/web/src/pages/RunsPage.tsx` and `apps/web/src/pages/RunsPage.test.tsx` — minimal Chinese display text and stable run-form test IDs.
- `apps/web/src/pages/RunDetailPage.tsx` — matching action-result redaction and localized detail text.
- `apps/web/e2e/auth-and-queue.spec.ts` — Chinese setup/login, run, queue, pending approval, deny, refresh, and audit flow.
- `apps/web/e2e/approval-flow.spec.ts` — setup-aware approval denial flow asserting persisted denied result and audit evidence.
- `scripts/verify-foundation.ps1` — parses actual structured `docker compose config` service bindings and retains health/migration/lease/heartbeat safety checks.

## TDD evidence

- Initial review-fix focused run: `3 failed, 11 passed`; failures exposed the fixture and assertion gaps before implementation correction.
- Focused green API/Compose run: `19 passed in 0.56s`.
- Full API suite: `148 passed, 4 skipped in 8.10s`.
- Frontend: lint passed; typecheck passed; Vitest `7 files, 11 tests passed`; production build passed.

All secrets and tokens in these tests are fake literals used only for regression assertions.

## Stage 0 verification

Passed checks:

- `Set-Location apps/api; .\.venv\Scripts\python.exe -m ruff check app tests` — `All checks passed!`
- `Set-Location apps/api; .\.venv\Scripts\python.exe -m mypy app` — `Success: no issues found in 53 source files`
- `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest -q` — `148 passed, 4 skipped in 8.10s`
- `Set-Location apps/api; .\.venv\Scripts\python.exe -m app.evals.runner` — all six cases `4/4 PASS`.
- `Set-Location apps/web; npm.cmd run lint` — passed.
- `Set-Location apps/web; npm.cmd run typecheck` — passed.
- `Set-Location apps/web; npm.cmd test -- --run` — `7 files, 11 tests passed`.
- `Set-Location apps/web; npm.cmd run build` — Vite build passed.
- `Set-Location apps/web; npx.cmd playwright install chromium` — exit code 0.
- `docker compose config` — exit code 0; structured `api`/`web` bindings showed `host_ip: 127.0.0.1`, expected published/target ports, and PostgreSQL had no host port.

Machine-readable eval output was written to the existing ignored `apps/api/eval-results.json` path; no secret-bearing verification output was added to Git.

Stage 0 is not accepted: the required E2E and foundation runtime checks did not pass.

## Limitations and known failures

- Exact `npm.cmd run test:e2e` with `AGENTGATE_E2E_PYTHON=..\api\.venv\Scripts\python.exe` did not start because `http://127.0.0.1:8000/health` was already in use. Read-only inspection showed listeners on port 8000 owned by PIDs `1200` and `35208`; no process was stopped or restarted.
- A bounded retry on `AGENTGATE_E2E_API_PORT=18000` reached Playwright but both tests failed before the flow because the API server reported the exact error `sqlite3.OperationalError: no such table: operators`. The E2E API process did start; the configured in-memory SQLite schema was not shared with request connections. The E2E tests therefore do not claim to pass. Docker/Playwright can be retried with a free port and initialized PostgreSQL.
- `scripts\verify-foundation.ps1` now parses the structured Compose bindings, but a bounded run did not pass the live health gate. Exact error: `scripts\verify-foundation.ps1:28 ... API health check failed.` No service was started, stopped, or restarted.
- PostgreSQL-dependent tests remain the existing four skips when `AGENTGATE_TEST_DATABASE_URL` is absent.

## Scope review

- No arbitrary shell execution, remote target support, file mutation, real service restart, or model dependency was added.
- The only executable operation used by the tests is the existing in-process fake `restart_service` contract; no host command is invoked.
- `git diff --check` passed (only Git's normal LF-to-CRLF warnings appeared for Windows working-tree files).
