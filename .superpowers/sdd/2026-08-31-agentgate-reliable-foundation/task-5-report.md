# Task 5 Report: Durable Outbox Events

## Delivered

- Replaced the process-local `EventBroker` as the event source with ordered `OutboxEvent` reads.
- Added durable generic `GET /api/v1/events` and cursor-based legacy run SSE at `GET /api/runs/{run_id}/events`.
- Added bounded SSE payload serialization with redaction, 15-second heartbeats, replay via `Last-Event-ID` or `after`, and polling from fresh database sessions.
- Added at-least-once relay acknowledgement: failed delivery leaves `published_at` unset; a restarted relay retries it; duplicate acknowledgement is harmless.
- Made run, action, approval, execution, audit, and failure event writes share their relevant state-transition transaction.
- Updated browser reconnects to retain a numeric cursor, use exponential backoff capped at 30 seconds, and refresh REST state only after a successful reconnect. Stale or malformed frames are ignored.

## Verification

- Focused backend: `python -m pytest tests/test_outbox_stream.py tests/test_sse.py tests/test_agent_loop.py tests/test_approvals.py -q` — 20 passed.
- Complete API: `python -m pytest -q` — 105 passed, 4 skipped (PostgreSQL-only tests require `AGENTGATE_TEST_DATABASE_URL`).
- API static checks: `python -m ruff check app tests` and `python -m mypy app` — passed.
- Web: `npm.cmd test -- --run`, `npm.cmd run lint`, and `npm.cmd run typecheck` — passed (10 tests).

## Scope

Task 6 request-bound `BackgroundTasks` behavior was intentionally retained; no Worker scheduling or real host action was added.

## Fix Round 1

- Changed executor `action.updated` Outbox events to use the owning `run_id` as `resource_id`; `action_id` remains in the payload. This preserves run-scoped SSE replay without changing the Outbox schema and leaves generic no-run events unchanged.
- Added a real run endpoint handler regression: an approved action is executed, its running and succeeded events are read from `/api/runs/{run_id}/events`, and reconnecting with `Last-Event-ID` plus `after` replays the next sequence exactly once.
- Focused command: `python -m pytest tests/test_sse.py tests/test_outbox_stream.py tests/test_agent_loop.py tests/test_approvals.py tests/test_executor.py -q` — 27 passed.

## Fix Round 2

- Added a FastAPI `TestClient` integration regression for `GET /api/runs/{run_id}/events`. The test creates a run and an approved action in the fixture database, executes it, and lets the real Outbox reader provide a finite number of frames so the HTTP response completes.
- The first request replays the action `running` and `succeeded` frames. A second HTTP request sends both `Last-Event-ID` and `after`; it replays only the next persisted sequence, proving run-scoped cursor recovery does not duplicate the action event.
- Focused command: `python -m pytest tests/test_sse.py tests/test_outbox_stream.py tests/test_executor.py -q` — 18 passed.
- Static commands: `python -m ruff check app tests` and `python -m mypy app` — passed.
