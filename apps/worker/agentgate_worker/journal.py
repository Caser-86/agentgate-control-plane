import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

MAX_JOURNAL_RESULT_BYTES = 4096
REDACTED = "***REDACTED***"
SENSITIVE_KEYS = frozenset({"api_key", "authorization", "token", "secret", "password"})


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if str(key).lower() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _bounded_result(result: dict[str, object], max_result_bytes: int) -> dict[str, object]:
    safe = _redact(result)
    if not isinstance(safe, dict):
        raise ValueError("journal result must be an object")
    encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    if len(encoded) <= max_result_bytes:
        return safe
    bounded: dict[str, object] = {
        key: value for key, value in safe.items() if key.lower() in SENSITIVE_KEYS
    }
    bounded["status"] = str(safe.get("status", "unknown"))
    bounded["truncated"] = True
    remaining = (
        max_result_bytes
        - len(json.dumps(bounded, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        - 32
    )
    detail = safe.get("detail")
    if isinstance(detail, str) and remaining > 0:
        bounded["detail"] = detail.encode("utf-8")[: max(0, remaining)].decode(
            "utf-8", errors="ignore"
        )
    return bounded


class WorkerJournal:
    """A bounded local ledger for started tasks and results awaiting an API acknowledgement."""

    def __init__(self, path: Path, *, max_result_bytes: int = MAX_JOURNAL_RESULT_BYTES) -> None:
        if max_result_bytes < 256 or max_result_bytes > MAX_JOURNAL_RESULT_BYTES:
            raise ValueError("invalid journal result limit")
        self.path = path
        self.max_result_bytes = max_result_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_journal (
                    task_id TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record_started(self, task_id: str, request_digest: str, lease_expires_at: datetime) -> None:
        if not task_id or re.fullmatch(r"[0-9a-f]{64}", request_digest) is None:
            raise ValueError("invalid task identity")
        now = datetime.now(lease_expires_at.tzinfo).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO worker_journal
                    (task_id, request_digest, lease_expires_at, status, created_at, updated_at)
                VALUES (?, ?, ?, 'started', ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    request_digest = excluded.request_digest,
                    lease_expires_at = excluded.lease_expires_at,
                    updated_at = excluded.updated_at
                """,
                (task_id, request_digest, lease_expires_at.isoformat(), now, now),
            )

    def record_result(self, task_id: str, result: dict[str, object]) -> None:
        safe = _bounded_result(result, self.max_result_bytes)
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        now = datetime.now().isoformat()
        with self._connection() as connection:
            changed = connection.execute(
                """
                UPDATE worker_journal
                SET status = 'report_pending', result_json = ?, updated_at = ?
                WHERE task_id = ? AND status IN ('started', 'report_pending')
                """,
                (encoded, now, task_id),
            ).rowcount
        if changed != 1:
            raise ValueError("result requires a started task")

    def pending_reports(self) -> list[tuple[str, str, dict[str, object]]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT task_id, request_digest, result_json
                FROM worker_journal
                WHERE status = 'report_pending'
                ORDER BY created_at
                """
            ).fetchall()
        return [(str(task_id), str(digest), json.loads(result)) for task_id, digest, result in rows]

    def mark_reported(self, task_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM worker_journal WHERE task_id = ?", (task_id,))
