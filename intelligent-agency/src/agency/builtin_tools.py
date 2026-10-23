"""The first two real tools: ``read_file`` and ``run_tests``.

Both are sandboxed to a single configured repository root and both are
registered through :mod:`agency.tools`, so neither can execute without passing
``PolicyEngine.check`` in the dispatch path.

Sandbox rules (shared by both tools)
------------------------------------
* The root is explicit: ``default_registry(root=...)`` or the
  ``AGENCY_TOOL_REPO_ROOT`` environment variable. A path outside it is refused
  (:class:`~agency.tools.ToolSandboxError`), including via ``..`` and via a
  symlink that escapes the root.
* Secret-ish paths are refused, reusing the forbidden-token idea from
  ``github_client.py:79-80`` (``.env``, ``secret``, ``credential``,
  ``private_key``, ``id_rsa``) plus ``.git/`` and ``.github/workflows/``.
* Reads are capped (:data:`MAX_READ_BYTES`) and test output is truncated to its
  tail (:data:`MAX_TEST_OUTPUT_BYTES`), so a tool call cannot flood a prompt or
  a log.

Neither tool writes, merges, publishes or spends. ``run_tests`` executes the
repository's own test suite with a timeout and no shell, which is exactly what
lets the HQ check its own work; it is classified :class:`ToolRisk.WRITE_LOCAL`
because the code under test may write to the work tree (bytecode caches,
fixtures), which is local and recoverable rather than irreversible.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .policy import ToolRisk
from .tools import Tool, ToolArgumentError, ToolRegistry, ToolSandboxError

#: Environment variable naming the single repository root tools may work in.
REPO_ROOT_ENV = "AGENCY_TOOL_REPO_ROOT"

FORBIDDEN_PATH_PREFIXES = (".git/", ".github/workflows/")
FORBIDDEN_PATH_TOKENS = (
    ".env",
    "secret",
    "credential",
    "private_key",
    "id_rsa",
    "id_ed25519",
)

MAX_READ_BYTES = 200_000
DEFAULT_TEST_TIMEOUT = 300
MAX_TEST_TIMEOUT = 1_800
MAX_TEST_OUTPUT_BYTES = 8_000

# Only ordinary process/runtime settings cross into repository-controlled tests.
# Provider credentials, CI tokens, cloud keys, and arbitrary parent settings do not.
_TEST_ENV_ALLOWLIST = frozenset({
    "PATH",
    "HOME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
})


def _test_environment() -> Dict[str, str]:
    """Build a minimal environment for untrusted repository test code."""
    env = {key: value for key, value in os.environ.items() if key in _TEST_ENV_ALLOWLIST}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ------------------------------------------------------------------ sandbox
def resolve_repo_root(root: Optional[os.PathLike | str] = None) -> Path:
    """The configured repository root, or ``AGENCY_TOOL_REPO_ROOT``, or the cwd."""
    raw = root if root is not None else os.getenv(REPO_ROOT_ENV) or os.getcwd()
    candidate = Path(raw).expanduser()
    if not candidate.exists() or not candidate.is_dir():
        raise ToolSandboxError(f"configured repo root does not exist or is not a directory: {raw}")
    return candidate.resolve()


def resolve_in_root(root: os.PathLike | str, path: str) -> Path:
    """Resolve ``path`` inside ``root``, refusing anything that escapes it."""
    if not isinstance(path, str) or not path.strip():
        raise ToolArgumentError("path must be a non-empty string")
    root_resolved = Path(root).resolve()
    candidate = Path(path).expanduser()
    target = candidate if candidate.is_absolute() else root_resolved / candidate
    resolved = target.resolve()  # follows symlinks: an escaping link is caught below
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ToolSandboxError(
            f"refusing {path!r}: it resolves outside the configured repo root {root_resolved}"
        )
    relative = "." if resolved == root_resolved else resolved.relative_to(root_resolved).as_posix()
    if relative != "." and relative.startswith(FORBIDDEN_PATH_PREFIXES):
        raise ToolSandboxError(
            f"refusing {relative!r}: Git control and workflow files are out of bounds for tools"
        )
    lowered = f"/{relative.lower()}/"
    for token in FORBIDDEN_PATH_TOKENS:
        if token in lowered:
            raise ToolSandboxError(
                f"refusing {relative!r}: secret/credential material is out of bounds for tools"
            )
    return resolved


def _relative(root: Path, target: Path) -> str:
    return "." if target == root else target.relative_to(root).as_posix()


# ----------------------------------------------------------------- read_file
def read_file(
    root: os.PathLike | str,
    path: str,
    max_bytes: int = MAX_READ_BYTES,
) -> Dict[str, Any]:
    """Read a text file inside the root, capped at ``max_bytes``."""
    root_resolved = resolve_repo_root(root)
    target = resolve_in_root(root_resolved, path)
    if not target.exists():
        raise ToolArgumentError(f"no such file inside the repo root: {_relative(root_resolved, target)}")
    if target.is_dir():
        raise ToolArgumentError(f"{_relative(root_resolved, target)!r} is a directory, not a file")
    size = target.stat().st_size
    with open(target, "rb") as handle:
        data = handle.read(max(0, int(max_bytes)) + 1)
    truncated = len(data) > max_bytes
    return {
        "path": _relative(root_resolved, target),
        "root": str(root_resolved),
        "bytes": size,
        "returned_bytes": len(data[:max_bytes]),
        "truncated": truncated,
        "content": data[:max_bytes].decode("utf-8", errors="replace"),
    }


# ----------------------------------------------------------------- run_tests
def pytest_command() -> List[str]:
    """The CI form when available: the ``pytest`` console entry point.

    ``python -m pytest`` prepends the cwd to ``sys.path`` and can hide an
    ``src.*`` import problem, so prefer the console script sitting next to the
    running interpreter and fall back to ``-m pytest`` only when it is absent.
    """
    script = Path(sys.executable).parent / "pytest"
    if script.exists():
        return [str(script)]
    return [sys.executable, "-m", "pytest"]


def _tail(raw: bytes, limit: int) -> str:
    if limit <= 0:
        return ""
    return raw[-limit:].decode("utf-8", errors="replace")


def run_tests(
    root: os.PathLike | str,
    target: str = ".",
    timeout_seconds: int = DEFAULT_TEST_TIMEOUT,
    max_output_bytes: int = MAX_TEST_OUTPUT_BYTES,
) -> Dict[str, Any]:
    """Run the repository's pytest suite inside the root, bounded in time and output."""
    root_resolved = resolve_repo_root(root)
    timeout = int(timeout_seconds)
    if timeout < 1 or timeout > MAX_TEST_TIMEOUT:
        raise ToolArgumentError(f"timeout_seconds must be between 1 and {MAX_TEST_TIMEOUT}")
    limit = int(max_output_bytes)
    if limit < 0:
        raise ToolArgumentError("max_output_bytes must be >= 0")
    workdir = resolve_in_root(root_resolved, target)
    if not workdir.exists():
        raise ToolArgumentError(f"test target does not exist: {target!r}")
    if not workdir.is_dir():
        raise ToolArgumentError(f"test target must be a directory inside the repo root: {target!r}")

    command = pytest_command() + ["-q", _relative(root_resolved, workdir)]
    env = _test_environment()
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, sandboxed cwd
            command,
            cwd=str(root_resolved),
            env=env,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"") + (exc.stderr or b"")
        return {
            "ok": False,
            "timed_out": True,
            "returncode": None,
            "timeout_seconds": timeout,
            "command": command,
            "root": str(root_resolved),
            "summary": f"timed out after {timeout}s",
            "truncated": len(raw) > limit,
            "output_tail": _tail(raw, limit),
        }
    raw = (proc.stdout or b"") + (proc.stderr or b"")
    lines = [line.strip() for line in raw.decode("utf-8", errors="replace").splitlines() if line.strip()]
    return {
        "ok": proc.returncode == 0,
        "timed_out": False,
        "returncode": proc.returncode,
        "timeout_seconds": timeout,
        "command": command,
        "root": str(root_resolved),
        "summary": lines[-1] if lines else "",
        "truncated": len(raw) > limit,
        "output_tail": _tail(raw, limit),
    }


