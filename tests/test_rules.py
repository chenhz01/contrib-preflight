"""One test class per rule: it must fire on the bad case and stay quiet on the good one."""

from __future__ import annotations

from pathlib import Path

from conftest import write

from cpreflight.rules import RULES_BY_ID
from cpreflight.scanner import scan_path

SHA = "a" * 40


def run_rule(repo: Path, rule_id: str, include_git: bool = True):
    return scan_path(repo, include_git=include_git, rules=[RULES_BY_ID[rule_id]])


# --------------------------------------------------------------------------- #


def test_actions_unpinned_ref_fires(repo: Path):
    write(
        repo,
        ".github/workflows/ci.yml",
        "jobs:\n  build:\n    steps:\n      - uses: actions/checkout@v4\n",
    )
    findings = run_rule(repo, "actions-unpinned-ref").findings
    assert [f.rule for f in findings] == ["actions-unpinned-ref"]
    assert findings[0].severity.value == "error"
    assert findings[0].line == 4
    assert "actions/checkout" in findings[0].message


def test_actions_unpinned_ref_quiet_when_sha_pinned(repo: Path):
    write(
        repo,
        ".github/workflows/ci.yml",
        f"jobs:\n  build:\n    steps:\n      - uses: actions/checkout@{SHA}  # v4\n",
    )
    assert run_rule(repo, "actions-unpinned-ref").findings == []


def test_actions_unpinned_ref_ignores_local_and_docker(repo: Path):
    write(
        repo,
        ".github/workflows/ci.yml",
        "      - uses: ./.github/actions/local\n      - uses: docker://alpine:3\n",
    )
    assert run_rule(repo, "actions-unpinned-ref").findings == []


def test_actions_unpinned_ref_ignores_workflow_outside_dir(repo: Path):
    write(repo, "ci.yml", "      - uses: actions/checkout@v4\n")
    assert run_rule(repo, "actions-unpinned-ref").findings == []


# --------------------------------------------------------------------------- #


def test_dependabot_major_only_with_groups_is_error(repo: Path):
    write(
        repo,
        ".github/dependabot.yml",
        "updates:\n"
        "  - package-ecosystem: npm\n"
        "    groups:\n"
        "      all:\n"
        "        patterns: ['*']\n"
        "    ignore:\n"
        "      - dependency-name: \"stripe\"\n"
        "        versions: [\">=20\"]\n",
    )
    findings = run_rule(repo, "dependabot-major-only-ignore").findings
    assert len(findings) == 1
    assert findings[0].severity.value == "error"
    assert "minor" in findings[0].message


def test_dependabot_major_only_without_groups_is_warn(repo: Path):
    write(
        repo,
        ".github/dependabot.yml",
        "updates:\n"
        "  - package-ecosystem: npm\n"
        "    ignore:\n"
        "      - dependency-name: \"stripe\"\n"
        "        versions: [\">=20\"]\n",
    )
    findings = run_rule(repo, "dependabot-major-only-ignore").findings
    assert [f.severity.value for f in findings] == ["warn"]


def test_dependabot_quiet_when_minor_range_also_ignored(repo: Path):
    write(
        repo,
        ".github/dependabot.yml",
        "updates:\n"
        "  - package-ecosystem: npm\n"
        "    groups:\n"
        "      all:\n"
        "        patterns: ['*']\n"
        "    ignore:\n"
        "      - dependency-name: \"stripe\"\n"
        "        versions: [\">=20\", \"21.x\"]\n",
    )
    assert run_rule(repo, "dependabot-major-only-ignore").findings == []


# --------------------------------------------------------------------------- #


def test_npm_git_drift_fires(git_repo: Path):
    write(git_repo, "package.json", '{"name": "x", "version": "1.0.0"}\n')
    findings = run_rule(git_repo, "npm-git-version-drift").findings
    assert len(findings) == 1
    assert "1.2.3" in findings[0].message


def test_npm_git_quiet_when_versions_match(git_repo: Path):
    write(git_repo, "package.json", '{"name": "x", "version": "1.2.3"}\n')
    assert run_rule(git_repo, "npm-git-version-drift").findings == []


