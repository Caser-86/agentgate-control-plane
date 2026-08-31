# Task 8 final verification report

## Evidence

- Script contract coverage: `10 passed` (`apps/api/tests/test_compose_contract.py`). It proves the three local scripts parse Compose host ports and that foundation verification selects `apps/worker/.venv`, checks `win32crypt`, and never falls back to `apps/api/.venv`.
- Worker tests: `8 passed`. The local-only `apps/worker/.venv` was created and installed with `pip install -e apps/worker`; `import win32crypt` succeeded.
- Backend: `165 passed, 5 skipped`; Ruff: `All checks passed!`; mypy: `Success: no issues found in 53 source files`.
- Frontend: lint, typecheck and build exited `0`; unit tests: `7` files / `13` tests passed.
- `docker compose config`: exited `0`; Postgres has no published port and API/Web remain loopback-only. With `AGENTGATE_API_PORT=18000` and `AGENTGATE_WEB_PORT=15173`, rendered host ports were `18000/15173`.
- PowerShell parser checks for `start-local.ps1`, `setup-local.ps1`, and `verify-foundation.ps1`, plus `git diff --check`, exited `0`.

## Limitations

- No bounded E2E or live foundation verification was run: doing so would require starting Compose services, and this task explicitly prohibited starting/stopping user services without an explicit bounded operation.
- No PostgreSQL runtime test was available because `AGENTGATE_TEST_DATABASE_URL` is not configured; the existing PostgreSQL tests remain skipped under their own fixture rules.
- The local Worker environment is ignored/local-only and is not part of the commit. `setup-local.ps1` recreates or updates it idempotently without printing token contents.

## Final port and Worker runtime fix pass — 2026-09-01

- `AGENTGATE_API_PORT=18000` and `AGENTGATE_WEB_PORT=15173` render loopback API/Web bindings and matching API CORS/Web runtime configuration; defaults render as `8000/5173`.
- API focused port/Compose contract: `16 passed`; API full: `169 passed, 5 skipped`; Ruff/mypy/evals passed. Web: lint/typecheck/build passed and `7 files / 14 tests passed`. Worker: `8 passed` plus `win32crypt` import from `apps/worker/.venv`.
- `start-worker.ps1` derives the API port from `docker compose config --format json` when no URL/port is supplied, accepts only loopback HTTP URLs, and never falls back to `apps/api/.venv`. Setup and foundation verification use the same Worker environment and do not print token contents.

Limitations: no Compose lifecycle was run. The read-only foundation verification attempt reported `API health check failed` because the Compose API was not running; Docker image build, live foundation verification, and PostgreSQL runtime tests are not claimed. The bounded temporary E2E run completed earlier with `2 passed` on `18220/18221`, and its ports were clean afterward.
