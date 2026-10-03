"""The rule set.

Every rule is a pure function ``(path, text, root) -> Iterable[Finding]`` and
carries its own ``suffixes`` so the scanner knows what to read.

Two rules (``npm-git-version-drift`` and anything needing git history) are
skippable because they shell out; the rest are pure text analysis.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Tuple

from .model import Finding, Severity
from .util import is_sha, line_of, rel

RuleFn = Callable[[Path, str, Path], Iterable[Finding]]


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    suffixes: Tuple[str, ...]
    run: RuleFn
    needs_git: bool = False


# --------------------------------------------------------------------------- #
# 1. GitHub Actions referenced by a mutable tag
# --------------------------------------------------------------------------- #

_USES = re.compile(r"^\s*(?:-\s*)?uses:\s*[\"']?([^\s\"'#]+)", re.M)


def _actions_unpinned(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if ".github/workflows" not in path.as_posix():
        return
    seen_refs = set()
    for m in _USES.finditer(text):
        ref = m.group(1)
        if ref.startswith("./") or ref.startswith("docker://") or "@" not in ref:
            continue
        name, _, version = ref.rpartition("@")
        if not name or is_sha(version):
            continue
        # One finding per distinct action per file: a repo that reuses
        # actions/checkout in twelve jobs has one unpinned ref to fix, not twelve.
        if name in seen_refs:
            continue
        seen_refs.add(name)
        yield Finding(
            rule="actions-unpinned-ref",
            severity=Severity.ERROR,
            path=rel(path, root),
            line=line_of(text, m.start()),
            message=(
                f"`{name}` is pinned to the mutable ref `@{version}`. Anyone who moves "
                f"that tag changes your CI without a commit."
            ),
            fix="Pin the 40-char commit SHA and keep the readable version as a comment: uses: name@<sha>  # v4",
        )


# --------------------------------------------------------------------------- #
# 2. Dependabot ignore rules that only block majors
# --------------------------------------------------------------------------- #

_CONSTRAINT = re.compile(r"[\"']([0-9><=~^][^\"']*)[\"']")
_MAJOR_ONLY = (
    re.compile(r"^>=?\s*\d+(?:\.0\.0)?$"),
    re.compile(r"^\d+\.\*$"),
    re.compile(r"^\d+$"),
)


def _is_major_only(constraint: str) -> bool:
    c = constraint.strip()
    return any(p.match(c) for p in _MAJOR_ONLY)


def _dependabot_major_only(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if path.name != "dependabot.yml":
        return
    has_groups = "groups:" in text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != "ignore:":
            continue
        indent = len(line) - len(line.lstrip())
        # Collect every line more indented than the `ignore:` key: the list item
        # plus its continuation keys (`versions:` sits deeper than the `-`).
        constraints: List[str] = []
        for follow in lines[i + 1 :]:
            if not follow.strip():
                continue
            cur_indent = len(follow) - len(follow.lstrip())
            if cur_indent <= indent:
                break
            constraints.extend(_CONSTRAINT.findall(follow))
        if not constraints or not all(_is_major_only(c) for c in constraints):
            continue
        severity = Severity.ERROR if has_groups else Severity.WARN
        extra = (
            " Because this file also uses `groups:`, that minor comes back inside the "
            "grouped PR and re-breaks the build you were trying to freeze."
            if has_groups
            else " If the intent was to freeze this dependency, minors still get through."
        )
        yield Finding(
            rule="dependabot-major-only-ignore",
            severity=severity,
            path=rel(path, root),
            line=i + 1,
            message=(
                f"ignore block only excludes major versions {constraints}.{extra}"
            ),
            fix="List the minor range too (e.g. add \"<next>.x\"), or drop the ignore and pin the dependency instead.",
        )


# --------------------------------------------------------------------------- #
# 3. package.json version vs the newest git tag
# --------------------------------------------------------------------------- #


def _norm_version(value: str) -> str:
    return value.strip().lstrip("vV")


def _latest_git_tag(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "tag", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        if line.strip():
            return line.strip()
    return None


def _npm_git_drift(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if path.name != "package.json":
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    version = data.get("version")
    if not isinstance(version, str):
        return
    tag = _latest_git_tag(root)
    if not tag:
        return
    if _norm_version(version) == _norm_version(tag):
        return
    yield Finding(
        rule="npm-git-version-drift",
        severity=Severity.ERROR,
        path=rel(path, root),
        line=0,
        message=(
            f"package.json declares {version} but the newest git tag is {tag}. "
            f"Publishing now ships a version that does not match the repository."
        ),
        fix="Bump package.json to the release version in the same commit that creates the tag.",
    )


# --------------------------------------------------------------------------- #
# 4. Resource acquired then closed unconditionally
# --------------------------------------------------------------------------- #

_ACQUIRE = re.compile(
    r"(?:^|[^\w.])([A-Za-z_]\w*)\s*(?::?=)\s*(?:fopen|fopen_s|os\.open|CreateFile|open)\s*\("
)
_CLOSER = re.compile(r"\b(?:fclose|Close|defer\s+\w*[Cc]lose|unique_ptr|shared_ptr)\b")
_GUARDISH = re.compile(
    r"\b(?:nil|NULL|nullptr|null|err|error|iferror|IsNil|Invalid)\b|^\s*(?:if|unless)\b|\?\s*[^:]+\s*:"
)
_WINDOW = 8


def _unbound_resource(path: Path, text: str, root: Path) -> Iterable[Finding]:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        m = _ACQUIRE.search(line)
        if not m:
            continue
        var = m.group(1)
        window = lines[idx : idx + _WINDOW]
        if not any(_CLOSER.search(w) for w in window):
            continue
        # A conditional or any error/nil token in the window means somebody
        # handled the failure path; stay quiet rather than guess.
        if any(_GUARDISH.search(w) for w in window):
            continue
        yield Finding(
            rule="unbound-resource-close",
            severity=Severity.WARN,
            path=rel(path, root),
            line=idx + 1,
            message=(
                f"`{var}` is opened and then closed (or deferred) with no visible "
                f"failure check in the next {_WINDOW} lines; if the open fails you close "
                f"an invalid handle."
            ),
            fix=f"Check `{var}` for failure immediately after the open, before registering the closer.",
        )


# --------------------------------------------------------------------------- #
# 5. Transposed / misspelled identifiers
# --------------------------------------------------------------------------- #

_TRANSPOSITIONS = {
    "envict": "evict",
    "convienient": "convenient",
    "seperate": "separate",
    "occured": "occurred",
    "recieve": "receive",
    "lenght": "length",
    "widht": "width",
    "heigth": "height",
    "sucessful": "successful",
    "paramter": "parameter",
    "funtion": "function",
    "retrun": "return",
    "existance": "existence",
    "adn": "and",
    "teh": "the",
    "taht": "that",
    "thier": "their",
}

_WORD = {token: re.compile(rf"(?<![A-Za-z]){token}(?![A-Za-z])") for token in _TRANSPOSITIONS}


def _inside_string_literal(line: str, col: int) -> bool:
    """True when character offset *col* sits inside a quoted string on *line*.

    Typos that only live inside string literals (a denylist table, a log
    message) are data, not identifiers, so we leave them alone. Handles single
    and double quotes with backslash escapes; does not attempt multi-line or
    triple-quoted strings.
    """
    in_single = in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double and i == col:
            return False
        elif (in_single or in_double) and i == col:
            return True
        i += 1
    return False


_VENDOR_PARTS = frozenset({"third_party", "thirdparty", "3rdparty", "extern", "external", "deps", "vendor"})


def _transposed_identifier(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if {p.lower() for p in path.parts} & _VENDOR_PARTS:
        return
    for token, pattern in _WORD.items():
        for m in pattern.finditer(text):
            start = m.start()
            line_no = line_of(text, start)
            line_start = text.rfind("\n", 0, start) + 1
            line_end = text.find("\n", start)
            line_text = text[line_start : line_end if line_end != -1 else len(text)]
            col = start - line_start
            if _inside_string_literal(line_text, col):
                continue
            yield Finding(
                rule="transposed-identifier",
                severity=Severity.WARN,
                path=rel(path, root),
                line=line_no,
                message=f"`{token}` looks like a transposition of `{_TRANSPOSITIONS[token]}`.",
                fix=f"Rename to `{_TRANSPOSITIONS[token]}` so grep and reviewers stop missing it.",
            )


# --------------------------------------------------------------------------- #
# 6. Compose bind mounts pointing at paths that do not exist
# --------------------------------------------------------------------------- #

_COMPOSE_NAME = re.compile(r"(^|/)(docker-)?compose(\.[\w-]+)?\.ya?ml$")
_VOLUME = re.compile(
    r"""^\s*-\s*["']?(?P<src>/[^:"'\s]+|\.{1,2}/[^:"'\s]+):[^:"'\s]*["']?\s*$""",
    re.M,
)