def test_npm_git_quiet_when_v_prefix(git_repo: Path):
    write(git_repo, "package.json", '{"name": "x", "version": "v1.2.3"}\n')
    assert run_rule(git_repo, "npm-git-version-drift").findings == []


def test_git_rule_skippable(repo: Path):
    write(repo, "package.json", '{"name": "x", "version": "0.0.1"}\n')
    assert run_rule(repo, "npm-git-version-drift", include_git=False).findings == []


# --------------------------------------------------------------------------- #


def test_unbound_resource_fires(repo: Path):
    write(
        repo,
        "reader.c",
        "#include <stdio.h>\n"
        "void run(void) {\n"
        "    FILE *f = fopen(\"a.txt\", \"r\");\n"
        "    DeferFn([&]{ fclose(f); });\n"
        "    use(f);\n"
        "}\n",
    )
    findings = run_rule(repo, "unbound-resource-close").findings
    assert len(findings) == 1
    assert "f" in findings[0].message


def test_unbound_resource_quiet_when_checked(repo: Path):
    write(
        repo,
        "reader.c",
        "#include <stdio.h>\n"
        "int run(void) {\n"
        "    FILE *f = fopen(\"a.txt\", \"r\");\n"
        "    if (!f) { return -1; }\n"
        "    DeferFn([&]{ fclose(f); });\n"
        "    return 0;\n"
        "}\n",
    )
    assert run_rule(repo, "unbound-resource-close").findings == []


def test_unbound_resource_quiet_for_go_with_err_check(repo: Path):
    write(
        repo,
        "reader.go",
        "func run() error {\n"
        "\tf, err := os.Open(\"a.txt\")\n"
        "\tif err != nil { return err }\n"
        "\tdefer f.Close()\n"
        "\treturn nil\n"
        "}\n",
    )
    assert run_rule(repo, "unbound-resource-close").findings == []


# --------------------------------------------------------------------------- #


def test_transposed_identifier_fires(repo: Path):
    write(repo, "cache.cpp", "static void envict_entry() {}\n")
    findings = run_rule(repo, "transposed-identifier").findings
    assert len(findings) == 1
    assert "evict" in findings[0].fix


def test_transposed_identifier_quiet_for_correct_word(repo: Path):
    write(repo, "cache.cpp", "static void evict_entry() {}\n")
    assert run_rule(repo, "transposed-identifier").findings == []


# --------------------------------------------------------------------------- #


def test_compose_bind_missing_fires(repo: Path):
    write(
        repo,
        "docker-compose.yml",
        "services:\n  app:\n    volumes:\n      - /definitely/not/here:/data\n",
    )
    findings = run_rule(repo, "compose-bind-source-missing").findings
    assert len(findings) == 1
    assert findings[0].severity.value == "error"


def test_compose_bind_quiet_when_source_exists(repo: Path):
    (repo / "data").mkdir()
    write(
        repo,
        "docker-compose.yml",
        "services:\n  app:\n    volumes:\n      - ./data:/data\n",
    )
    assert run_rule(repo, "compose-bind-source-missing").findings == []


def test_compose_bind_skips_env_interpolation(repo: Path):
    write(
        repo,
        "compose.yaml",
        "services:\n  app:\n    volumes:\n      - ${DATA_DIR}:/data\n",
    )
    assert run_rule(repo, "compose-bind-source-missing").findings == []


# --------------------------------------------------------------------------- #


def test_artifact_unverified_fires(repo: Path):
    write(
        repo,
        ".github/workflows/release.yml",
        "jobs:\n  r:\n    steps:\n      - uses: actions/upload-artifact@v4\n",
    )
    findings = run_rule(repo, "artifact-unverified").findings
    assert len(findings) == 1
    assert findings[0].severity.value == "warn"


def test_artifact_unverified_quiet_with_hash_files(repo: Path):
    write(
        repo,
        ".github/workflows/release.yml",
        "jobs:\n  r:\n    steps:\n"
        "      - uses: actions/upload-artifact@v4\n"
        "      - run: echo $(hashFiles('out/**'))\n",
    )
    assert run_rule(repo, "artifact-unverified").findings == []


