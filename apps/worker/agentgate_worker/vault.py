import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def _normalize_dpapi_result(result: object, operation: str) -> bytes:
    if isinstance(result, bytes):
        return result
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], bytes):
        return result[1]
    raise ValueError(f"Crypt{operation}Data returned an invalid result shape")


class Protector(Protocol):
    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class DPAPIProtector:
    def protect(self, value: bytes) -> bytes:
        try:
            import win32crypt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError("Windows DPAPI support is unavailable") from error
        return _normalize_dpapi_result(
            win32crypt.CryptProtectData(value, "AgentGate Worker", None, None, None, 0),
            "Protect",
        )

    def unprotect(self, value: bytes) -> bytes:
        try:
            import win32crypt  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError("Windows DPAPI support is unavailable") from error
        return _normalize_dpapi_result(
            win32crypt.CryptUnprotectData(value, None, None, None, 0), "Unprotect"
        )


@dataclass(frozen=True)
class WorkerCredentials:
    worker_id: str
    token: str
    protocol_version: str


class WorkerVault:
    def __init__(self, path: Path, *, protector: Protector | None = None) -> None:
        self.path = path
        self.protector = protector or DPAPIProtector()

    def save(self, credentials: WorkerCredentials) -> None:
        raw = json.dumps(credentials.__dict__, separators=(",", ":")).encode("utf-8")
        protected = self.protector.protect(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".worker-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(protected)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    def load(self) -> WorkerCredentials | None:
        if not self.path.exists():
            return None
        decoded = json.loads(self.protector.unprotect(self.path.read_bytes()).decode("utf-8"))
        return WorkerCredentials(
            worker_id=str(decoded["worker_id"]),
            token=str(decoded["token"]),
            protocol_version=str(decoded["protocol_version"]),
        )
