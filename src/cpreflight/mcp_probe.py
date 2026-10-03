"""Fail-fast liveness probe for stdio MCP backends.

A stdio MCP server that cannot start is expensive: hosts commonly publish their
tool list only after *every* backend finishes handshaking, so one dead backend
costs a full handshake timeout on each boot and the tools it would have provided
simply never appear.

This probe spawns the backend the same way a host would, sends an ``initialize``
request, and classifies the failure instead of waiting it out.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

#: (needle, verdict, hint) — checked in order against combined stdout+stderr.
SIGNATURES = (
    (
        "unrecognized subcommand",
        "subcommand-removed",
        "The installed CLI no longer exposes this subcommand. Check the server's "
        "current --help and update the argv, or upgrade/downgrade the CLI.",
    ),
    (
        "stdin is not a terminal",
        "requires-tty",
        "The server refuses to run in piped stdio mode. It is being invoked "
        "interactively; spawn it with pipes instead of a TTY.",
    ),
    (
        "command not found",
        "binary-missing",
        "The executable is not on PATH. Install it or use an absolute path.",
    ),
    (
        "No such file or directory",
        "binary-missing",
        "The executable or interpreter does not exist at that path.",
    ),
    (
        "EADDRINUSE",
        "port-in-use",
        "The server binds a port that is already taken. Stop the other process "
        "or configure a different port.",
    ),
    (
        "ECONNREFUSED",
        "upstream-refused",
        "An upstream the server depends on refused the connection.",
    ),
    (
        "Address already in use",
        "port-in-use",
        "The server binds a port that is already taken.",
    ),
    (
        "Traceback (most recent call last)",
        "crashed",
        "The server crashed during startup. Read the traceback above for the cause.",
    ),
)

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "cpreflight", "version": "0.1.0"},
    },
}


@dataclass
class ProbeResult:
    """Verdict for one backend."""

    command: List[str]
    ok: bool
    ready: bool
    reason: str
    hint: str = ""
    returncode: Optional[int] = None
    elapsed_ms: int = 0
    output: str = field(default="", repr=False)

    def as_dict(self) -> dict:
        return {
            "command": self.command,
            "ok": self.ok,
            "ready": self.ready,
            "reason": self.reason,
            "hint": self.hint,
            "returncode": self.returncode,
            "elapsed_ms": self.elapsed_ms,
        }


def _classify(output: str) -> Optional[tuple]:
    lowered = output.lower()
    for needle, verdict, hint in SIGNATURES:
        if needle.lower() in lowered:
            return verdict, hint
    return None


def probe_mcp_backend(
    command: Sequence[str],
    timeout: float = 5.0,
    payload: Optional[dict] = None,
) -> ProbeResult:
    """Spawn *command* as a stdio MCP server and classify how it starts.

    Returns as soon as a known failure signature appears, so a dead backend is
    reported in milliseconds rather than after the full handshake timeout.
    """
    argv = list(command)
    if not argv:
        return ProbeResult(argv, ok=False, ready=False, reason="no-command", hint="pass the server argv")

    request = json.dumps(payload or INITIALIZE) + "\n"
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return ProbeResult(argv, ok=False, ready=False, reason="binary-missing",
                           hint="The executable is not on PATH. Install it or use an absolute path.")
    except OSError as exc:
        return ProbeResult(argv, ok=False, ready=False, reason="spawn-failed", hint=str(exc))

    import time

    started = time.perf_counter()
    try:
        out, err = proc.communicate(input=request, timeout=timeout)
        elapsed = int((time.perf_counter() - started) * 1000)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            out, err = proc.communicate(timeout=2)
        except Exception:  # pragma: no cover - best effort cleanup
            out, err = "", ""
        elapsed = int((time.perf_counter() - started) * 1000)
        combined = (out or "") + (err or "")
        verdict = _classify(combined)
        reason, hint = verdict if verdict else ("handshake-timeout", "No initialize response within the timeout.")
        return ProbeResult(argv, ok=False, ready=False, reason=reason, hint=hint,
                           returncode=proc.returncode, elapsed_ms=elapsed, output=combined[-2000:])

    combined = (out or "") + (err or "")
    elapsed = int((time.perf_counter() - started) * 1000)

    verdict = _classify(combined)
    if verdict:
        reason, hint = verdict
        return ProbeResult(argv, ok=False, ready=False, reason=reason, hint=hint,
                           returncode=proc.returncode, elapsed_ms=elapsed, output=combined[-2000:])

    # No known signature: if it answered with JSON-RPC it is alive.
    if proc.returncode == 0 and '"jsonrpc"' in combined:
        return ProbeResult(argv, ok=True, ready=True, reason="initialized",
                           returncode=0, elapsed_ms=elapsed, output=combined[-2000:])

    return ProbeResult(
        argv,
        ok=False,
        ready=False,
        reason="no-response",
        hint="The process exited without a JSON-RPC response. Check that the argv starts the server in stdio mode.",
        returncode=proc.returncode,
        elapsed_ms=elapsed,
        output=combined[-2000:],
    )
