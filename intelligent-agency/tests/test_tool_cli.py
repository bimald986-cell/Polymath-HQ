"""Tests for the *reachable* tool-use entry point (stage 4).

`run_agent_loop` alone proves nothing about the HQ being able to act: the loop
needs a production caller. These tests drive the real CLI (`cli.main`) and check
that a tool actually runs, that the run leaves a durable record, and that the
gate still holds when the loop is driven from the command line.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cli  # noqa: E402
from agency.llm import LLMConfigError  # noqa: E402


def _write(root, relative, text):
    path = os.path.join(str(root), relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


@pytest.fixture(autouse=True)
def _no_ambient_provider(monkeypatch):
    """The CLI must behave the same whatever provider the host happens to have."""
    monkeypatch.delenv("AGENCY_LLM", raising=False)
    monkeypatch.delenv("AGENCY_LLM_API_KEY", raising=False)


# --------------------------------------------------------------- reachability
def test_cli_tools_lists_only_the_tools_that_exist(tmp_path, capsys):
    assert cli.main(["tools", "--repo-root", str(tmp_path)]) == 0
    specs = json.loads(capsys.readouterr().out)
    assert sorted(s["name"] for s in specs) == ["read_file", "run_tests"]
    assert all("risk" in s for s in specs)


def test_cli_tool_reads_a_real_file_through_the_gate(tmp_path, capsys):
    _write(tmp_path, "notes/hq.txt", "the tool channel ran")
    code = cli.main(
        ["tool", "read_file", "--arg", "path=notes/hq.txt", "--repo-root", str(tmp_path)]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["output"]["content"] == "the tool channel ran"
    assert payload["risk"] == "read"
    assert payload["decision"]["allowed"] is True


def test_cli_tool_rejects_an_unregistered_name_without_a_traceback(tmp_path, capsys):
    code = cli.main(["tool", "merge_pull_request", "--repo-root", str(tmp_path)])
    assert code == 1
    assert "unknown tool" in capsys.readouterr().out


# ------------------------------------------------- the loop, run from the CLI
def test_cli_loop_executes_a_real_tool_and_persists_the_run(tmp_path, capsys):
    _write(tmp_path, "notes/hq.txt", "read by the loop")
    plan_file = os.path.join(str(tmp_path), "plan.json")
    with open(plan_file, "w", encoding="utf-8") as handle:
        json.dump([{"tool": "read_file", "arguments": {"path": "notes/hq.txt"}}], handle)
    runs = os.path.join(str(tmp_path), "runs", "tool_runs.jsonl")

    code = cli.main(
        [
            "loop",
            "--query",
            "read notes/hq.txt",
            "--plan",
            plan_file,
            "--repo-root",
            str(tmp_path),
            "--out",
            runs,
            "--actor",
            "cli-test",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["steps"][0]["observation"]["output"]["content"] == "read by the loop"
    # the run is observable after the process: one durable JSON line
    lines = open(runs, encoding="utf-8").read().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["task"] == "read notes/hq.txt"
    assert record["actor"] == "cli-test"
    assert record["tools"] == ["read_file", "run_tests"]
    assert record["steps"][0]["tool"] == "read_file"


def test_cli_loop_requires_a_live_model_when_the_model_picks_the_tools(tmp_path, capsys):
    """No --plan and no provider: refuse, rather than look busy on mock text."""
    code = cli.main(["loop", "--query", "do something", "--repo-root", str(tmp_path)])
    assert code == 2
    captured = capsys.readouterr()
    assert "No live LLM provider configured" in captured.err
    assert '"status"' not in captured.out


def test_cli_loop_mock_is_opt_in_and_claims_no_tool_run(tmp_path, capsys):
    code = cli.main(
        ["loop", "--query", "do something", "--repo-root", str(tmp_path), "--allow-mock-llm"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    # the mock reply contains no tool call, and the run says so instead of
    # pretending a tool ran
    assert payload["steps"][0]["tool"] is None
    assert "no JSON tool call" in payload["steps"][0]["observation"]["error"]


def test_cli_loop_reports_a_tool_that_does_not_exist_as_a_failed_run(tmp_path, capsys):
    plan_file = os.path.join(str(tmp_path), "plan.json")
    with open(plan_file, "w", encoding="utf-8") as handle:
        json.dump([{"tool": "read_secrets", "arguments": {"path": "/etc/passwd"}}], handle)
    code = cli.main(
        ["loop", "--plan", plan_file, "--repo-root", str(tmp_path), "--out",
         os.path.join(str(tmp_path), "runs.jsonl")]
    )
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert "unknown tool" in payload["message"]


def test_cli_loop_refuses_a_plan_that_escapes_the_root(tmp_path, capsys):
    outside = os.path.join(os.path.dirname(str(tmp_path)), "outside-plan-secret.txt")
    with open(outside, "w", encoding="utf-8") as handle:
        handle.write("not yours to read")
    plan_file = os.path.join(str(tmp_path), "plan.json")
    with open(plan_file, "w", encoding="utf-8") as handle:
        json.dump([{"tool": "read_file", "arguments": {"path": outside}}], handle)

    cli.main(["loop", "--plan", plan_file, "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out

    payload = json.loads(out)
    step = payload["steps"][0]
    assert step["tool"] == "read_file"
    assert step["observation"]["ok"] is False
    assert "not yours to read" not in out  # the file's content never came back
    os.unlink(outside)


def test_cli_loop_exit_code_is_nonzero_when_the_plan_never_terminates(tmp_path, capsys):
    plan_file = os.path.join(str(tmp_path), "plan.json")
    with open(plan_file, "w", encoding="utf-8") as handle:
        json.dump([{"tool": "read_file", "arguments": {"path": "notes/hq.txt"}}], handle)
    _write(tmp_path, "notes/hq.txt", "x")
    code = cli.main(
        ["loop", "--plan", plan_file, "--repo-root", str(tmp_path), "--max-steps", "1"]
    )
    assert code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "max_steps"


def test_llm_config_error_is_what_the_guard_raises():
    """Guards the guard: the CLI catches this exact type."""
    from agency.llm import MockBackend, get_backend, require_live_backend

    assert isinstance(get_backend(), MockBackend)
    with pytest.raises(LLMConfigError):
        require_live_backend()
