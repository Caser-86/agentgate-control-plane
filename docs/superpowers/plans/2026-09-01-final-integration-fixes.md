# Phase Zero Final Integration Fixes Implementation Plan

> **For agentic workers:** Execute each task with a failing regression test before production changes and fresh verification before commit.

**Goal:** Close the remaining audit, safe-check, lease-recovery, verification-script, and denial-render integration gaps without weakening Phase 0 boundaries.

**Architecture:** Keep generic audit events independent of AgentRun, accept only the existing bounded `platform.self_check` Worker path for check proposals, and centralize expired-lease recovery so its guarded state transition and audit/Outbox records share one transaction. Make foundation verification migrate/readiness-first and run the native no-op protocol round trip only after a Worker is usable.

**Tech Stack:** FastAPI/SQLModel, SQLite unit tests plus optional disposable PostgreSQL, React/Vite, PowerShell, Docker Compose.

## Tasks

- [ ] Add API regression coverage for generic audit list/export with `run_id=None` and resource context; make response fields nullable/preserved.
- [ ] Add API regression coverage rejecting unsupported read-only check proposals with a safe audit and no task; preserve the successful `platform.self_check` contract.
- [ ] Add claim-path recovery coverage for state/audit/Outbox atomicity; reuse the guarded recovery function from scheduler and claim code.
- [ ] Add verification-script ordering/contract coverage and repair the script for migration/readiness-first native self-check execution; retain loopback-only, no-secret, no-host-mutation constraints.
- [ ] Run focused and full checks, update the ledger/report with exact evidence and limitations, and commit only this worktree.
