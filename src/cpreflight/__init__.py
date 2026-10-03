"""contrib-preflight: integrity preflight for repositories and MCP backends.

Public API is intentionally small::

    from cpreflight import scan_path, probe_mcp_backend

Both return plain dataclasses so they can be embedded in CI or other tools.
"""

from .model import Finding, Result, Severity
from .scanner import scan_path
from .mcp_probe import ProbeResult, probe_mcp_backend

__all__ = [
    "Finding",
    "Result",
    "Severity",
    "scan_path",
    "ProbeResult",
    "probe_mcp_backend",
    "__version__",
]

__version__ = "0.1.0"
