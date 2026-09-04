from pathlib import Path

import pytest

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
