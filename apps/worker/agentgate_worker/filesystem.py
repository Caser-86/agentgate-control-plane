import hashlib
import ntpath
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agentgate_worker.client import WorkspaceContext

REPARSE_POINT = 0x0400


class FileActionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FileMetadata:
    relative_path: str
    size_bytes: int
    content_sha256: str
    modified_at_ns: int


def _normalize_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise FileActionError("invalid_relative_path", "文件路径不能为空或包含 NUL")
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or ntpath.splitdrive(normalized)[0]:
        raise FileActionError("invalid_relative_path", "不允许绝对路径或 UNC 路径")
    segments = normalized.split("/")
    if any(
        not segment
        or segment in {".", ".."}
        or ":" in segment
        or segment.endswith((".", " "))
        for segment in segments
    ):
        raise FileActionError("invalid_relative_path", "文件路径包含不安全片段")
    if len(normalized) > 4000 or any(len(segment) > 255 for segment in segments):
        raise FileActionError("invalid_relative_path", "文件路径过长")
    return normalized


def _is_reparse(path: Path, metadata: os.stat_result | None = None) -> bool:
    if path.is_symlink():
        return True
    value = metadata or os.lstat(path)
    return bool(getattr(value, "st_file_attributes", 0) & REPARSE_POINT)


def _final_handle_path(path: Path) -> str:
    try:
        import win32con  # type: ignore[import-untyped]
        import win32file  # type: ignore[import-untyped]

        handle = win32file.CreateFile(
            str(path),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        try:
            final_path = win32file.GetFinalPathNameByHandle(handle, 0)
        finally:
            win32file.CloseHandle(handle)
        return str(final_path).removeprefix("\\\\?\\")
    except (ImportError, OSError):
        return os.path.realpath(path)


class FileConnector:
    def _safe_file(self, context: WorkspaceContext, relative_path: str) -> tuple[str, Path]:
        normalized = _normalize_relative_path(relative_path)
        root = Path(context.root_path)
        try:
            root_metadata = os.lstat(root)
        except FileNotFoundError as error:
            raise FileActionError("workspace_root_not_found", "工作区根目录不存在") from error
        if _is_reparse(root, root_metadata) or not stat.S_ISDIR(root_metadata.st_mode):
            raise FileActionError("workspace_root_invalid", "工作区根目录不是安全目录")

        candidate = root.joinpath(*normalized.split("/"))
        current = root
        segments = normalized.split("/")
        for index, segment in enumerate(segments):
            current = current / segment
            try:
                metadata = os.lstat(current)
            except FileNotFoundError as error:
                raise FileActionError("file_not_found", "目标文件不存在") from error
            if _is_reparse(current, metadata):
                raise FileActionError("reparse_point_denied", "符号链接或 reparse point 已拒绝")
            if index < len(segments) - 1 and not stat.S_ISDIR(metadata.st_mode):
                raise FileActionError("parent_not_directory", "文件路径的父级不是目录")

        try:
            if ntpath.commonpath(
                [ntpath.normcase(str(candidate)), ntpath.normcase(str(root))]
            ) != ntpath.normcase(str(root)):
                raise FileActionError("path_escape", "目标路径越过工作区边界")
        except ValueError as error:
            raise FileActionError("path_escape", "目标路径使用了不同卷") from error
        final_path = _final_handle_path(candidate)
        try:
            if ntpath.commonpath(
                [ntpath.normcase(final_path), ntpath.normcase(str(root))]
            ) != ntpath.normcase(str(root)):
                raise FileActionError("path_escape", "最终文件句柄越过工作区边界")
        except ValueError as error:
            raise FileActionError("path_escape", "最终文件使用了不同卷") from error
        metadata = os.lstat(candidate)
        if _is_reparse(candidate, metadata) or not stat.S_ISREG(metadata.st_mode):
            raise FileActionError("regular_file_required", "只允许操作普通文件")
        return normalized, candidate

    def inspect(self, context: WorkspaceContext, relative_path: str) -> FileMetadata:
        normalized, path = self._safe_file(context, relative_path)
        metadata = os.stat(path)
        digest = hashlib.sha256()
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise FileActionError("file_read_failed", "文件读取失败") from error
        return FileMetadata(
            relative_path=normalized,
            size_bytes=metadata.st_size,
            content_sha256=digest.hexdigest(),
            modified_at_ns=metadata.st_mtime_ns,
        )
