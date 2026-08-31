from agentgate_worker.vault import WorkerCredentials, WorkerVault


class FakeProtector:
    def protect(self, value: bytes) -> bytes:
        return b"protected:" + value[::-1]

    def unprotect(self, value: bytes) -> bytes:
        assert value.startswith(b"protected:")
        return value.removeprefix(b"protected:")[::-1]


def test_vault_uses_injected_protector_without_storing_plaintext(tmp_path: object) -> None:
    """Removing vault protection would leave the Worker bearer token readable on disk."""
    path = tmp_path / "worker-credentials.bin"  # type: ignore[operator]
    vault = WorkerVault(path, protector=FakeProtector())
    credentials = WorkerCredentials(
        worker_id="worker-1", token="worker-token-for-test", protocol_version="1.0"
    )

    vault.save(credentials)

    assert b"worker-token-for-test" not in path.read_bytes()
    assert vault.load() == credentials
