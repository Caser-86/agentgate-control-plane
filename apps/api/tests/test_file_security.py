from pathlib import Path

import pytest

from app.files.security import (
    DEFAULT_PROTECTED_PATTERNS,
    InvalidManagedRoot,
    InvalidRelativePath,
    normalize_relative_path,
    protected_match,
    validate_managed_root,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(r"docs\notes.txt", "docs/notes.txt"), ("a/b.txt", "a/b.txt")],
)
def test_normalize_relative_path_returns_forward_slashes(raw: str, expected: str) -> None:
    assert normalize_relative_path(raw) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "..",
        r"C:\a.txt",
        r"\\server\share\a.txt",
        "a:stream",
        "a/../b",
        "a//b",
        "a\x00b",
        "report.txt.",
        "CON.txt",
    ],
)
def test_normalize_relative_path_rejects_unsafe_input(value: str) -> None:
    with pytest.raises(InvalidRelativePath):
        normalize_relative_path(value)


def test_protected_match_is_case_insensitive_and_uses_relative_path() -> None:
    assert protected_match(".GIT/HEAD", [".git/**"]) == ".git/**"
    assert protected_match("protected/secret.txt", DEFAULT_PROTECTED_PATTERNS) == "protected/**"
    assert protected_match("notes/readme.txt", DEFAULT_PROTECTED_PATTERNS) is None


def test_validate_managed_root_requires_path_inside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    root = allowed / "project"
    root.mkdir(parents=True)

    assert validate_managed_root(str(root), str(allowed)).casefold() == str(root).casefold()


def test_validate_managed_root_rejects_sibling_path(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    sibling = tmp_path / "allowed-sibling"
    allowed.mkdir()
    sibling.mkdir()

    with pytest.raises(InvalidManagedRoot):
        validate_managed_root(str(sibling), str(allowed))