# --------------------------------------------------------------------------- #


def test_hardcoded_credential_fires(repo: Path):
    write(repo, "app.py", 'API_KEY = "sk_live_9f8a7b6c5d4e3f2a1b"\n')
    findings = run_rule(repo, "hardcoded-credential").findings
    assert len(findings) == 1
    assert findings[0].severity.value == "error"


def test_hardcoded_credential_quiet_for_env_read(repo: Path):
    write(repo, "app.py", 'API_KEY = os.environ["STRIPE_KEY"]\n')
    assert run_rule(repo, "hardcoded-credential").findings == []


def test_hardcoded_credential_quiet_for_placeholder(repo: Path):
    write(repo, "app.py", 'api_key = "your-api-key-here-placeholder"\n')
    assert run_rule(repo, "hardcoded-credential").findings == []


# --------------------------------------------------------------------------- #


def test_clean_repository_has_zero_findings(repo: Path):
    """Dogfood: a repository written the right way must scan clean."""
    write(repo, "README.md", "# demo\n")
    write(repo, "src/app.py", "import os\n\n\ndef run():\n    return os.environ.get('K', '')\n")
    write(repo, "src/util.c", "#include <stdio.h>\nint run(void) {\n    FILE *f = fopen(\"a\", \"r\");\n    if (!f) { return -1; }\n    fclose(f);\n    return 0;\n}\n")
    write(repo, "docker-compose.yml", "services:\n  app:\n    image: alpine\n")
    write(
        repo,
        ".github/workflows/ci.yml",
        f"jobs:\n  build:\n    steps:\n      - uses: actions/checkout@{SHA}  # v4\n"
        "      - run: pytest\n"
        f"      - uses: actions/upload-artifact@{SHA}  # v4\n"
        "      - run: echo $(hashFiles('out/**'))\n",
    )
    write(
        repo,
        ".github/dependabot.yml",
        "updates:\n  - package-ecosystem: npm\n    ignore:\n"
        "      - dependency-name: \"x\"\n        versions: [\">=2\", \"2.x\"]\n",
    )
    result = scan_path(repo, include_git=False)
    assert result.findings == [], [f.format() for f in result.ordered()]
    assert result.files_scanned > 0


def test_hardcoded_credential_skips_test_trees(repo: Path):
    write(repo, "pkg/__tests__/auth.test.ts", 'const apiKey = "sk_live_9f8a7b6c5d4e3f2a1b";\n')
    write(repo, "tests/conftest.py", 'PASSWORD = "hunter20000000000000"\n')
    assert run_rule(repo, "hardcoded-credential").findings == []


def test_hardcoded_credential_skips_dummy_values(repo: Path):
    write(repo, "src/client.py", 'api_key = "test-api-key-0000000000"\n')
    write(repo, "src/other.py", 'token = "fake-token-abcdefabcdef"\n')
    assert run_rule(repo, "hardcoded-credential").findings == []


def test_hardcoded_credential_still_fires_in_source(repo: Path):
    write(repo, "src/client.py", 'api_key = "sk_live_9f8a7b6c5d4e3f2a1b"\n')
    assert len(run_rule(repo, "hardcoded-credential").findings) == 1


def test_transposed_identifier_skips_vendor(repo: Path):
    write(repo, "third_party/lib/seperate.cpp", "void seperate() {}\n")
    assert run_rule(repo, "transposed-identifier").findings == []


def test_transposed_identifier_ignores_string_literals(repo: Path):
    write(repo, "denylist.py", 'TYPOS = {"envict": "evict"}\n')
    assert run_rule(repo, "transposed-identifier").findings == []


def test_actions_unpinned_dedupes_repeated_action(repo: Path):
    write(
        repo,
        ".github/workflows/ci.yml",
        "      - uses: actions/checkout@v4\n      - run: x\n      - uses: actions/checkout@v4\n",
    )
    assert len(run_rule(repo, "actions-unpinned-ref").findings) == 1
