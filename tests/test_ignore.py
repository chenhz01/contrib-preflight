"""Suppression via .cpreflightignore — a linter nobody can silence gets deleted."""

from __future__ import annotations

from pathlib import Path

from conftest import write

from cpreflight.scanner import load_ignores, scan_path

BAD_DEPENDABOT = (
    "updates:\n"
    "  - package-ecosystem: npm\n"
    "    groups:\n"
    "      all:\n"
    "        patterns: ['*']\n"
    "    ignore:\n"
    "      - dependency-name: \"stripe\"\n"
    "        versions: [\">=20\"]\n"
)


def test_ignore_file_suppresses_whole_rule(repo: Path):
    write(repo, ".github/dependabot.yml", BAD_DEPENDABOT)
    assert scan_path(repo, include_git=False).errors == 1
    write(repo, ".cpreflightignore", "dependabot-major-only-ignore\n")
    assert scan_path(repo, include_git=False).findings == []


def test_ignore_file_scopes_to_path(repo: Path):
    write(repo, ".github/dependabot.yml", BAD_DEPENDABOT)
    write(repo, ".cpreflightignore", "dependabot-major-only-ignore:.github/dependabot.yml\n")
    assert scan_path(repo, include_git=False).findings == []


def test_ignore_file_does_not_leak_to_other_paths(repo: Path):
    write(repo, ".github/dependabot.yml", BAD_DEPENDABOT)
    write(repo, "other/dependabot.yml", BAD_DEPENDABOT)
    write(repo, ".cpreflightignore", "dependabot-major-only-ignore:.github/dependabot.yml\n")
    result = scan_path(repo, include_git=False)
    assert [f.path for f in result.findings] == ["other/dependabot.yml"]


def test_comments_and_blank_lines_are_ignored(repo: Path):
    write(repo, ".github/dependabot.yml", BAD_DEPENDABOT)
    write(
        repo,
        ".cpreflightignore",
        "# a comment\n\n   \ndependabot-major-only-ignore  # trailing comment\n",
    )
    assert scan_path(repo, include_git=False).findings == []


def test_ignore_file_can_be_disabled(repo: Path):
    write(repo, ".github/dependabot.yml", BAD_DEPENDABOT)
    write(repo, ".cpreflightignore", "dependabot-major-only-ignore\n")
    assert scan_path(repo, include_git=False, use_ignore_file=False).errors == 1


def test_load_ignores_parses_both_forms(repo: Path):
    write(repo, ".cpreflightignore", "rule-a\nrule-b:src/**\n")
    assert load_ignores(repo) == [("rule-a", None), ("rule-b", "src/**")]


def test_missing_ignore_file_is_empty(repo: Path):
    assert load_ignores(repo) == []
