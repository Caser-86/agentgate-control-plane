from pathlib import Path

import pytest

from agentgate_worker.client import WorkspaceContext
from agentgate_worker.filesystem import FileActionError, FileConnector


@pytest.fixture
def context(tmp_path: Path) -> WorkspaceContext:
    root = tmp_path / "workspace"
    quarantine = tmp_path / "quarantine"
    root.mkdir()
    quarantine.mkdir()
    return WorkspaceContext(
        workspace_id="00000000-0000-0000-0000-000000000001",
        version=1,
        root_path=str(root),
        quarantine_root_path=str(quarantine),
        protected_patterns=(".env",),
    )


def test_inspect_returns_metadata_and_sha256_without_content(
    context: WorkspaceContext,
) -> None:
    path = Path(context.root_path) / "notes.txt"
    path.write_bytes(b"hello")

    result = FileConnector().inspect(context, "notes.txt")

    assert result.relative_path == "notes.txt"
    assert result.size_bytes == 5
    assert result.content_sha256 == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    assert not hasattr(result, "content")


@pytest.mark.parametrize("relative", ["../x", r"C:\x", "a:stream", "folder"])
def test_inspect_rejects_unsafe_or_non_file_target(
    context: WorkspaceContext, relative: str
) -> None:
    if relative == "folder":
        (Path(context.root_path) / relative).mkdir()
    with pytest.raises(FileActionError):
        FileConnector().inspect(context, relative)


def test_inspect_rejects_symbolic_link(context: WorkspaceContext) -> None:
    target = Path(context.root_path) / "target.txt"
    link = Path(context.root_path) / "link.txt"
    target.write_text("secret", encoding="utf-8")
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable in this Windows test environment")

    with pytest.raises(FileActionError):
        FileConnector().inspect(context, "link.txt")
