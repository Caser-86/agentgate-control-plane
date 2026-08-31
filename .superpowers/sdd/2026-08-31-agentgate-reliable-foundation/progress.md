# SDD ledger — plan: docs/superpowers/plans/2026-08-31-agentgate-reliable-foundation.md

## Execution context

- Isolated worktree: `D:/LLM Files/files/agentgate-control-plane/.worktrees/reliable-foundation`
- Branch: `codex/reliable-foundation-20260831`
- Baseline commit: `890db06` (`chore: ignore local worktrees`)
- Baseline verification: API `59 passed in 4.42s`; web `5 files / 6 tests passed`.
- Plan script note: the bundled `sdd-workspace`, `task-brief`, and `review-package` files are Bash scripts, but this Windows host has no usable Git Bash; their defined outputs are being reproduced with PowerShell in the same plan-scoped directory.

## Preflight task-conflict scan

Every planned task is represented below. A row exists for each task's own consistency and for each pair that shares a file, interface, schema, runtime boundary, or acceptance evidence.

| Tasks | Shared surface | Producer / consumer relationship | Found | Ruling / cost if wrong |
|---|---|---|---|---|
| 0 / 0 | Baseline and preservation checks | Task 0 records the clean isolated baseline used by all later tasks. | No conflict; setup only. | Ruling: Task 0 must not change product code; if it does, later diffs lose a trustworthy base. |
| 1 / 1 | `apps/api/app/models.py`, Alembic env, Compose startup | Task 1 creates the migration baseline for the models present at its point; its DB health/startup is consumed by every persistence task. | Intentional sequencing. | Ruling: Task 1 migrates only the pre-Task-2 schema; if future entities are imported early, migration history becomes non-reproducible. |
| 2 / 2 | `ControlTask`, `WorkerRegistration`, `OutboxEvent`, generic audit, repositories | Task 2 defines durable entities and repository contracts consumed by Tasks 4–8. | Intentional sequencing. | Ruling: entity state transitions and indexes are the source of truth; if repos bypass them, leases/outbox recovery can diverge. |
| 3 / 3 | Auth tables, session cookies, CSRF, adapter-token hashing | Task 3 owns authentication and token lifecycle end-to-end, including route and security tests. | Self-contained. | Ruling: opaque secrets are stored hashed and authentication is enforced centrally; if any route bypasses dependencies, local-only trust is broken. |
| 4 / 4 | Native Worker protocol, registration, leases, journal | Task 4 consumes Task 2 control-task/worker entities and Task 3 worker-token verification, then supplies protocol behavior to Tasks 6–8. | Intentional sequencing. | Ruling: phase 0 worker executes only safe self-check/journal actions; if real host mutation slips in, the security boundary is invalid. |
| 5 / 5 | Durable events, Outbox relay, SSE cursor | Task 5 owns replacement of process-local EventBroker and supplies durable stream semantics to UI/runs/approvals. | Self-contained after Task 2. | Ruling: database events are authoritative and cursors are monotonic; if memory remains authoritative, restart/reconnect loses history. |
| 6 / 6 | Run/approval services, durable queue, worker dispatch | Task 6 replaces request-bound background work with durable tasks and lease/retry behavior, consuming Tasks 2, 3, 4, and 5 contracts. | Intentional sequencing. | Ruling: API requests enqueue and return; workers resume/approve from durable state; if request lifetime owns execution, restart safety is lost. |
| 7 / 7 | `compose.yaml`, Dockerfiles, native Worker startup, `/api/v1/checks` | Task 7 assembles the runtime topology and exposes a safe platform self-check over Task 4/6 foundations. | Intentional sequencing. | Ruling: Postgres is mandatory in the supported topology, native Worker remains outside Docker for Windows access, and self-check is read-only. |
| 8 / 8 | Security, fault injection, E2E, acceptance docs | Task 8 verifies the full Phase 0 surface and documents commands/evidence from Tasks 1–7. | Self-contained acceptance task. | Ruling: security/fault tests are release gates; if they are skipped, “real local use” is unverified. |
| 1 / 2 | `models.py`, Alembic migration head, startup imports | Task 1 establishes Alembic; Task 2 extends models and creates the next migration. | Producer then consumer. | Ruling: run `alembic check` and migration upgrade after each schema extension; if heads fork, stop and repair before continuing. |
| 1 / 3 | `pyproject.toml`, `main.py`, DB/session dependencies | Task 1 adds migration/security groundwork; Task 3 adds auth runtime and routes. | Sequential dependency. | Ruling: dependencies remain additive and app startup must import all models before migration checks; if import order hides tables, schema drift results. |
| 1 / 7 | `compose.yaml`, API image/env, Postgres healthcheck | Task 1 makes API/Postgres startup verifiable; Task 7 adds the full runtime topology. | Sequential configuration merge. | Ruling: Task 7 must preserve Task 1 DB health/readiness and not reintroduce SQLite as the default. |
| 2 / 4 | Control/worker entities and repository methods | Task 2 supplies the durable records; Task 4 registers/leases/heartbeats and journals against them. | Producer then consumer. | Ruling: lease expiry and idempotency fields must be explicit before protocol code; if absent, duplicate execution cannot be distinguished. |
| 2 / 5 | `OutboxEvent`, audit repository, transaction boundaries | Task 2 defines persisted events/audit; Task 5 publishes them and exposes cursored reads. | Producer then consumer. | Ruling: Task 5 may not make an in-memory broker authoritative; transaction commit must precede delivery. |
| 2 / 6 | Control-task queue, lease repo, run/approval transitions | Task 2 defines queue/lease persistence; Task 6 dispatches runs and approvals. | Producer then consumer. | Ruling: Task 6 must use durable status transitions and reclaim expired leases, otherwise restart causes stuck work. |
| 2 / 8 | Entity constraints and fault/security tests | Task 8 asserts invariants introduced in Task 2. | Verification dependency. | Ruling: tests must exercise uniqueness, legal status transitions, idempotency, and append-only audit before acceptance. |
| 3 / 4 | Worker authentication and adapter token scope | Task 3 issues/verifies scoped adapter tokens; Task 4 authenticates native Worker protocol calls. | Producer then consumer. | Ruling: Worker identity is distinct from browser operator session; if scopes are interchangeable, token blast radius is too large. |
| 3 / 6 | Operator auth, approval routes, run routes | Task 3 supplies auth/CSRF dependencies; Task 6 protects mutations and approval resume. | Producer then consumer. | Ruling: every mutating browser route remains CSRF-protected after queue refactor; if approval bypasses session checks, the gate is ineffective. |
| 3 / 8 | Login/enrollment/token security tests | Task 8 tests Task 3's security boundary. | Verification dependency. | Ruling: secrets never appear in response/log/audit payloads; if any do, stop acceptance and redact at source. |
| 4 / 6 | Worker task protocol and durable dispatch | Task 4 handles claim/heartbeat/result; Task 6 emits and reconciles run/approval tasks. | Producer then consumer. | Ruling: task IDs and idempotency keys are reused end-to-end; if the API invents a second identity, retries can duplicate work. |
| 4 / 7 | Worker process, native startup, self-check | Task 4 provides Worker runtime; Task 7 packages its developer startup and verifies it. | Producer then consumer. | Ruling: platform self-check is the only phase 0 action exposed to Worker; if startup silently falls back to a fake Worker, acceptance must fail. |
| 4 / 8 | Worker journal, protocol fault tests | Task 8 verifies malformed messages, expiry, duplicate results, and bounded journal content. | Verification dependency. | Ruling: malformed or unauthorized commands must never execute; tests must prove that property. |
| 5 / 6 | Durable SSE/events and run/approval state changes | Task 5 supplies event publication/cursors; Task 6 emits events for durable transitions. | Sequential dependency. | Ruling: event publication is tied to committed state and reconnect uses `after_id`; if a transition has no durable event, UI state can be stale after restart. |
| 5 / 8 | SSE restart/reconnect and outbox recovery tests | Task 8 verifies Task 5's delivery guarantees. | Verification dependency. | Ruling: tests must cover reconnect from cursor, relay restart, and no duplicate event IDs. |
| 6 / 7 | API/Worker services, Compose process graph, health | Task 6 makes queue processing real; Task 7 starts the API/Worker/Postgres graph. | Sequential runtime dependency. | Ruling: no request-bound `BackgroundTasks` remain for runs/approvals; if Docker startup hides a worker failure, health/self-check must report it. |
| 6 / 8 | Run/approval fault recovery and E2E | Task 8 verifies API restart, lease reclaim, approval idempotency, and existing UI flow. | Verification dependency. | Ruling: acceptance requires evidence after process interruption, not only happy-path API tests. |
| 7 / 8 | Compose and verification commands/docs | Task 7 defines runnable topology; Task 8 documents and executes it. | Sequential acceptance dependency. | Ruling: docs must use Windows-compatible commands and explicitly identify services/ports/health; if a command is unverified, label it as such. |

