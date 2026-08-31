from datetime import UTC, datetime, timedelta

from agentgate_worker.journal import WorkerJournal


def test_journal_replays_result_after_api_disconnect(tmp_path: object) -> None:
    """Removing a pending row after a disconnect would lose the only durable result copy."""
    journal = WorkerJournal(tmp_path / "journal.db")  # type: ignore[operator]
    lease_expires_at = datetime.now(UTC) + timedelta(seconds=30)

    journal.record_started("task-1", "a" * 64, lease_expires_at)
    journal.record_result("task-1", {"status": "succeeded"})

    assert journal.pending_reports() == [("task-1", "a" * 64, {"status": "succeeded"})]


def test_journal_redacts_and_bounds_persisted_result(tmp_path: object) -> None:
    """Removing result sanitisation would persist secrets or unbounded host data locally."""
    journal = WorkerJournal(tmp_path / "journal.db")  # type: ignore[operator]
    journal.record_started("task-2", "b" * 64, datetime.now(UTC) + timedelta(seconds=30))

    journal.record_result("task-2", {"token": "never-store", "detail": "x" * 10_000})

    result = journal.pending_reports()[0][2]
    assert result["token"] == "***REDACTED***"
    assert len(result["detail"]) < 10_000
