import fnmatch
import ntpath
from pathlib import PureWindowsPath

DEFAULT_PROTECTED_PATTERNS = [
    ".git/**",
    ".agentgate/**",
    ".env",
    ".env.*",
    "*.key",
    "*.pem",
    "credentials.*",
    "protected/**",
]


class InvalidRelativePath(ValueError):
    """The Agent supplied a path that is not a relative file path."""


class InvalidManagedRoot(ValueError):
    """A managed root is not a local path inside the configured allow-list."""


_RESERVED_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def _is_reserved_device_name(segment: str) -> bool:
    stem = segment.split(".", 1)[0].upper()
    return stem in _RESERVED_DEVICE_NAMES


def normalize_relative_path(raw: str) -> str:
    """Return a safe slash-normalized Agent-relative path."""
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise InvalidRelativePath("path must be a non-empty UTF-8 string without NUL")

    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or ntpath.splitdrive(normalized)[0]:
        raise InvalidRelativePath("absolute, UNC, and drive paths are not allowed")

    segments = normalized.split("/")
    if any(
        not segment
        or segment in {".", ".."}
        or ":" in segment
        or segment.endswith((".", " "))
        or _is_reserved_device_name(segment)
        or len(segment) > 255
        for segment in segments
    ):
        raise InvalidRelativePath("path contains an unsafe Windows segment")
    if len(normalized) > 4000 or PureWindowsPath(normalized).is_absolute():
        raise InvalidRelativePath("path is too long or absolute")
    return normalized


def _canonical_local_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise InvalidManagedRoot("root path is required")
    normalized = ntpath.normpath(value)
    drive, _ = ntpath.splitdrive(normalized)
    if not drive or normalized.startswith(("\\\\", "\\?\\", "\\.\\")):
        raise InvalidManagedRoot("only local drive paths are allowed")
    if not ntpath.isabs(value):
        raise InvalidManagedRoot("root path must be absolute")
    # The API may run in Linux/WSL while the Worker owns the Windows filesystem.
    # Do not resolve a Windows path through the API host's filesystem.
    return normalized


def validate_managed_root(root_path: str, allowed_root: str) -> str:
    """Canonicalize a local root and require it to be inside the allow-list root."""
    root = _canonical_local_path(root_path)
    allowed = _canonical_local_path(allowed_root)
    try:
        common = ntpath.commonpath([root, allowed])
    except ValueError as error:
        raise InvalidManagedRoot("root and allowed root use different volumes") from error
    if ntpath.normcase(common) != ntpath.normcase(allowed):
        raise InvalidManagedRoot("root path is outside the allowed root")
    return root


def protected_match(relative_path: str, patterns: list[str]) -> str | None:
    """Return the first case-insensitive protected glob matching a relative path."""
    candidate = normalize_relative_path(relative_path).casefold()
    for pattern in patterns:
        normalized_pattern = normalize_relative_path(pattern.replace("**", "x")).casefold()
        if pattern.replace("\\", "/").endswith("/**"):
            prefix = pattern.replace("\\", "/").casefold()[:-3].rstrip("/")
            if candidate == prefix or candidate.startswith(f"{prefix}/"):
                return pattern
        elif "/" not in normalized_pattern:
            if fnmatch.fnmatchcase(candidate.rsplit("/", 1)[-1], normalized_pattern):
                return pattern
        elif fnmatch.fnmatchcase(candidate, normalized_pattern):
            return pattern
    return None
