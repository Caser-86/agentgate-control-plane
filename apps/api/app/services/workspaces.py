import ntpath
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.config import get_settings
from app.files.models import ManagedWorkspace, QuarantineEntry
from app.files.security import (
    DEFAULT_PROTECTED_PATTERNS,
    InvalidManagedRoot,
    InvalidRelativePath,
    normalize_relative_path,
    validate_managed_root,
)


@dataclass(frozen=True)
class WorkspacePatch:
    name: str | None = None
    root_path: str | None = None
    protected_patterns: list[str] | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class WorkspaceContext:
    id: UUID
    version: int
    root_path: str
    quarantine_root_path: str
    protected_patterns: tuple[str, ...]


class WorkspaceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.status_code = status_code


def _validate_name(name: str) -> str:
    value = name.strip()
    if not value or any(ord(character) < 32 for character in value):
        raise WorkspaceError("invalid_workspace_name", "工作区名称不能为空或包含控制字符")
    return value


def _validate_patterns(patterns: list[str] | None) -> list[str]:
    values = list(DEFAULT_PROTECTED_PATTERNS if patterns is None else patterns)
    if len(values) > 64:
        raise WorkspaceError("too_many_protected_patterns", "保护规则不能超过 64 条")
    normalized: list[str] = []
    for pattern in values:
        if not isinstance(pattern, str) or not pattern or len(pattern) > 256:
            raise WorkspaceError("invalid_protected_pattern", "保护规则格式不合法")
        candidate = pattern.replace("\\", "/").replace("**", "x")
        try:
            normalize_relative_path(candidate)
        except InvalidRelativePath as error:
            raise WorkspaceError("invalid_protected_pattern", "保护规则格式不合法") from error
        normalized.append(pattern.replace("\\", "/"))
    return normalized


class WorkspaceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _quarantine_root(workspace_id: UUID, allowed_root: str, root_path: str) -> str:
        if ntpath.normcase(root_path) == ntpath.normcase(allowed_root):
            raise WorkspaceError(
                "workspace_root_too_broad",
                "工作区不能直接等于允许根目录",
            )
        allowed_parent = ntpath.dirname(allowed_root.rstrip("\\/")) or allowed_root
        quarantine_root = ntpath.join(allowed_parent, ".agentgate-quarantine", str(workspace_id))
        if (
            ntpath.splitdrive(quarantine_root)[0].casefold()
            != ntpath.splitdrive(root_path)[0].casefold()
        ):
            raise WorkspaceError("quarantine_volume_mismatch", "隔离区必须与工作区位于同一卷")
        if ntpath.commonpath([quarantine_root, root_path]).casefold() == root_path.casefold():
            raise WorkspaceError("quarantine_root_inside_workspace", "隔离区不能位于工作区内部")
        return quarantine_root

    def create(
        self, name: str, root_path: str, protected_patterns: list[str] | None
    ) -> ManagedWorkspace:
        settings = get_settings()
        try:
            canonical_root = validate_managed_root(root_path, settings.workspace_allowed_root)
        except InvalidManagedRoot as error:
            raise WorkspaceError(
                "workspace_root_not_allowed", "工作区必须位于允许根目录内"
            ) from error
        workspace_id = uuid4()
        workspace = ManagedWorkspace(
            id=workspace_id,
            name=_validate_name(name),
            root_path=root_path,
            canonical_root_path=canonical_root,
            quarantine_root_path=self._quarantine_root(
                workspace_id, settings.workspace_allowed_root, canonical_root
            ),
            protected_patterns=_validate_patterns(protected_patterns),
            enabled=True,
            version=1,
        )
        self.session.add(workspace)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def update(self, workspace_id: UUID, patch: WorkspacePatch) -> ManagedWorkspace:
        workspace = self.session.get(ManagedWorkspace, workspace_id)
        if workspace is None:
            raise WorkspaceError("workspace_not_found", "工作区不存在", 404)
        changes = {key: value for key, value in vars(patch).items() if value is not None}
        if not changes:
            raise WorkspaceError("empty_workspace_update", "没有可更新的工作区字段")
        if "root_path" in changes:
            active_entries = self.session.exec(
                select(QuarantineEntry).where(
                    QuarantineEntry.workspace_id == workspace_id,
                    cast(Any, QuarantineEntry.status).in_(["quarantined", "failed"]),
                )
            ).first()
            if active_entries is not None:
                raise WorkspaceError(
                    "workspace_has_pending_entries", "存在未完成隔离记录，不能修改根目录"
                )
            try:
                canonical_root = validate_managed_root(
                    str(changes["root_path"]), get_settings().workspace_allowed_root
                )
            except InvalidManagedRoot as error:
                raise WorkspaceError(
                    "workspace_root_not_allowed", "工作区必须位于允许根目录内"
                ) from error
            workspace.canonical_root_path = canonical_root
            workspace.root_path = str(changes["root_path"])
            workspace.quarantine_root_path = self._quarantine_root(
                workspace_id, get_settings().workspace_allowed_root, canonical_root
            )
        if "name" in changes:
            workspace.name = _validate_name(str(changes["name"]))
        if "protected_patterns" in changes:
            workspace.protected_patterns = _validate_patterns(changes["protected_patterns"])
        if "enabled" in changes:
            workspace.enabled = bool(changes["enabled"])
        workspace.version += 1
        workspace.updated_at = datetime.now(UTC)
        self.session.add(workspace)
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def set_enabled(self, workspace_id: UUID, enabled: bool) -> ManagedWorkspace:
        return self.update(workspace_id, WorkspacePatch(enabled=enabled))

    def get_context(self, workspace_id: UUID, version: int) -> WorkspaceContext:
        workspace = self.session.get(ManagedWorkspace, workspace_id)
        if workspace is None:
            raise WorkspaceError("workspace_not_found", "工作区不存在", 404)
        if workspace.version != version:
            raise WorkspaceError("workspace_version_conflict", "工作区版本已变化", 409)
        if not workspace.enabled:
            raise WorkspaceError("workspace_disabled", "工作区已停用", 409)
        return WorkspaceContext(
            id=workspace.id,
            version=workspace.version,
            root_path=workspace.canonical_root_path,
            quarantine_root_path=workspace.quarantine_root_path,
            protected_patterns=tuple(workspace.protected_patterns),
        )

    def list_all(self) -> list[ManagedWorkspace]:
        return list(
            self.session.exec(
                select(ManagedWorkspace).order_by(cast(Any, ManagedWorkspace.created_at))
            )
        )

    def list_quarantine_entries(
        self, workspace_id: UUID, status: str | None = None
    ) -> list[QuarantineEntry]:
        statement = select(QuarantineEntry).where(QuarantineEntry.workspace_id == workspace_id)
        if status is not None:
            statement = statement.where(QuarantineEntry.status == status)
        return list(
            self.session.exec(statement.order_by(cast(Any, QuarantineEntry.created_at).desc()))
        )
