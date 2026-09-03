import argparse
import os
from pathlib import Path

from agentgate_worker.client import WorkerClient, WorkerProtocolError
from agentgate_worker.journal import WorkerJournal
from agentgate_worker.vault import WorkerVault


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the safe native AgentGate Worker once")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--state-dir", type=Path, default=Path(".agentgate-worker"))
    parser.add_argument("--name", default="local-worker")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument(
        "--enrollment-token", default=os.environ.get("AGENTGATE_WORKER_ENROLLMENT_TOKEN")
    )
    return parser


def main() -> int:
    options = _parser().parse_args()
    client = WorkerClient(
        base_url=options.api_url,
        vault=WorkerVault(options.state_dir / "credentials.bin"),
        journal=WorkerJournal(options.state_dir / "journal.db"),
        worker_name=options.name,
        worker_version=options.version,
        capabilities={"platform.self_check", "monitor.http", "monitor.windows_service"},
    )
    try:
        if client.vault.load() is None:
            if not options.enrollment_token:
                raise WorkerProtocolError("A one-time worker enrollment token is required")
            client.register(options.enrollment_token)
        client.heartbeat()
        client.recover_pending_reports()
        grant = client.claim()
        if grant is not None:
            client.start(grant)
            client.complete(grant, client.probe_result(grant))
    except WorkerProtocolError as error:
        print(f"Worker request failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
