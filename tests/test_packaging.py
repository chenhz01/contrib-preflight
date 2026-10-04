"""The ``Typing :: Typed`` classifier is a promise, not a decoration.

PEP 561 only makes an installed package's inline annotations visible to type
checkers when the package ships a ``py.typed`` marker. A classifier without
the marker claims a capability the wheel does not have, so the two are tested
against each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "cpreflight"

def test_py_typed_marker_is_shipped():
    assert (PKG / "py.typed").is_file()


def test_classifier_matches_the_marker():
    """If someone drops py.typed, the classifier must go with it."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declares_typed = "Typing :: Typed" in pyproject
    if not declares_typed:
        pytest.skip("classifier removed; update this test when re-adding it")
    assert (PKG / "py.typed").is_file()


def test_py_typed_is_not_gitignored():
    """A marker that never gets committed produces a green CI and a broken wheel."""
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        return
    for line in gitignore.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # anything that matches the marker itself would stop it reaching the tag
        if "py.typed" in stripped and stripped.lstrip("!*/") == "py.typed":
            pytest.fail(f".gitignore hides the py.typed marker: {stripped!r}")
