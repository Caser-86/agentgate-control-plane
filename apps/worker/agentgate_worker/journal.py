import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

MAX_JOURNAL_RESULT_BYTES = 4096
REDACTED = "***REDACTED***"
ALLOWED_RESULT_KEYS = frozenset(
    {"status", "worker_version", "protocol_version", "capabilities", "detail"}
)
SENSITIVE_KEY_PARTS = frozenset(
    {"apikey", "authorization", "clientsecret", "password", "passwordhash", "secret", "token"}
)


def _normalized_key(key: object) -> str:
    return "".join(character for character in str(key).lower() if character.isalnum())


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_key(key)
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _bounded_result(result: dict[str, object], max_result_bytes: int) -> dict[str, object]:
    safe = _redact(result)
    if not isinstance(safe, dict):
        raise ValueError("journal result must be an object")
    bounded: dict[str, object] = {
        key: value
        for key, value in safe.items()
        if key in ALLOWED_RESULT_KEYS
        and (
            key != "capabilities"
            or isinstance(value, list) and all(isinstance(item, str) for item in value)
        )
        and (
            key not in {"status", "worker_version", "protocol_version", "detail"}
            or isinstance(value, str)
        )
    }
    if "status" not in bounded:
        bounded["status"] = "unknown"
    encoded = json.dumps(
        bounded, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) <= max_result_bytes:
        return bounded
    bounded["truncated"] = True
    while True:
        encoded = json.dumps(
            bounded, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        if len(encoded) <= max_result_bytes:
            return bounded
        candidates = [
            key
            for key in ("detail", "status", "worker_version", "protocol_version")
            if isinstance(bounded.get(key), str) and bounded[key]
        ]
        if candidates:
            key = max(candidates, key=lambda item: len(str(bounded[item]).encode("utf-8")))
            value = str(bounded[key])
            byte_count = len(value.encode("utf-8"))
            bounded[key] = value.encode("utf-8")[: byte_count // 2].decode(
                "utf-8", errors="ignore"
            )
            continue
        if "capabilities" in bounded:
            bounded.pop("capabilities")
            continue
        bounded["status"] = ""


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
