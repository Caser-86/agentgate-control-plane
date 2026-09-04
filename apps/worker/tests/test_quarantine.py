import os
import sys
import types
from pathlib import Path
from uuid import uuid4

import pytest

from agentgate_worker.client import WorkspaceContext
from agentgate_worker.quarantine import (
    QuarantineService,
    _move_without_replace,
    recover_incomplete_journal,
)


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
        protected_patterns=(".env", "protected/**"),
    )


def test_quarantine_then_restore_preserves_digest_and_never_overwrites(
    context: WorkspaceContext, tmp_path: Path
) -> None:
    original = Path(context.root_path) / "report.txt"
    original.write_bytes(b"stable")
    service = QuarantineService(tmp_path / "journal.jsonl")
    action_id = uuid4()

    result = service.quarantine(context, action_id, "report.txt")

    assert result.status == "quarantined"
    assert not original.exists()
    assert Path(result.entry.quarantine_absolute_path).exists()
    restored = service.restore(context, result.entry)
    assert restored.status == "restored"
    assert original.read_bytes() == b"stable"
    assert restored.content_sha256 == result.entry.content_sha256

    original.write_bytes(b"new content")
    conflict = service.restore(context, result.entry)
    assert conflict.status == "destination_conflict"
    assert original.read_bytes() == b"new content"


def test_duplicate_quarantine_action_returns_existing_result_without_second_move(
    context: WorkspaceContext, tmp_path: Path
) -> None:
    original = Path(context.root_path) / "repeat.txt"
    original.write_bytes(b"once")
    service = QuarantineService(tmp_path / "journal.jsonl")
    action_id = uuid4()

    first = service.quarantine(context, action_id, "repeat.txt")
    second = service.quarantine(context, action_id, "repeat.txt")

    assert second.entry.quarantine_absolute_path == first.entry.quarantine_absolute_path
    assert Path(second.entry.quarantine_absolute_path).read_bytes() == b"once"


def test_incomplete_journal_requires_manual_review(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        '{"action_id":"00000000-0000-0000-0000-000000000001","phase":"prepared"}\n',
        encoding="utf-8",
    )

    notices = recover_incomplete_journal(journal)

    assert len(notices) == 1
    assert notices[0].decision == "manual_review_required"


def test_windows_move_uses_flag_from_win32file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    source.write_bytes(b"stable")
    flags: list[int] = []

    def move_file_ex(source_name: str, destination_name: str, move_flags: int) -> None:
        flags.append(move_flags)
        os.rename(source_name, destination_name)

    monkeypatch.setitem(sys.modules, "win32con", types.SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "win32file",
        types.SimpleNamespace(MOVEFILE_WRITE_THROUGH=8, MoveFileEx=move_file_ex),
    )

    _move_without_replace(source, destination)

    assert flags == [8]
    assert destination.read_bytes() == b"stable"