def _compose_bind_missing(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if not _COMPOSE_NAME.search(path.as_posix()):
        return
    for m in _VOLUME.finditer(text):
        src = m.group("src")
        if "${" in src:
            continue
        candidate = Path(src)
        if not candidate.is_absolute():
            candidate = path.parent / src
        if candidate.exists():
            continue
        yield Finding(
            rule="compose-bind-source-missing",
            severity=Severity.ERROR,
            path=rel(path, root),
            line=line_of(text, m.start()),
            message=f"bind mount source `{src}` does not exist; `compose up` fails while creating the container.",
            fix=f"Create {src} or drop the bind mount.",
        )


# --------------------------------------------------------------------------- #
# 7. Artifacts uploaded but never verified
# --------------------------------------------------------------------------- #


#: Any of these in the workflow counts as "the artifact was actually checked".
#: All lowercase, because the haystack is lowercased before comparison.
#: Deliberately generous: a false accusation here is worse than a miss.
_VERIFIED_SIGNALS = (
    "hashfiles(",
    "exit 0",
    "sha256sum",
    "checksum",
    "-eq ",
    "[[ ",
    "assert",
    "verify",
)


def _artifact_unverified(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if ".github/workflows" not in path.as_posix():
        return
    if "actions/upload-artifact" not in text:
        return
    lowered = text.lower()
    if any(signal in lowered for signal in _VERIFIED_SIGNALS):
        return
    yield Finding(
        rule="artifact-unverified",
        severity=Severity.WARN,
        path=rel(path, root),
        line=line_of(text, text.find("actions/upload-artifact")),
        message=(
            "This workflow uploads an artifact but never checks it (no hashFiles(...) "
            "and no exit-code assertion), so a truncated or stale artifact passes CI."
        ),
        fix="Assert the artifact right after upload, e.g. test \"$(find . -name '*.tar.gz' | wc -l)\" -eq 1.",
    )


# --------------------------------------------------------------------------- #
# 8. Credential-looking literals in source
# --------------------------------------------------------------------------- #

_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret)"
    r"\s*[:=]\s*[\"']([A-Za-z0-9_\-]{16,})[\"']"
)
_PLACEHOLDER = re.compile(
    r"(?i)(example|dummy|placeholder|your|changeme|redacted|xxxx|<|\$\{|os\.environ|getenv|process\.env)"
)
_SOURCE_SUFFIXES = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".kt", ".rs", ".sh", ".env",
)

