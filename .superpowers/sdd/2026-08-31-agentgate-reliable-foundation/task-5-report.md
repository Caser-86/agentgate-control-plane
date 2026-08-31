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
