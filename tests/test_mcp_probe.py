"""The MCP probe must classify the failure modes it claims to handle."""

from __future__ import annotations

import sys
import textwrap

from cpreflight.mcp_probe import probe_mcp_backend


def _script(tmp_path, name: str, body: str) -> list:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return [sys.executable, str(path)]


def test_detects_removed_subcommand(tmp_path):
    argv = _script(
        tmp_path,
        "dead.py",
        """
        import sys
        sys.stderr.write("error: unrecognized subcommand 'mcp-server'\\n")
        sys.exit(2)
        """,
    )
    result = probe_mcp_backend(argv, timeout=5)
    assert result.ready is False
    assert result.reason == "subcommand-removed"
    assert result.hint


def test_detects_tty_requirement(tmp_path):
    argv = _script(
        tmp_path,
        "tty.py",
        """
        import sys
        sys.stderr.write("stdin is not a terminal\\n")
        sys.exit(1)
        """,
    )
    assert probe_mcp_backend(argv, timeout=5).reason == "requires-tty"


def test_detects_missing_binary():
    result = probe_mcp_backend(["definitely-not-a-real-binary-xyz"], timeout=5)
    assert result.ready is False
    assert result.reason == "binary-missing"


def test_healthy_backend_is_ready(tmp_path):
    argv = _script(
        tmp_path,
        "ok.py",
        """
        import json, sys
        for line in sys.stdin:
            req = json.loads(line)
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }) + "\\n")
            sys.stdout.flush()
        """,
    )
    result = probe_mcp_backend(argv, timeout=10)
    assert result.ready is True
    assert result.reason == "initialized"
    assert result.returncode == 0


def test_silent_backend_times_out_fast(tmp_path):
    argv = _script(
        tmp_path,
        "silent.py",
        """
        import time
        time.sleep(30)
        """,
    )
    result = probe_mcp_backend(argv, timeout=1.0)
    assert result.ready is False
    assert result.reason == "handshake-timeout"
    # It must not have waited for the full 30s sleep.
    assert result.elapsed_ms < 10_000


def test_empty_argv_is_reported():
    result = probe_mcp_backend([], timeout=1)
    assert result.ready is False
    assert result.reason == "no-command"


def test_result_serialises(tmp_path):
    argv = _script(
        tmp_path,
        "x.py",
        "import sys; sys.stderr.write('boom'); sys.exit(1)",
    )
    payload = probe_mcp_backend(argv, timeout=5).as_dict()
    assert set(payload) == {
        "command",
        "ok",
        "ready",
        "reason",
        "hint",
        "returncode",
        "elapsed_ms",
    }
    assert isinstance(payload["ready"], bool)
