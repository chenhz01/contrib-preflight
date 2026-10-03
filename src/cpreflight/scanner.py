"""Walk a tree, apply every rule, return a :class:`Result`."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .model import Finding, Result
from .rules import RULES, Rule
from .util import iter_source_files, read_text

#: Repo-level suppression file, same spirit as .gitignore / .eslintignore.
IGNORE_FILE = ".cpreflightignore"


def load_ignores(root: Path) -> List[Tuple[str, Optional[str]]]:
    """Parse ``.cpreflightignore`` into ``(rule_id, path_glob|None)`` pairs.

    Each line is ``rule-id`` (whole rule) or ``rule-id:glob`` (rule scoped to
    matching paths). Blank lines and ``#`` comments are ignored.
    """
    path = root / IGNORE_FILE
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: List[Tuple[str, Optional[str]]] = []
    for line in raw.splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        if ":" in entry:
            rule, _, glob = entry.partition(":")
            out.append((rule.strip(), glob.strip() or None))
        else:
            out.append((entry, None))
    return out


def is_ignored(finding: Finding, ignores: Sequence[Tuple[str, Optional[str]]]) -> bool:
    """True when *finding* is suppressed by the parsed ignore list."""
    for rule, glob in ignores:
        if rule != finding.rule:
            continue
        if glob is None or fnmatch.fnmatch(finding.path, glob):
            return True
        # Also allow a bare directory prefix, e.g. ".github/workflows".
        if glob and (finding.path == glob or finding.path.startswith(glob.rstrip("/") + "/")):
            return True
    return False


def scan_path(
    root: Path,
    include_git: bool = True,
    rules: Optional[Sequence[Rule]] = None,
    use_ignore_file: bool = True,
) -> Result:
    """Scan *root* and return every finding.

    :param include_git: when False, skip rules that shell out to git.
    :param rules: override the rule set (mostly useful for tests).
    :param use_ignore_file: honour ``.cpreflightignore`` in *root*.
    """
    root = Path(root).resolve()
    result = Result()
    if not root.exists():
        return result

    ignores = load_ignores(root) if use_ignore_file else []
    seen: set = set()
    for rule in rules if rules is not None else RULES:
        if rule.needs_git and not include_git:
            continue
        for path in iter_source_files(root, rule.suffixes):
            # NOTE: every rule must analyse the file, so `seen` is only used to
            # count distinct files -- it must never short-circuit the loop.
            text = read_text(path)
            if text is None:
                continue
            seen.add(path)
            for finding in rule.run(path, text, root):
                if not is_ignored(finding, ignores):
                    result.add(finding)

    result.files_scanned = len(seen)
    return result


def rules_covering(rule_ids: Iterable[str]):
    """Return the subset of :data:`RULES` matching *rule_ids*."""
    from .rules import RULES_BY_ID

    wanted = list(rule_ids)
    unknown = [r for r in wanted if r not in RULES_BY_ID]
    if unknown:
        raise KeyError(f"unknown rule id(s): {', '.join(unknown)}")
    return [RULES_BY_ID[r] for r in wanted]
