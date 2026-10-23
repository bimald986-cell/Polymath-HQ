"""Tests for the two sandboxed built-in tools: read_file and run_tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import agency.builtin_tools as builtin_tools  # noqa: E402
from agency.builtin_tools import (  # noqa: E402
    MAX_READ_BYTES,
    default_registry,
    read_file,
    resolve_in_root,
    run_tests,
)
from agency.policy import ToolRisk, default_engine  # noqa: E402
from agency.tools import ToolDispatcher, ToolSandboxError  # noqa: E402


def _write(root, relative, text):
    path = os.path.join(str(root), relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


# ------------------------------------------------------------------ read_file
def test_read_file_returns_content_inside_the_root(tmp_path):
    _write(tmp_path, "docs/note.txt", "hello HQ")
    result = read_file(tmp_path, "docs/note.txt")
    assert result["content"] == "hello HQ"
    assert result["path"] == "docs/note.txt"
    assert result["truncated"] is False


def test_read_file_is_capped_and_reports_truncation(tmp_path):
    _write(tmp_path, "big.txt", "x" * (MAX_READ_BYTES + 500))
    result = read_file(tmp_path, "big.txt", max_bytes=64)
    assert result["truncated"] is True
    assert result["returned_bytes"] == 64
    assert result["content"] == "x" * 64
    assert result["bytes"] == MAX_READ_BYTES + 500


def test_read_file_refuses_paths_outside_the_root(tmp_path):
    _write(tmp_path, "inside.txt", "ok")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    for escaping in ("../outside.txt", str(outside), "/etc/hostname"):
        try:
            read_file(tmp_path, escaping)
        except ToolSandboxError as exc:
            assert "outside the configured repo root" in str(exc)
        else:  # pragma: no cover - a sandbox escape must never pass
            raise AssertionError(f"{escaping!r} was not refused")


def test_read_file_refuses_a_symlink_that_escapes_the_root(tmp_path):
    outside = tmp_path.parent / "target.txt"
    outside.write_text("nope", encoding="utf-8")
    link = tmp_path / "link.txt"
    os.symlink(outside, link)
    try:
        read_file(tmp_path, "link.txt")
    except ToolSandboxError as exc:
        assert "outside the configured repo root" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an escaping symlink was not refused")


def test_read_file_refuses_secret_and_control_paths(tmp_path):
    for relative in (".env", "config/secret.yaml", "deploy/credentials.json",
                     "keys/private_key.pem", ".git/config"):
        _write(tmp_path, relative, "sensitive")
        try:
            read_file(tmp_path, relative)
        except ToolSandboxError as exc:
            assert "out of bounds for tools" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"{relative!r} was not refused")


def test_read_file_reports_a_missing_file_as_a_failed_call(tmp_path):
    dispatcher = ToolDispatcher(default_registry(tmp_path), default_engine())
    result = dispatcher.dispatch("read_file", {"path": "nope.txt"})
    assert result.ok is False and result.denied is False
    assert "no such file" in result.error


def test_resolve_in_root_rejects_traversal_and_accepts_the_root_itself(tmp_path):
    assert resolve_in_root(tmp_path, ".") == tmp_path.resolve()
    try:
        resolve_in_root(tmp_path, "../")
    except ToolSandboxError:
        pass
    else:  # pragma: no cover
        raise AssertionError("'../' was not refused")


# ------------------------------------------------------------------ run_tests
def test_run_tests_reports_pass_inside_the_root(tmp_path):
    _write(tmp_path, "tests/test_ok.py", "def test_ok():\n    assert 1 + 1 == 2\n")
    result = run_tests(tmp_path, ".", timeout_seconds=120)
    assert result["ok"] is True, result
    assert result["returncode"] == 0
    assert "1 passed" in result["summary"]
    assert result["timed_out"] is False


def test_run_tests_reports_failure_with_the_tail_of_the_output(tmp_path):
    _write(tmp_path, "tests/test_bad.py", "def test_bad():\n    assert False\n")
    result = run_tests(tmp_path, "tests", timeout_seconds=120)
    assert result["ok"] is False
    assert result["returncode"] != 0
    assert "1 failed" in result["summary"]
    assert "assert False" in result["output_tail"]


def test_run_tests_honours_the_timeout(tmp_path):
    _write(tmp_path, "tests/test_slow.py", "import time\n\ndef test_slow():\n    time.sleep(30)\n")
    result = run_tests(tmp_path, ".", timeout_seconds=1)
    assert result["timed_out"] is True
    assert result["ok"] is False
    assert "timed out" in result["summary"]


def test_run_tests_caps_the_output_it_returns(tmp_path):
    _write(tmp_path, "tests/test_chatty.py",
           "def test_chatty():\n    print('line ' * 5000)\n    assert True\n")
    result = run_tests(tmp_path, ".", timeout_seconds=120, max_output_bytes=64)
    assert result["truncated"] is True
    assert len(result["output_tail"]) == 64


def test_run_tests_refuses_a_target_outside_the_root(tmp_path):
    try:
        run_tests(tmp_path, "../", timeout_seconds=10)
    except ToolSandboxError:
        pass
    else:  # pragma: no cover
        raise AssertionError("an escaping test target was not refused")


# ------------------------------------------------------------ through the gate
def test_builtin_tools_are_registered_with_their_declared_risk(tmp_path):
    registry = default_registry(tmp_path)
    assert registry.names() == ["read_file", "run_tests"]
    assert registry.risks()["read_file"] is ToolRisk.READ
    assert registry.risks()["run_tests"] is ToolRisk.WRITE_LOCAL


def test_read_file_through_the_dispatcher_reads_and_is_audited(tmp_path):
    _write(tmp_path, "README.md", "# hello")
    dispatcher = ToolDispatcher(default_registry(tmp_path), default_engine(), actor="atlas")
    result = dispatcher.dispatch("read_file", {"path": "README.md"})
    assert result.ok is True
    assert result.output["content"] == "# hello"
    assert result.decision["allowed"] is True
    assert dispatcher.policy.audit_sink.last(actor="atlas")["tool"] == "read_file"


def test_sandbox_refusal_becomes_a_failed_call_not_a_bypass(tmp_path):
    """A refusal inside the executor is contained by the dispatcher."""
    dispatcher = ToolDispatcher(default_registry(tmp_path), default_engine())
    result = dispatcher.dispatch("read_file", {"path": "../../etc/hostname"})
    assert result.ok is False
    assert result.denied is False
    assert "outside the configured repo root" in result.error



def test_run_tests_does_not_inherit_unapproved_parent_environment(tmp_path, monkeypatch):
    captured = {}

    def fake_run(command, *, cwd, env, capture_output, timeout):
        captured.update(env)
        return type(
            "Completed",
            (),
            {"stdout": b"1 passed\n", "stderr": b"", "returncode": 0},
        )()

    monkeypatch.setenv("OPENAI_API_KEY", "do-not-forward")
    monkeypatch.setenv("GITHUB_TOKEN", "do-not-forward")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-forward")
    monkeypatch.setenv("UNAPPROVED_TEST_SETTING", "do-not-forward")
    monkeypatch.setattr(builtin_tools.subprocess, "run", fake_run)

    result = run_tests(tmp_path, target=".", timeout_seconds=5)

    assert result["ok"] is True
    assert "PATH" in captured
    assert captured["PYTHONDONTWRITEBYTECODE"] == "1"
    assert captured["PYTHONIOENCODING"] == "utf-8"
    for name in (
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "UNAPPROVED_TEST_SETTING",
    ):
        assert name not in captured
