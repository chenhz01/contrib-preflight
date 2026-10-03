"""Shared fixtures: build throwaway repositories on disk."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def write(root: Path, rel_path: str, text: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture
def git_repo(repo: Path) -> Path:
    """A repo with one commit and one tag, for the git-backed rule."""
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(repo),
    }
    try:
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True, env=env)
        write(repo, "README.md", "x")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, capture_output=True, env=env)
        subprocess.run(["git", "tag", "v1.2.3"], cwd=repo, check=True, capture_output=True, env=env)
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pytest.skip("git unavailable in this environment")
    return repo
