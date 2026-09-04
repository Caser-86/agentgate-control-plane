from pathlib import Path

import pytest

import agentgate_worker.filesystem as filesystem_module
from agentgate_worker.client import WorkspaceContext
from agentgate_worker.filesystem import FileActionError, FileConnector


def test_parent_reparse_point_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    junction = root / "linked"
    try:
        junction.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory links are unavailable in this Windows test environment")
    context = WorkspaceContext(
        workspace_id="00000000-0000-0000-0000-000000000001",
        version=1,
        root_path=str(root),
        quarantine_root_path=str(tmp_path / "quarantine"),
        protected_patterns=(),
    )
    Path(context.quarantine_root_path).mkdir()

    with pytest.raises(FileActionError):
        FileConnector().inspect(context, "linked/secret.txt")


def test_logical_workspace_root_uses_its_final_handle_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "demo.txt").write_text("stable", encoding="utf-8")
    context = WorkspaceContext(
        workspace_id="00000000-0000-0000-0000-000000000002",
        version=1,
        root_path=str(root),
        quarantine_root_path=str(tmp_path / "quarantine"),
        protected_patterns=(),
    )
    final_root = r"C:\physical\workspace"

    def redirected_final_path(path: Path) -> str:
        if path == root:
            return final_root
        return final_root + r"\demo.txt"

    monkeypatch.setattr(filesystem_module, "_final_handle_path", redirected_final_path)

    metadata = FileConnector().inspect(context, "demo.txt")

    assert metadata.relative_path == "demo.txt"
