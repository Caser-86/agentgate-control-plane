# Task 3 Report — Local Operator Authentication

## Scope delivered

- Added a single local `Operator`, opaque `WebSession`, one-time `BootstrapToken`, and scoped `ClientToken` persistence model with Alembic revision `0003_auth_tables`.
- Passwords use Argon2id; sessions, bootstrap enrollment values, CSRF values, and adapter tokens are persisted only as SHA-256 digests. Raw adapter tokens are emitted only by token creation/rotation responses and are never written to audit data.
- On non-test startup, a first-run bootstrap token is created in the configured token file with a bounded lifetime. Setup atomically consumes it, creates the sole operator, and removes the file. Reuse and expiry are rejected.
- Added HttpOnly, SameSite=Strict session cookies, an explicit cookie Secure setting, server-side session revocation, exact configured-Origin CSRF validation for cookie-authenticated mutations, and CSRF rotation/read endpoint support.
- Protected existing browser API reads and mutations with the operator dependency. Approval actors now derive from the authenticated operator; request-body actor input is rejected.
- Added scoped Bearer-token v1 proposal endpoints for events, checks, and actions. Events are durable audit observations; checks only create read-only durable control tasks; actions validate registry target/parameters and return policy output without accepting a caller final decision.
- Added Chinese AuthProvider/LoginPage flow. It fetches status, redirects unauthenticated routes, retains CSRF only in memory, sends it on mutations, clears it on 401, and exposes stable client error codes without surfacing backend error messages.

## Tests and verification

- `apps/api`: focused auth/v1 pytest: `13 passed`.
- `apps/api`: full pytest: `87 passed, 3 skipped`.
- `apps/api`: `ruff check app tests`: passed.
- `apps/api`: `mypy app`: passed.
- `apps/web`: full Vitest run: `7 passed` files, `8 passed` tests.
- `apps/web`: `npm run typecheck`: passed.
- `apps/web`: `npm run lint`: passed.

## Prior blocker and repair

The first frontend focused test run failed because the brief-required `AuthProvider.tsx` and `LoginPage.tsx` files did not exist. They were implemented, connected to `App.tsx`, and their authentication-flow tests now pass. The full API run then identified old anonymous browser-route tests; their fixtures were updated to establish a real local operator session with CSRF, preserving explicit unauthenticated coverage in the new authentication tests.

## Review notes

- No Worker runtime, SSE protocol work, controls, filesystem, scripts, or shell execution was added.
- Existing historical migration files contain independent style debt when linting the entire repository root; Task 3 validation uses the application and test targets required for this change, both clean.
