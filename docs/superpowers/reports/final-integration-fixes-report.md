# Final integration fixes verification report

## Worker loopback boundary and explicit URL fix — 2026-09-01

### Changes

- Added one shared native Worker URL policy used by `HttpTransport` and `WorkerClient` before default or injected transport use. It accepts HTTP(S) `localhost`, IPv4 loopback, and IPv6 loopback; rejects malformed URLs, unsafe schemes/hosts, URL credentials, query/fragment, paths, and invalid ports.
- Added direct Worker client and main-entry-point regression tests proving unsafe URLs fail before `httpx.request`; updated the in-process failure-injection fixture to use a documented loopback URL.
- Changed `start-worker.ps1` to parse explicit `-ApiUrl` first and derive/validate its port without consulting `-ApiPort`, environment, or Compose fallback. `verify-foundation.ps1` now invokes that script for the native round trip.

### Fresh evidence

- Worker: `19 passed`; Worker Ruff: `All checks passed!`.
- Backend: `171 passed, 5 skipped`; API Ruff: `All checks passed!`; mypy: `Success: no issues found in 53 source files`.
- Frontend: lint/typecheck/build exited `0`; Vitest: `7` files / `14` tests passed.
- Compose default and alternate-port (`18000`/`15173`) config exited `0`.
- PowerShell parser checks for `start-worker.ps1` and `verify-foundation.ps1` exited `0`; bounded script execution rejected `http://example.com:8000` before Worker runtime/network use.
- `git diff --check` exited `0`.

### Limitations

- No Compose service was started or stopped. Live `verify-foundation.ps1`, Docker image build, bounded browser E2E, and PostgreSQL runtime tests are not claimed.
- PostgreSQL tests remain skipped because `AGENTGATE_TEST_DATABASE_URL` is not configured.

## Scope

针对最终审查中的 Worker grant 恢复、check submitter 隔离、check proposal 观测原子性，以及 self-check 安全边界完成修复；本轮补齐了原生 Worker 环境与可变 Compose host 端口集成。未执行真实宿主机动作。

## Evidence

- Backend focused: `33 passed, 4 skipped`（后续包含全部相关回归：`29 passed, 2 skipped`）。
- Backend full: `163 passed, 5 skipped`。
- Ruff: `All checks passed!`。
- mypy: `Success: no issues found in 53 source files`。
- Frontend lint/typecheck/unit/build: lint、typecheck、build 退出码 0；`7` test files、`13` tests passed。
- Deterministic eval: `6` cases，全部 `4/4 PASS`。
- `docker compose config`: 成功；loopback API/Web、未发布 Postgres 端口和迁移依赖均保留。
- `AGENTGATE_API_PORT=18000`、`AGENTGATE_WEB_PORT=15173` 的 Compose 配置覆盖验证成功；三个本地脚本从 `docker compose config --format json` 读取实际 loopback host 端口，健康检查使用派生 API 端口。
- 原生 Worker 固定使用本地-only `apps/worker/.venv`，安装 `apps/worker` editable 依赖并验证 `win32crypt`；契约测试证明不会静默使用 API-only `.venv`。
- 首次 Compose 构建完成，但 migrate 因 revision 长度超过 `VARCHAR(32)` 失败；已修正 revision。第二次 Docker 构建在 30 秒有界窗口内仍处于依赖下载，已终止，未将其记录为通过。
- 可用的 disposable PostgreSQL 测试 URL 未配置，因此 PostgreSQL 并发/迁移用例按测试自身规则跳过。

## Limitations

本报告不宣称修正后的 Compose migration、bounded browser E2E、live `verify-foundation.ps1` 或 disposable PostgreSQL 已通过；本轮未启动用户服务，且需要隔离 Postgres 与可控运行态后重新运行。详细 Task 8 证据见 [task-8-report.md](task-8-report.md)。

## Final port and Worker runtime fix pass — 2026-09-01

- Added one local port contract: `AGENTGATE_API_PORT`/`AGENTGATE_WEB_PORT` default to `8000`/`5173`; Compose publishes loopback ports, API derives CORS origins, Vite derives dev proxy/API base, and the built Web image writes its runtime API base from `AGENTGATE_API_BASE_URL`.
- Alternate-port/config/client regression coverage: `16 passed`; rendered `18000/15173` values align across published ports, API Web port, and Web runtime API URL.
- `start-worker.ps1` now uses `apps/worker/.venv`, validates `win32crypt`, derives the API port from rendered Compose config, and rejects non-loopback URLs. Setup validates the same environment; `verify-foundation.ps1` uses it and never prints token contents.
- Fresh backend: `169 passed, 5 skipped`; Ruff/mypy/evals pass. Fresh frontend: lint/typecheck/build pass; Vitest `7 files / 14 tests passed`. Worker: `8 passed` plus `win32crypt` import. Default/alternate Compose config, PowerShell parse, and `git diff --check` passed.

Limitations: no Compose services were started or stopped. A read-only `verify-foundation.ps1` attempt failed at API health because the stack was not running; no live foundation verification, Docker image build, or PostgreSQL runtime test is claimed. Bounded temporary E2E previously completed with `2 passed` on `18220/18221`.
