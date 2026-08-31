# Task 8 Report: Reliable Foundation Safety Boundaries

## Changed files

- `apps/api/tests/test_security_regressions.py` — fake-secret redaction, unknown/shell denial, expired lease, digest mismatch, and unscoped client-token approval matrix.
- `apps/api/tests/test_failure_injection.py` — database disconnect before claim, pre-grant disconnect, post-grant journal reporting, and side-effect-uncertain crash coverage.
- `apps/api/app/services/audit.py` — audit/API redaction now recognizes normalized `apikey`, `access_token`, `refresh_token`, `client_secret`, and `private_key` keys in addition to existing sensitive keys.
- `apps/web/e2e/auth-and-queue.spec.ts` — Chinese first-run login, queued/running observation, approval rejection, refresh, and audit evidence flow.
- `apps/web/e2e/approval-flow.spec.ts` — login/setup-aware rejection flow with refresh and audit evidence.
- `apps/web/src/components/ApprovalCard.tsx` — matching client-side redaction allowlist.
- `apps/web/src/pages/RunDetailPage.tsx` — matching action-detail redaction allowlist.

No changes were needed in `apps/api/app/api/runs.py`, `apps/api/app/api/approvals.py`, or `apps/web/src/pages/RunsPage.tsx`; their existing contracts were exercised by the new tests/E2E selectors.

## TDD evidence

- Initial new-test run: `3 failed, 6 passed`; failures exposed test-fixture issues and confirmed the new tests were exercising real boundaries.
- After minimal test corrections and the audit redaction enhancement: `9 passed in 0.39s` for `tests/test_security_regressions.py tests/test_failure_injection.py`.

All secrets and tokens in these tests are fake literals used only for regression assertions.

## Stage 0 verification

Passed:

- `Set-Location apps/api; .\.venv\Scripts\python.exe -m ruff check app tests` — `All checks passed!`
- `Set-Location apps/api; .\.venv\Scripts\python.exe -m mypy app` — `Success: no issues found in 53 source files`
- `Set-Location apps/api; .\.venv\Scripts\python.exe -m pytest -q` — `144 passed, 4 skipped in 7.96s`
- `Set-Location apps/api; .\.venv\Scripts\python.exe -m app.evals.runner` — all six cases `4/4 PASS`.
- `Set-Location apps/web; npm.cmd run lint` — passed.
- `Set-Location apps/web; npm.cmd run typecheck` — passed.
- `Set-Location apps/web; npm.cmd test -- --run` — `7 passed`, `10 passed`.
- `Set-Location apps/web; npm.cmd run build` — Vite build passed.
- `Set-Location apps/web; npx.cmd playwright install chromium` — exit code 0.
- `docker compose config` — exit code 0.

Machine-readable eval output was written to the existing ignored `apps/api/eval-results.json` path; no secret-bearing verification output was added to Git.

## Limitations and known failures

- Exact `npm.cmd run test:e2e` with `AGENTGATE_E2E_PYTHON=..\api\.venv\Scripts\python.exe` did not start because `http://127.0.0.1:8000/health` was already in use. Read-only inspection showed listeners on port 8000 owned by PIDs `1200` and `35208`; no process was stopped or restarted.
- A retry on `AGENTGATE_E2E_API_PORT=18000` reached Playwright but both tests failed before the flow because the API's `sqlite://` server process reported the exact error `sqlite3.OperationalError: no such table: operators`. The E2E API process did start; the configured in-memory SQLite schema was not shared with request connections. The E2E tests therefore do not claim to pass.
- `scripts/verify-foundation.ps1` did not pass. Exact error: `scripts\verify-foundation.ps1:10 ... API is not loopback-only.` `docker compose config` renders structured `host_ip`, `published`, and `target` fields, while the script expects the old single-line `127.0.0.1:...` text pattern. This is recorded as a pre-existing verification-script/Compose-format mismatch; no script outside the allowed Task 8 files was changed.
- PostgreSQL-dependent tests remain the existing four skips when `AGENTGATE_TEST_DATABASE_URL` is absent.

## Scope review

- No arbitrary shell execution, remote target support, file mutation, real service restart, or model dependency was added.
- The only executable operation used by the tests is the existing in-process fake `restart_service` contract; no host command is invoked.
- `git diff --check` passed (only Git's normal LF-to-CRLF warnings appeared for Windows working-tree files).