## Task ledger

- [x] Task 0 — 记录现有基线并保护工作区 — implemented/verified; review approved, with evidence limits noted for tests and worktree isolation.
- [x] Task 1 — PostgreSQL、Alembic 和可验证启动 — implemented in `b6a1f8c`, fixed in `50ce4f1`; review + re-review approved.
- [x] Task 2 — 持久化任务、租约、Outbox 和通用审计实体 — implemented in `8011f92`, fixed in `9d1967f` and `254b778`; review + two re-reviews approved.
- [x] Task 3 — 单用户认证、会话、CSRF 和适配器令牌 — implemented in `b6266a0`, fixed in `5349e36` and `57fcb6d`; review + two re-reviews approved.
- [x] Task 4 — 原生 Worker 注册、租约协议和本机执行日志 — implemented in `014674b`/`05c9f9f`, fixed in `16495ae`/`7790b7a`; review + two re-reviews approved.
- [x] Task 5 — 用持久化 Outbox 替换内存事件代理 — implemented in `487f9d2`, fixed in `ba12b09`, `d110b60`, `14401bf`; review + three re-reviews approved.
- [x] Task 6 — 移除请求内后台任务并接入持久化控制 Worker — implemented in `5380d8d`, fixed in `b22744a`, `0146c34`, `8b00c3f`; review + three re-reviews approved.
- [x] Task 7 — Compose 运行拓扑、Worker 开发启动和平台自检 — implemented in `f74fa69`, fixed in `5e7249c` and `b58977a`; review + three re-reviews approved. Docker smoke remains limited by host port 8000 already being allocated.
- [x] Task 8 — 安全回归、故障注入和阶段 0 验收 — implemented in `7e5f369`, fixed through `b6b0ae8`, `3735b6e`, `eddcd2e`, `b366272`, `0757e8f`; review + five re-reviews approved. Stage 0 acceptance remains evidence-limited: E2E denial element is not rendered in the available runtime and `verify-foundation.ps1` is blocked/fails in the available environment; the reports record exact results.

