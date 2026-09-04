import argparse
import os
import signal
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from agentgate_worker.client import TaskGrant, WorkerClient, WorkerProtocolError
from agentgate_worker.journal import WorkerJournal
from agentgate_worker.vault import WorkerVault


class WorkerRuntimeClient(Protocol):
    def heartbeat(self) -> None: ...

    def recover_pending_reports(self) -> int: ...

    def claim(self) -> TaskGrant | None: ...

    def start(self, grant: TaskGrant) -> None: ...

    def probe_result(self, grant: TaskGrant) -> dict[str, object]: ...

    def complete(self, grant: TaskGrant, result: dict[str, object]) -> None: ...


def _bounded_seconds(value: str, *, minimum: float, maximum: float) -> float:
    try:
        seconds = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("seconds must be a number") from error
    if not minimum <= seconds <= maximum:
        raise argparse.ArgumentTypeError(
            f"seconds must be between {minimum:g} and {maximum:g}"
        )
    return seconds


def _poll_seconds(value: str) -> float:
    return _bounded_seconds(value, minimum=0.1, maximum=60.0)


def _heartbeat_seconds(value: str) -> float:
    return _bounded_seconds(value, minimum=1.0, maximum=60.0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the safe native AgentGate Worker")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state-dir", type=Path, default=Path(".agentgate-worker"))
    parser.add_argument("--name", default="local-worker")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep the Worker running and poll for monitoring tasks",
    )
    parser.add_argument(
        "--poll-seconds",
        type=_poll_seconds,
        default=1.0,
        help="Seconds between task polls in loop mode (0.1-60)",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=_heartbeat_seconds,
        default=10.0,
        help="Seconds between heartbeats in loop mode (1-60)",
    )
    parser.add_argument(
        "--enrollment-token", default=os.environ.get("AGENTGATE_WORKER_ENROLLMENT_TOKEN")
    )
    return parser


def _process_worker_tasks(client: WorkerRuntimeClient) -> None:
    client.recover_pending_reports()
    grant = client.claim()
    if grant is not None:
        client.start(grant)
        client.complete(grant, client.probe_result(grant))


def run_worker_cycle(client: WorkerRuntimeClient) -> None:
    client.heartbeat()
    _process_worker_tasks(client)


def run_worker_loop(
    client: WorkerRuntimeClient,
    *,
    stop_event: threading.Event,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 10.0,
    wait: Callable[[float], bool] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    wait_for_stop = wait or stop_event.wait
    next_heartbeat = 0.0
    retry_delay = 1.0

    while not stop_event.is_set():
        try:
            now = monotonic()
            if now >= next_heartbeat:
                client.heartbeat()
                next_heartbeat = now + heartbeat_seconds
            _process_worker_tasks(client)
            retry_delay = 1.0
            if wait_for_stop(poll_seconds):
                return
        except WorkerProtocolError as error:
            print(f"Worker request failed: {error}")
            if wait_for_stop(retry_delay):
                return
            retry_delay = min(retry_delay * 2, 30.0)


def _install_stop_handlers(stop_event: threading.Event) -> None:
    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)


def main() -> int:
    options = _parser().parse_args()
    client = WorkerClient(
        base_url=options.api_url,
        vault=WorkerVault(options.state_dir / "credentials.bin"),
        journal=WorkerJournal(options.state_dir / "journal.db"),
        worker_name=options.name,
        worker_version=options.version,
        capabilities={
            "platform.self_check",
            "monitor.http",
            "monitor.windows_service",
            "file.inspect.v1",
            "file.quarantine.v1",
            "file.restore.v1",
        },
    )
    try:
        if client.vault.load() is None:
            if not options.enrollment_token:
                raise WorkerProtocolError("A one-time worker enrollment token is required")
            client.register(options.enrollment_token)
        if options.loop:
            stop_event = threading.Event()
            _install_stop_handlers(stop_event)
            run_worker_loop(
                client,
                stop_event=stop_event,
                poll_seconds=options.poll_seconds,
                heartbeat_seconds=options.heartbeat_seconds,
            )
        else:
            run_worker_cycle(client)
    except WorkerProtocolError as error:
        print(f"Worker request failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
