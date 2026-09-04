from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.db import create_db_and_tables, create_db_engine
from app.services.workspaces import WorkspaceError, WorkspacePatch, WorkspaceService


@pytest.fixture
def session():
    engine = create_db_engine("sqlite://")
    create_db_and_tables(engine)
    with Session(engine) as database_session:
        yield database_session


def test_create_workspace_derives_external_quarantine_root(
    session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(tmp_path))
    root = tmp_path / "project"
    root.mkdir()

    workspace = WorkspaceService(session).create("演示工作区", str(root), None)

    assert workspace.version == 1
    assert workspace.enabled is True
    assert workspace.protected_patterns == [
        ".git/**",
        ".agentgate/**",
        ".env",
        ".env.*",
        "*.key",
        "*.pem",
        "credentials.*",
        "protected/**",
    ]
    assert workspace.quarantine_root_path.casefold().startswith(str(tmp_path.parent).casefold())
    assert not workspace.quarantine_root_path.casefold().startswith(str(root).casefold())


def test_update_workspace_increments_version_and_disable_is_persisted(
    session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "workspace_allowed_root", str(tmp_path))
    root = tmp_path / "project"
    root.mkdir()
    workspace = WorkspaceService(session).create("演示工作区", str(root), None)

    updated = WorkspaceService(session).update(
        workspace.id, WorkspacePatch(enabled=False, name="已停用工作区")
    )

    assert updated.version == 2
    assert updated.enabled is False
    assert updated.name == "已停用工作区"


def test_update_unknown_workspace_returns_stable_error(session: Session) -> None:
    with pytest.raises(WorkspaceError, match="workspace_not_found"):
        WorkspaceService(session).update(uuid4(), WorkspacePatch(enabled=False))
