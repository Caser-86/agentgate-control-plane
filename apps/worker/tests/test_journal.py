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
    assert "token" not in result
    assert len(result["detail"]) < 10_000


def test_journal_normalizes_compound_sensitive_keys_and_drops_commands(tmp_path: object) -> None:
    journal = WorkerJournal(tmp_path / "journal.db")  # type: ignore[operator]
    journal.record_started("task-3", "c" * 64, datetime.now(UTC) + timedelta(seconds=30))

    journal.record_result(
        "task-3",
        {
            "status": "succeeded",
            "apiKey": "secret-api-key",
            "client_secret": "secret-client-secret",
            "password_hash": "secret-password-hash",
            "command": "powershell Remove-Item -Recurse C:\\",
            "unknown": "discard-me",
        },
    )

    result = journal.pending_reports()[0][2]
    assert result == {"status": "succeeded"}
    assert "secret-api-key" not in (tmp_path / "journal.db").read_bytes().decode("utf-8", "ignore")


def test_journal_result_bytes_never_exceed_configured_limit(tmp_path: object) -> None:
    journal = WorkerJournal(tmp_path / "journal.db", max_result_bytes=256)  # type: ignore[operator]
    journal.record_started("task-4", "d" * 64, datetime.now(UTC) + timedelta(seconds=30))

    journal.record_result(
        "task-4",
        {"status": "s" * 10_000, "detail": "d" * 10_000, "command": "cmd.exe /c whoami"},
    )

    result = journal.pending_reports()[0][2]
    import json

    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 256
    assert len(result["status"]) < 10_000
    assert len(result["detail"]) < 10_000