# ---------------------------------------------------------------- declarations
READ_FILE_PARAMETERS: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Path to the file, relative to the repo root (or an absolute path inside it).",
        },
        "max_bytes": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_READ_BYTES,
            "description": f"Read cap in bytes (default and maximum {MAX_READ_BYTES}).",
        },
    },
    "required": ["path"],
}

RUN_TESTS_PARAMETERS: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "Directory to test, relative to the repo root (default '.', the whole suite).",
        },
        "timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TEST_TIMEOUT,
            "description": f"Hard wall-clock limit (default {DEFAULT_TEST_TIMEOUT}).",
        },
        "max_output_bytes": {
            "type": "integer",
            "minimum": 0,
            "description": f"Tail of the output to return (default {MAX_TEST_OUTPUT_BYTES}).",
        },
    },
    "required": [],
}


def read_file_tool(root: Optional[os.PathLike | str] = None) -> Tool:
    root_path = resolve_repo_root(root)

    def executor(path: str, max_bytes: int = MAX_READ_BYTES) -> Dict[str, Any]:
        return read_file(root_path, path, max_bytes)

    return Tool(
        name="read_file",
        description=(
            "Read a text file from the configured repository root. Refused outside the "
            "root and for secret/credential paths; output is size-capped."
        ),
        parameters=READ_FILE_PARAMETERS,
        risk=ToolRisk.READ,
        executor=executor,
        tags=("filesystem", "read"),
    )


def run_tests_tool(root: Optional[os.PathLike | str] = None) -> Tool:
    root_path = resolve_repo_root(root)

    def executor(
        target: str = ".",
        timeout_seconds: int = DEFAULT_TEST_TIMEOUT,
        max_output_bytes: int = MAX_TEST_OUTPUT_BYTES,
    ) -> Dict[str, Any]:
        return run_tests(root_path, target, timeout_seconds, max_output_bytes)

    return Tool(
        name="run_tests",
        description=(
            "Run the repository's pytest suite inside the configured repo root, bounded by "
            "timeout and output cap; returns pass/fail plus the tail of the output."
        ),
        parameters=RUN_TESTS_PARAMETERS,
        risk=ToolRisk.WRITE_LOCAL,
        executor=executor,
        tags=("tests", "verification"),
    )


def default_registry(root: Optional[os.PathLike | str] = None) -> ToolRegistry:
    """The registry of built-in tools, sandboxed to one repo root."""
    root_path = resolve_repo_root(root)
    return ToolRegistry([read_file_tool(root_path), run_tests_tool(root_path)])
