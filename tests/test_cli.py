"""CLI surface: exit codes, --format json, --list-rules, rule selection."""

from __future__ import annotations

import json

from conftest import write

from cpreflight.cli import main

SHA = "a" * 40


def test_list_rules(capsys):
    assert main(["scan", "--list-rules"]) == 0
    out = capsys.readouterr().out
    assert "actions-unpinned-ref" in out
    assert "npm-git-version-drift" in out


def test_clean_tree_exits_zero(repo, capsys):
    write(repo, "README.md", "# ok\n")
    assert main(["scan", str(repo), "--no-git"]) == 0
    assert "0 error(s)" in capsys.readouterr().out


def test_error_exits_one(repo, capsys):
    write(repo, ".github/workflows/ci.yml", "steps:\n  - uses: actions/checkout@v4\n")
    assert main(["scan", str(repo), "--no-git"]) == 1


def test_warn_only_passes_by_default(repo, capsys):
    write(repo, "a.c", "void x(void) {\n    FILE *f = fopen(\"a\", \"r\");\n"
                       "    DeferFn([&]{ fclose(f); });\n    use(f);\n}\n")
    assert main(["scan", str(repo), "--no-git"]) == 0
    assert main(["scan", str(repo), "--no-git", "--fail-on", "warn"]) == 1


def test_fail_on_never_always_zero(repo):
    write(repo, ".github/workflows/ci.yml", "steps:\n  - uses: actions/checkout@v4\n")
    assert main(["scan", str(repo), "--no-git", "--fail-on", "never"]) == 0


def test_json_output(repo, capsys):
    write(repo, ".github/workflows/ci.yml", "steps:\n  - uses: actions/checkout@v4\n")
    main(["scan", str(repo), "--no-git", "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_count"] == 1
    assert payload["findings"][0]["rule"] == "actions-unpinned-ref"
    assert payload["findings"][0]["severity"] == "error"


def test_rule_selection(repo, capsys):
    write(repo, ".github/workflows/ci.yml", "steps:\n  - uses: actions/checkout@v4\n")
    write(repo, "app.py", 'API_KEY = "sk_live_9f8a7b6c5d4e3f2a1b"\n')
    assert main(["scan", str(repo), "--no-git", "--rule", "hardcoded-credential"]) == 1
    out = capsys.readouterr().out
    assert "hardcoded-credential" in out
    assert "actions-unpinned-ref" not in out


def test_unknown_rule_is_usage_error(repo, capsys):
    assert main(["scan", str(repo), "--rule", "nope"]) == 2
    assert "unknown rule" in capsys.readouterr().err


def test_mcp_probe_without_argv_is_usage_error(capsys):
    assert main(["mcp-probe"]) == 2


def test_mcp_probe_text_output(capsys):
    code = main(["mcp-probe", "--", "definitely-not-a-real-binary-xyz"])
    assert code == 1
    assert "NOT ready" in capsys.readouterr().out


def test_missing_path_is_usage_error_not_silent_pass(tmp_path, capsys):
    """A linter that 'passes' on a bad path is worse than no linter."""
    code = main(["scan", str(tmp_path / "nope"), "--no-git"])
    assert code == 2
    assert "no such path" in capsys.readouterr().err


def test_file_instead_of_dir_is_usage_error(repo, capsys):
    target = write(repo, "a.py", "x = 1\n")
    assert main(["scan", str(target), "--no-git"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_empty_dir_warns_on_stderr(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["scan", str(empty), "--no-git"]) == 0
    assert "nothing was checked" in capsys.readouterr().err
