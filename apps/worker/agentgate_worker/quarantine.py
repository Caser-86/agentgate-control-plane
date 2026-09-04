import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from uuid import UUID

from agentgate_worker.client import WorkspaceContext
from agentgate_worker.filesystem import FileActionError, FileConnector, _normalize_relative_path


@dataclass(frozen=True)
class QuarantineEntryView:
    id: UUID
    workspace_id: str
    action_id: UUID
    original_relative_path: str
    quarantine_relative_path: str
    quarantine_absolute_path: str
    content_sha256: str
    size_bytes: int
    status: str


@dataclass(frozen=True)
class QuarantineResult:
    status: str
    entry: QuarantineEntryView
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class RestoreResult:
    status: str
    entry_id: UUID
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class RecoveryNotice:
    action_id: str
    decision: str


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise FileActionError("file_read_failed", "文件摘要读取失败") from error
    return digest.hexdigest(), size


def _append_journal(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"created_at": datetime.now(UTC).isoformat(), **record}
    with path.open("a", encoding="utf-8") as journal:
        journal.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        journal.flush()
        os.fsync(journal.fileno())


def _read_journal(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _move_without_replace(source: Path, destination: Path) -> None:
    try:
        import win32file  # type: ignore[import-untyped]

        win32file.MoveFileEx(
            str(source),
            str(destination),
            win32file.MOVEFILE_WRITE_THROUGH,
        )
    except ImportError:
        try:
            os.rename(source, destination)
        except FileExistsError as error:
            raise FileActionError("destination_conflict", "目标文件已存在，未覆盖") from error
        except OSError as error:
            raise FileActionError("move_failed", "文件移动失败，状态需要复核") from error
    except Exception as error:
        if getattr(error, "winerror", None) in {80, 183}:
            raise FileActionError("destination_conflict", "目标文件已存在，未覆盖") from error
        if error.__class__.__module__ not in {"pywintypes", "win32file"}:
            raise
        raise FileActionError("move_failed", "文件移动失败，状态需要复核") from error


def _validate_missing_destination(context: WorkspaceContext, relative_path: str) -> Path:
    normalized = _normalize_relative_path(relative_path)
    root = Path(context.root_path)
    destination = root.joinpath(*normalized.split("/"))
    try:
        root_case = os.path.normcase(str(root))
        destination_case = os.path.normcase(str(destination))
        if os.path.commonpath([root_case, destination_case]) != root_case:
            raise FileActionError("path_escape", "恢复目标越过工作区边界")
    except ValueError as error:
        raise FileActionError("path_escape", "恢复目标使用了不同卷") from error
    current = root
    for segment in normalized.split("/")[:-1]:
        current = current / segment
        try:
            metadata = os.lstat(current)
        except FileNotFoundError as error:
            raise FileActionError("parent_not_found", "恢复目标父目录不存在") from error
        if getattr(metadata, "st_file_attributes", 0) & 0x0400 or current.is_symlink():
            raise FileActionError("reparse_point_denied", "恢复目标父目录包含 reparse point")
        if not stat.S_ISDIR(metadata.st_mode):
            raise FileActionError("parent_not_directory", "恢复目标父级不是目录")
    if os.path.lexists(destination):
        raise FileActionError("destination_conflict", "目标文件已存在，未覆盖")
    return destination


class QuarantineService:
    def __init__(self, journal_path: Path, connector: FileConnector | None = None) -> None:
        self.journal_path = journal_path
        self.connector = connector or FileConnector()

    def _completed(self, action_id: UUID) -> QuarantineResult | None:
        for record in reversed(_read_journal(self.journal_path)):
            if record.get("action_id") != str(action_id) or record.get("phase") != "completed":
                continue
            size_bytes = record.get("size_bytes")
            if not isinstance(size_bytes, int) or size_bytes < 0:
                continue
            entry = QuarantineEntryView(
                id=UUID(str(record["entry_id"])),
                workspace_id=str(record["workspace_id"]),
                action_id=action_id,
                original_relative_path=str(record["original_relative_path"]),
                quarantine_relative_path=str(record["quarantine_relative_path"]),
                quarantine_absolute_path=str(record["quarantine_absolute_path"]),
                content_sha256=str(record["content_sha256"]),
                size_bytes=size_bytes,
                status="quarantined",
            )
            return QuarantineResult("quarantined", entry, entry.content_sha256, entry.size_bytes)
        return None

    def quarantine(
        self,
        context: WorkspaceContext,
        action_id: UUID,
        relative_path: str,
        expected_digest: str | None = None,
    ) -> QuarantineResult:
        completed = self._completed(action_id)
        if completed is not None:
            return completed
        normalized, source = self.connector._safe_file(context, relative_path)
        if _protected_match(normalized, context.protected_patterns):
            raise FileActionError("protected_path", "目标路径受保护，未执行任何变化")
        digest, size = _sha256(source)
        if expected_digest is not None and expected_digest != digest:
            raise FileActionError("source_changed", "文件摘要已变化，未执行隔离")
        quarantine_root = Path(context.quarantine_root_path)
        quarantine_root.mkdir(parents=True, exist_ok=True)
        try:
            if os.stat(source).st_dev != os.stat(quarantine_root).st_dev:
                raise FileActionError("quarantine_volume_mismatch", "隔离区必须与工作区位于同一卷")
            workspace_root = Path(context.root_path)
            if os.path.commonpath(
                [os.path.normcase(str(workspace_root)), os.path.normcase(str(quarantine_root))]
            ) == os.path.normcase(str(workspace_root)):
                raise FileActionError(
                    "quarantine_root_inside_workspace",
                    "隔离区不能位于工作区内部",
                )
        except ValueError as error:
            raise FileActionError(
                "quarantine_volume_mismatch",
                "隔离区必须与工作区位于同一卷",
            ) from error
        entry_id = UUID(str(action_id))
        quarantine_relative = f"entries/{entry_id.hex}/{Path(normalized).name}"
        destination = quarantine_root.joinpath(*quarantine_relative.split("/"))
        if destination.exists():
            raise FileActionError("quarantine_destination_exists", "隔离目标已存在，状态需要复核")
        destination.parent.mkdir(parents=True, exist_ok=True)
        _append_journal(
            self.journal_path,
            {
                "phase": "prepared",
                "action_id": str(action_id),
                "entry_id": str(entry_id),
                "workspace_id": context.workspace_id,
                "original_relative_path": normalized,
                "quarantine_relative_path": quarantine_relative,
                "quarantine_absolute_path": str(destination),
                "content_sha256": digest,
                "size_bytes": size,
            },
        )
        _move_without_replace(source, destination)
        actual_digest, actual_size = _sha256(destination)
        if actual_digest != digest or actual_size != size:
            raise FileActionError("quarantine_verify_failed", "隔离后摘要校验失败，状态需要复核")
        _append_journal(
            self.journal_path,
            {
                "phase": "completed",
                "action_id": str(action_id),
                "entry_id": str(entry_id),
                "workspace_id": context.workspace_id,
                "original_relative_path": normalized,
                "quarantine_relative_path": quarantine_relative,
                "quarantine_absolute_path": str(destination),
                "content_sha256": digest,
                "size_bytes": size,
            },
        )
        entry = QuarantineEntryView(
            id=entry_id,
            workspace_id=context.workspace_id,
            action_id=action_id,
            original_relative_path=normalized,
            quarantine_relative_path=quarantine_relative,
            quarantine_absolute_path=str(destination),
            content_sha256=digest,
            size_bytes=size,
            status="quarantined",
        )
        return QuarantineResult("quarantined", entry, digest, size)

    def restore(self, context: WorkspaceContext, entry: QuarantineEntryView) -> RestoreResult:
        if entry.status == "restored":
            return RestoreResult("restored", entry.id, entry.content_sha256, entry.size_bytes)
        source = Path(entry.quarantine_absolute_path)
        try:
            destination = _validate_missing_destination(context, entry.original_relative_path)
        except FileActionError as error:
            if error.code == "destination_conflict":
                return RestoreResult(
                    "destination_conflict", entry.id, entry.content_sha256, entry.size_bytes
                )
            raise
        if not source.exists() or source.is_symlink():
            raise FileActionError("quarantine_file_not_found", "隔离文件不存在")
        metadata = os.lstat(source)
        if not stat.S_ISREG(metadata.st_mode) or getattr(
            metadata, "st_file_attributes", 0
        ) & 0x0400:
            raise FileActionError("quarantine_file_invalid", "隔离文件不是安全普通文件")
        digest, size = _sha256(source)
        if digest != entry.content_sha256 or size != entry.size_bytes:
            raise FileActionError("quarantine_digest_mismatch", "隔离文件摘要不匹配")
        _append_journal(
            self.journal_path,
            {
                "phase": "restore_prepared",
                "action_id": str(entry.action_id),
                "entry_id": str(entry.id),
            },
        )
        _move_without_replace(source, destination)
        _append_journal(
            self.journal_path,
            {
                "phase": "restore_completed",
                "action_id": str(entry.action_id),
                "entry_id": str(entry.id),
            },
        )
        return RestoreResult("restored", entry.id, digest, size)


def recover_incomplete_journal(journal_path: Path) -> list[RecoveryNotice]:
    records = _read_journal(journal_path)
    completed = {
        str(record.get("action_id"))
        for record in records
        if record.get("phase") in {"completed", "restore_completed"}
    }
    prepared = {
        str(record.get("action_id"))
        for record in records
        if record.get("phase") in {"prepared", "restore_prepared"}
    }
    return [
        RecoveryNotice(action_id=action_id, decision="manual_review_required")
        for action_id in sorted(prepared - completed)
        if action_id and action_id != "None"
    ]


def _protected_match(relative_path: str, patterns: tuple[str, ...]) -> bool:
    candidate = relative_path.casefold()
    basename = candidate.rsplit("/", 1)[-1]
    for raw_pattern in patterns:
        pattern = raw_pattern.replace("\\", "/").casefold()
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if candidate == prefix or candidate.startswith(f"{prefix}/"):
                return True
        elif "/" not in pattern:
            if fnmatchcase(basename, pattern):
                return True
        elif fnmatchcase(candidate, pattern):
            return True
    return False
