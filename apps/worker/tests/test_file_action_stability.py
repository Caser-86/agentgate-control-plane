import hashlib
from pathlib import Path
from uuid import uuid4

from agentgate_worker.client import WorkspaceContext
from agentgate_worker.quarantine import QuarantineService


def test_repeated_real_disk_quarantine_restore_cycle_is_stable(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    quarantine = tmp_path / "quarantine"
    root.mkdir()
    context = WorkspaceContext(
        workspace_id=str(uuid4()),
        version=1,
        root_path=str(root),
        quarantine_root_path=str(quarantine),
        protected_patterns=(".env", "protected/**"),
    )
    service = QuarantineService(tmp_path / "file-actions.jsonl")

    for index in range(12):
        relative_path = f"case-{index}.txt"
        original = f"stable-file-action-{index}".encode()
        file_path = root / relative_path
        file_path.write_bytes(original)
        digest = hashlib.sha256(original).hexdigest()
        action_id = uuid4()

        first = service.quarantine(context, action_id, relative_path)
        replay = service.quarantine(context, action_id, relative_path)
        assert first.status == replay.status == "quarantined"
        assert first.content_sha256 == replay.content_sha256 == digest
        assert not file_path.exists()
        assert Path(first.entry.quarantine_absolute_path).exists()

        restored = service.restore(context, first.entry)
        assert restored.status == "restored"
        assert file_path.read_bytes() == original
        assert hashlib.sha256(file_path.read_bytes()).hexdigest() == digest
