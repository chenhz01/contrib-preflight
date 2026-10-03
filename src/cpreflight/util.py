"""Small filesystem / text helpers shared by rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

#: A fully-pinned GitHub Action / dependency reference is a 40-char object name.
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: Never read files larger than this into memory.
MAX_BYTES = 2_000_000

#: Directories that are never interesting and are expensive to walk.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "vendor",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)


def is_sha(ref: str) -> bool:
    """True when *ref* is a fully-pinned 40-character commit SHA."""
    return bool(SHA_RE.match(ref.strip()))


def line_of(text: str, index: int) -> int:
    """1-based line number for a character offset in *text*."""
    return text.count("\n", 0, index) + 1


def read_text(path: Path) -> Optional[str]:
    """Read *path* as UTF-8 text, or return None if that is not sensible.

    Skips oversized files and anything that looks binary, so the scanner can
    walk a whole tree without special-casing.
    """
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8000]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def iter_source_files(root: Path, suffixes: Iterable[str]) -> List[Path]:
    """Every file under *root* whose suffix is in *suffixes*, skipping noise dirs."""
    wanted = {s.lower() for s in suffixes}
    found: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in wanted:
            found.append(path)
    return sorted(found)


def rel(path: Path, root: Path) -> str:
    """POSIX-style path of *path* relative to *root* (falls back to absolute)."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
