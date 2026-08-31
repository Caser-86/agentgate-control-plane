# Worker Loopback Boundary and Script Parameter Fixes Implementation Plan

> **For agentic workers:** Execute each task with a failing regression test before production changes and fresh verification before commit.

**Goal:** Ensure every native Worker entry point rejects unsafe API URLs before credentials or network use, and make explicit `-ApiUrl` take precedence over PowerShell port fallback.

**Architecture:** Keep one URL policy in `apps/worker/agentgate_worker/client.py`, invoked by both `HttpTransport` and `WorkerClient`, so injected transports cannot bypass validation. Make `start-worker.ps1` parse and validate an explicit URL first, derive its port locally, and have `verify-foundation.ps1` delegate to that safe script path.

**Tech Stack:** Python 3.11, httpx, pytest, PowerShell, Docker Compose contract tests.

## Global Constraints

- Only localhost/loopback API targets are supported.
- Accept documented `http`/`https` loopback URLs, including IPv4 and IPv6 loopback.
- Reject malformed URLs, non-HTTP(S) schemes, remote DNS/IP hosts, URL credentials, query/fragment, and invalid ports before bearer/enrollment token use.
- Preserve queue/grant/auth/redaction/migration/Compose contracts; do not add host actions.
- Do not start or stop user services during bounded verification.

## Tasks

- [x] Add Worker regression coverage for unsafe `HttpTransport`, `WorkerClient`, and `main()` URLs, including no-network behavior.
- [x] Add explicit `-ApiUrl` PowerShell precedence/port derivation contract coverage and route foundation verification through `start-worker.ps1`.
- [x] Implement the shared native URL policy and PowerShell safe path without changing queue, grant, auth, redaction, migration, or Compose behavior.
- [ ] Run focused and full checks, update the ledger/report with exact evidence and limitations, and commit only this worktree.
