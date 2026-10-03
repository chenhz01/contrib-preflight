"""Command line interface.

    cpreflight scan [PATH] [options]
    cpreflight mcp-probe -- <server argv...>

Exit codes for ``scan``: 0 clean, 1 findings at or above --fail-on, 2 bad usage.
Exit codes for ``mcp-probe``: 0 the backend answered, 1 it did not, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .mcp_probe import probe_mcp_backend
from .model import Result, Severity
from .rules import RULES
from .scanner import scan_path

_FAIL_ON = {"error": Severity.ERROR, "warn": Severity.WARN, "never": None}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpreflight",
        description="Integrity preflight for repositories and MCP backends.",
    )
    parser.add_argument("--version", action="version", version=f"cpreflight {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser(
        "scan",
        help="run repository integrity checks",
        description="Run repository integrity checks over PATH (default: current directory).",
    )
    scan.add_argument("path", nargs="?", default=".", help="directory to scan (default: .)")
    scan.add_argument(
        "--fail-on",
        choices=sorted(_FAIL_ON),
        default="error",
        help="lowest severity that makes the run fail (default: error)",
    )
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.add_argument(
        "--no-git",
        action="store_true",
        help="skip rules that shell out to git (faster, one less dependency)",
    )
    scan.add_argument(
        "--rule",
        action="append",
        default=None,
        metavar="RULE_ID",
        help="only run this rule (repeatable)",
    )
    scan.add_argument("--list-rules", action="store_true", help="print rule ids and exit")

    probe = sub.add_parser(
        "mcp-probe",
        help="classify how a stdio MCP backend starts",
        description="Spawn a stdio MCP backend, send initialize, and classify the failure fast.",
    )
    probe.add_argument("--timeout", type=float, default=5.0, help="seconds to wait (default: 5)")
    probe.add_argument("--format", choices=("text", "json"), default="text")
    probe.add_argument("server", nargs=argparse.REMAINDER, help="-- <server argv...>")

    return parser


def _print_rules() -> None:
    width = max(len(r.id) for r in RULES)
    for rule in RULES:
        title = rule.title + ("  [needs git]" if rule.needs_git else "")
        print(f"{rule.id.ljust(width)}  {title}")


def _render_text(result: Result) -> None:
    for finding in result.ordered():
        print(finding.format())
    print()
    print(
        f"scanned {result.files_scanned} file(s): "
        f"{result.errors} error(s), {result.warnings} warning(s)"
    )


def _cmd_scan(args: argparse.Namespace) -> int:
    if args.list_rules:
        _print_rules()
        return 0

    target = Path(args.path)
    if not target.exists():
        print(f"error: {args.path}: no such path", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"error: {args.path}: not a directory", file=sys.stderr)
        return 2

    rules = None
    if args.rule:
        from .scanner import rules_covering

        try:
            rules = rules_covering(args.rule)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    result = scan_path(target, include_git=not args.no_git, rules=rules)

    if result.files_scanned == 0:
        print(
            f"warning: no scannable files found under {args.path}; "
            f"a clean result here means nothing was checked",
            file=sys.stderr,
        )

    if args.format == "json":
        print(json.dumps(result.as_dict(), indent=2))
    else:
        _render_text(result)

    threshold = _FAIL_ON[args.fail_on]
    if threshold is not None and any(f.severity is threshold for f in result.findings):
        return 1
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    argv = args.server
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("error: pass the server argv after --", file=sys.stderr)
        return 2

    result = probe_mcp_backend(argv, timeout=args.timeout)

    if args.format == "json":
        print(json.dumps(result.as_dict(), indent=2))
    else:
        status = "ready" if result.ready else "NOT ready"
        print(f"{status}  ({result.elapsed_ms} ms)  {result.reason}")
        print(f"  argv: {' '.join(result.command)}")
        if result.hint:
            print(f"  hint: {result.hint}")
    return 0 if result.ready else 1


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return _cmd_scan(args)
    if args.command == "mcp-probe":
        return _cmd_probe(args)
    parser.print_help()  # pragma: no cover - argparse enforces a subcommand
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
