import sys
import threading
from datetime import UTC, datetime, timedelta

import pytest

from agentgate_worker.client import TaskGrant, WorkerProtocolError
from agentgate_worker.main import _parser, main, run_worker_loop


class FakeRuntimeClient:
    def __init__(
        self,
        grants: list[TaskGrant] | None = None,
        errors: list[WorkerProtocolError] | None = None,
    ) -> None:
        self.grants = list(grants or [])
        self.errors = list(errors or [])
        self.calls: list[str] = []

    def _raise_next_error(self) -> None:
        if self.errors:
            raise self.errors.pop(0)

    def heartbeat(self) -> None:
        self.calls.append("heartbeat")
        self._raise_next_error()

    def recover_pending_reports(self) -> int:
        self.calls.append("recover")
        self._raise_next_error()
        return 0

    def claim(self) -> TaskGrant | None:
        self.calls.append("claim")
        self._raise_next_error()
        return self.grants.pop(0) if self.grants else None

    def start(self, grant: TaskGrant) -> None:
        self.calls.append(f"start:{grant.task_id}")

    def probe_result(self, grant: TaskGrant) -> dict[str, object]:
        self.calls.append(f"probe:{grant.task_id}")
        return {"status": "healthy", "detail": "test"}

    def file_result(self, grant: TaskGrant) -> dict[str, object]:
        self.calls.append(f"file:{grant.task_id}")
        return {
            "status": "succeeded",
            "result_kind": "file_metadata",
            "side_effect": "none",
            "content_sha256": "a" * 64,
            "size_bytes": 1,
        }

    def complete(self, grant: TaskGrant, result: dict[str, object]) -> None:
        self.calls.append(f"complete:{grant.task_id}")


def _test_grant() -> TaskGrant:
    return TaskGrant(
        task_id="task-1",
        idempotency_key="idempotency-1",
        request_digest="digest-1",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        payload={"task_type": "platform.self_check"},
    )


def test_main_rejects_remote_api_url_before_enrollment_or_network(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_network_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call must not occur for a rejected API URL")

    monkeypatch.setattr("httpx.request", fail_if_network_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agentgate-worker",
            "--api-url",
            "http://example.com:8000",
            "--state-dir",
            str(tmp_path),
            "--enrollment-token",
            "test-enrollment-token",
        ],
    )

    with pytest.raises(ValueError, match="loopback"):
        main()


def test_worker_loop_heartbeats_and_processes_claimed_task() -> None:
    client = FakeRuntimeClient(grants=[_test_grant()])
    stop_event = threading.Event()

    def wait_for_stop(_seconds: float) -> bool:
        stop_event.set()
        return True

    run_worker_loop(
        client,
        stop_event=stop_event,
        poll_seconds=0.1,
        heartbeat_seconds=10.0,
        wait=wait_for_stop,
    )

    assert client.calls == [
        "heartbeat",
        "recover",
        "claim",
        "start:task-1",
        "probe:task-1",
        "complete:task-1",
    ]


def test_worker_loop_routes_file_task_to_file_executor() -> None:
    grant = TaskGrant(
        task_id="file-task-1",
        idempotency_key="idempotency-1",
        request_digest="a" * 64,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=1),
        payload={"task_type": "file.inspect.v1"},
        capability="file.inspect.v1",
    )
    client = FakeRuntimeClient(grants=[grant])
    stop_event = threading.Event()

    def wait_for_stop(_seconds: float) -> bool:
        stop_event.set()
        return True

    run_worker_loop(client, stop_event=stop_event, wait=wait_for_stop)

    assert "file:file-task-1" in client.calls
    assert "probe:file-task-1" not in client.calls


def test_worker_loop_keeps_polling_when_queue_is_empty() -> None:
    client = FakeRuntimeClient()
    stop_event = threading.Event()
    waits: list[float] = []

    def wait_for_stop(seconds: float) -> bool:
        waits.append(seconds)
        if len(waits) == 2:
            stop_event.set()
        return stop_event.is_set()

    run_worker_loop(
        client,
        stop_event=stop_event,
        poll_seconds=0.25,
        heartbeat_seconds=10.0,
        wait=wait_for_stop,
    )

    assert client.calls == ["heartbeat", "recover", "claim", "recover", "claim"]
    assert waits == [0.25, 0.25]


def test_worker_loop_uses_bounded_backoff_after_protocol_error() -> None:
    client = FakeRuntimeClient(errors=[WorkerProtocolError("temporary failure")])
    stop_event = threading.Event()
    waits: list[float] = []

    def wait_for_stop(seconds: float) -> bool:
        waits.append(seconds)
        stop_event.set()
        return True

    run_worker_loop(
        client,
        stop_event=stop_event,
        poll_seconds=0.1,
        heartbeat_seconds=10.0,
        wait=wait_for_stop,
    )

    assert client.calls == ["heartbeat"]
    assert waits == [1.0]


@pytest.mark.parametrize(
    ("argument", "value"),
    [("--poll-seconds", "0.09"), ("--poll-seconds", "60.1"), ("--heartbeat-seconds", "0.9")],
)
def test_parser_rejects_unsafe_worker_timings(argument: str, value: str) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args([argument, value])
