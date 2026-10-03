"""Core data types shared by every rule and by the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List


class Severity(str, Enum):
    """How much a finding should worry you."""

    ERROR = "error"
    WARN = "warn"
    INFO = "info"


# Lower sorts first when we order findings for output.
_ORDER = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2}


@dataclass(frozen=True)
class Finding:
    """One problem, anchored to a file and (when known) a line."""

    rule: str
    severity: Severity
    path: str
    line: int
    message: str
    fix: str = ""

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "fix": self.fix,
        }

    def format(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        out = f"{self.severity.value.upper():<5} {self.rule:<28} {where}\n"
        out += f"      {self.message}"
        if self.fix:
            out += f"\n      fix: {self.fix}"
        return out


@dataclass
class Result:
    """Accumulated findings for one scan."""

    findings: List[Finding] = field(default_factory=list)
    files_scanned: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    def ordered(self) -> List[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (_ORDER[f.severity], f.path, f.line, f.rule),
        )

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is severity)

    @property
    def errors(self) -> int:
        return self.count(Severity.ERROR)

    @property
    def warnings(self) -> int:
        return self.count(Severity.WARN)

    def as_dict(self) -> dict:
        return {
            "files_scanned": self.files_scanned,
            "error_count": self.errors,
            "warning_count": self.warnings,
            "findings": [f.as_dict() for f in self.ordered()],
        }
