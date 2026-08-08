"""Safe local path helpers."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from .errors import SecurityBoundaryError

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def validate_identifier(value: str, *, label: str = "identifier") -> str:
    """Validate an identifier used as a local path segment."""

    if not _SAFE_ID.fullmatch(value):
        raise SecurityBoundaryError(f"unsafe {label}: {value!r}")
    return value


def ensure_safe_child(root: Path, candidate: Path, *, must_exist: bool = False) -> Path:
    """Return a resolved child path while rejecting traversal and symlinks."""

    root_resolved = root.resolve(strict=True)
    if candidate.is_absolute():
        resolved = candidate.resolve(strict=must_exist)
    else:
        resolved = (root_resolved / candidate).resolve(strict=must_exist)
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise SecurityBoundaryError(f"path escapes root: {candidate}")
    cursor = resolved
    while cursor != root_resolved:
        if cursor.exists() and cursor.is_symlink():
            raise SecurityBoundaryError(f"symlink is not allowed: {cursor}")
        cursor = cursor.parent
    return resolved


def packaged_case_dir() -> Path:
    """Return the packaged synthetic case directory."""

    location = resources.files("business_change_impact_agent").joinpath("sample_case")
    return Path(str(location))


def packaged_design_dir() -> Path:
    """Return the packaged deterministic rule directory."""

    location = resources.files("business_change_impact_agent").joinpath("rules")
    return Path(str(location))
