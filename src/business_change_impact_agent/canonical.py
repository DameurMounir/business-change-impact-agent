"""Canonical JSON and SHA-256 helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a JSON-compatible value with a stable byte representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def pretty_json(value: Any) -> str:
    """Return deterministic human-readable JSON."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def sha256_bytes(data: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