## Decisions

- Ruling: Execute the approved Phase 0 plan in a dedicated Git worktree — the user selected option 1 and existing uncommitted UI work must remain isolated; cost if wrong is an extra branch/worktree to remove at handoff.
- Ruling: Keep the current root checkout untouched except the explicitly required `.gitignore` entry — current uncommitted files belong to the user; cost if wrong is accidental loss or mixing of their design work.
- Ruling: Migration integration tests must create a random loopback-only `agentgate_test_migration_*` database and drop it with `FORCE` — a name-only test guard could hit a persistent volume and produce false confidence; cost if wrong is accepting an unverified migration path.
- Ruling: Treat `50ce4f145c8205d549144204546cf57c48860c08` as the actual Task 1 fix head — the reviewer prompt contained a mistyped full SHA, but the worktree and diff resolved to this object; cost if wrong is reviewing the wrong commit range.
- Ruling: PostgreSQL lease recovery coverage must use two sessions and verify expired reclaim plus exclusive subsequent claim — single-session SQLite cannot prove the production locking contract; cost if wrong is a false concurrency guarantee. The final test uses a held row lock; independent committed-state competition remains a non-blocking observation for final review.
- Ruling: Keep `/health` as an explicitly documented anonymous infrastructure liveness exception with fixed non-business output, while protecting all browser/business API reads — existing Compose, local startup, and Playwright probes depend on anonymous liveness; cost if wrong is an unstartable local stack or an overly broad anonymous API.
- Ruling: Migration `0004` must normalize historical duplicate bootstrap rows before its uniqueness constraint — real local upgrades may encounter data from the earlier race; cost if wrong is an upgrade failure on an existing installation.
- Ruling: Keep both Worker client-side and API-side self-check result allowlists in Phase 0 — clients may be compromised or drift, so the API must revalidate before persistence; cost if wrong is command/PowerShell data entering durable task results. Future schema deduplication is a non-blocking follow-up.
- Ruling: Associate executor action events with the owning `run_id` and retain `action_id` in payload — legacy run SSE filters by run resource, and action IDs otherwise make approved execution events disappear; cost if wrong is an incomplete timeline after approval.
- Ruling: Permit an optional bounded SSE `limit` for deterministic integration tests while retaining unbounded default polling/heartbeat behavior — real HTTP stream coverage must not replace production streaming; cost if wrong is either untestable hanging streams or a changed default delivery contract.
- Ruling: Task 6 lease renewal, completion, and lost-lease recovery must be single conditional database updates keyed by worker ID and lease version; read-then-write recovery is unsafe under reclaim races, so stale workers must produce no state or Outbox changes.
- Ruling: Task 8 may add test-only E2E database reset/readiness wiring only behind the explicit test environment and SQLite guards; production PostgreSQL migration/runtime paths must remain unchanged. Stage 0 is not accepted while E2E or foundation verification lacks a passing run.