# Test trees and fixtures hold deliberately fake credentials; flagging them is
# noise that trains people to ignore the rule.
_TEST_PATH_PARTS = frozenset(
    {"test", "tests", "__tests__", "testdata", "test_data", "fixtures", "fixture", "spec", "specs", "e2e", "mocks", "__mocks__"}
)
_DUMMY_WORDS = re.compile(
    r"(?i)(test|fake|mock|dummy|example|placeholder|your|changeme|redacted|xxx+|foo|bar|baz|abc123|1234|0000|lorem|asdf|qwerty)"
)


def _looks_like_test_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & _TEST_PATH_PARTS:
        return True
    name = path.name.lower()
    return (
        name.startswith("test_")
        or ".test." in name
        or ".spec." in name
        or name.endswith("_test.go")
    )


def _hardcoded_credential(path: Path, text: str, root: Path) -> Iterable[Finding]:
    if path.suffix.lower() not in _SOURCE_SUFFIXES and path.name != ".env":
        return
    if _looks_like_test_path(path):
        return
    for m in _SECRET.finditer(text):
        value = m.group(2)
        if _PLACEHOLDER.search(value) or _DUMMY_WORDS.search(value) or _PLACEHOLDER.search(m.group(0)):
            continue
        yield Finding(
            rule="hardcoded-credential",
            severity=Severity.ERROR,
            path=rel(path, root),
            line=line_of(text, m.start()),
            message=f"`{m.group(1)}` is assigned a literal credential inline.",
            fix="Read it from the environment or a secret store, and rotate the exposed value.",
        )


# --------------------------------------------------------------------------- #

RULES: Tuple[Rule, ...] = (
    Rule("actions-unpinned-ref", "GitHub Actions must be pinned to a commit SHA", (".yml", ".yaml"), _actions_unpinned),
    Rule("dependabot-major-only-ignore", "Dependabot ignores that only block majors", (".yml", ".yaml"), _dependabot_major_only),
    Rule("npm-git-version-drift", "package.json version vs newest git tag", (".json",), _npm_git_drift, needs_git=True),
    Rule("unbound-resource-close", "Resource opened then closed with no failure check", (".c", ".h", ".cc", ".cpp", ".hpp", ".go"), _unbound_resource),
    Rule("transposed-identifier", "Transposed or misspelled identifiers", (".c", ".h", ".cc", ".cpp", ".hpp", ".go", ".py", ".rs", ".ts", ".js"), _transposed_identifier),
    Rule("compose-bind-source-missing", "Compose bind mount source does not exist", (".yml", ".yaml"), _compose_bind_missing),
    Rule("artifact-unverified", "Artifact uploaded but never verified", (".yml", ".yaml"), _artifact_unverified),
    Rule("hardcoded-credential", "Credential-looking literal in source", _SOURCE_SUFFIXES, _hardcoded_credential),
)

RULES_BY_ID = {rule.id: rule for rule in RULES}