## Integration fix pass — 2026-09-01

- Applied the six requested integration fixes plus the safe check-capability clarification in the isolated worktree only: guarded lease recovery, Compose migration gate, normalized redaction, authenticated platform diagnostics, structured port/config verification, and denial-state UI/E2E repairs.
- Evidence after the requested interruption is bounded and local: API focused `33 passed, 1 skipped`; Ruff passed; web focused Vitest `2 files / 6 tests passed`; web lint/typecheck passed; PowerShell AST parse passed; cleanup verified zero connections on the temporary E2E ports.
- Prior valid bounded E2E run on free port `18220` passed both specs. No new Docker, Postgres, or E2E command was run after interruption.
- Limitations: `AGENTGATE_TEST_DATABASE_URL` is unset, so PostgreSQL two-session race coverage is skipped; live Compose/verify-foundation remains unverified and previously encountered execution-policy/loopback-environment failures; full suites were not rerun after interruption by explicit user instruction.

## Final integration fix pass — 2026-09-01

- Fixed nullable generic audit serialization, preserving resource context in API list/export and adding a `run_id=None` regression.
- Restricted v1 check proposals to the existing safe `platform.self_check` handler path; unsupported checks are audited and rejected without a durable task.
- Unified `claim_next_task` expiry recovery with the guarded scheduler recovery function so state, audit, and Outbox changes commit together; focused claim consistency coverage passes.
- Reordered `verify-foundation.ps1` so the proposed safe no-op is consumed by a temporary native Worker before heartbeat verification; temporary state cleanup is bounded and credentials are never printed.
- Fresh evidence: backend `156 passed, 5 skipped`, Ruff/mypy/evals pass; frontend lint/typecheck/Vitest `7 files, 12 tests`/build pass; Compose config and PowerShell AST pass; bounded E2E `2 passed (14.4s)` on ports 18220/18221.
- Exact limitation: Bypass foundation run failed at line 29 with `API health check failed.` because the worktree Compose stack was not running; port inspection found two unrelated listeners on 8000. PostgreSQL race tests remain skipped because `AGENTGATE_TEST_DATABASE_URL` is unset. Stage 0 remains not accepted.

## Final whole-branch review fixes — 2026-09-01

- [x] Native Worker completion atomically writes the successful ControlTask mutation, one task-scoped `task.updated` Outbox event, Worker audit event, and grant completion; succeeded replay remains idempotent. Focused regression passed.
- [x] Added authenticated read-only `GET /api/v1/checks/{check_id}` and changed `verify-foundation.ps1` to validate the exact submitted task ID, succeeded task/result status, and allowlisted result keys after the native Worker round trip. Temporary credentials/journal are removed in `finally`; token contents are never printed.
- [x] Localized RunDetailPage loading/error/failed-run copy into Chinese fixed safe text and added a regression proving underlying exception text is not exposed.
- [x] Fresh evidence: backend `157 passed, 5 skipped`; Ruff/mypy/evals pass; frontend `7 files, 13 tests`/lint/typecheck/build pass; Compose config and PowerShell AST pass; bounded E2E `2 passed` on `18220/18221`.
- [ ] Foundation live verification remains unavailable: Bypass run failed at line 29 with `API health check failed.` because the Compose API was not running. PostgreSQL race coverage remains skipped because `AGENTGATE_TEST_DATABASE_URL` is unset. No persistent/user database or service restart was used.
