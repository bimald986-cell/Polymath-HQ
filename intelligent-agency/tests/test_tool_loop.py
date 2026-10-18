"""Tests for the reachable tool-using loop (stage 4)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.agent_loop import run_agent_loop  # noqa: E402
from agency.builtin_tools import default_registry  # noqa: E402
from agency.policy import PolicyEngine, PolicyAuditSink, ToolRisk, default_engine  # noqa: E402
from agency.tool_agent import (  # noqa: E402
    LLMToolPlanner,
    ScriptedPlanner,
    parse_tool_call,
    run_tool_loop,
)
from agency.tools import Tool, ToolDispatcher, ToolRegistry  # noqa: E402


class RecordingBackend:
    """A backend that replays canned replies and records the prompts it saw."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def complete(self, system_prompt, user_prompt):
        self.prompts.append((system_prompt, user_prompt))
        if not self.replies:
            return '{"final": "out of replies"}'
        return self.replies.pop(0)


def _write(root, relative, text):
    path = os.path.join(str(root), relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


# ------------------------------------------------------------------ planners
def test_parse_tool_call_handles_fences_and_prose():
    assert parse_tool_call('{"tool": "read_file", "arguments": {"path": "a"}}')["tool"] == "read_file"
    assert parse_tool_call('```json\n{"final": "done"}\n```')["final"] == "done"
    assert parse_tool_call("I will not call a tool.") is None
    assert parse_tool_call("") is None


def test_scripted_planner_replays_calls_then_terminates():
    planner = ScriptedPlanner([{"tool": "read_file", "arguments": {"path": "x"}}])
    assert planner(1, []) == {"tool": "read_file", "arguments": {"path": "x"}}
    exhausted = planner(2, [])
    assert exhausted["terminal"] is True


# ------------------------------------------------------- the loop with real tools
def test_loop_executes_a_real_tool_end_to_end(tmp_path):
    """The honest end-to-end case: the loop reads a real file and reports it."""
    _write(tmp_path, "notes/hq.txt", "verified: 132 tests")
    result = run_tool_loop(
        task="check the note",
        registry=default_registry(tmp_path),
        plan=[{"tool": "read_file", "arguments": {"path": "notes/hq.txt"}}],
        actor="atlas",
    )
    assert result.status == "completed"
    first = result.steps[0]
    assert first.tool == "read_file"
    assert first.observation["ok"] is True
    assert first.observation["output"]["content"] == "verified: 132 tests"
    assert first.error is None


def test_loop_can_run_the_test_suite_it_lives_in(tmp_path):
    _write(tmp_path, "threadbare.py", "def add(a, b):\n    return a + b\n")
    _write(tmp_path, "tests/test_threadbare.py",
           "import sys, os\nsys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n"
           "from threadbare import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    result = run_tool_loop(
        registry=default_registry(tmp_path),
        plan=[{"tool": "run_tests", "arguments": {"target": ".", "timeout_seconds": 120}}],
    )
    assert result.status == "completed"
    observation = result.steps[0].observation
    assert observation["ok"] is True, observation
    assert "1 passed" in observation["output"]["summary"]


def test_loop_is_bounded_when_the_plan_never_terminates(tmp_path):
    _write(tmp_path, "a.txt", "x")
    result = run_tool_loop(
        registry=default_registry(tmp_path),
        plan=[{"tool": "read_file", "arguments": {"path": "a.txt"}}] * 5,
        max_steps=3,
    )
    assert result.status == "max_steps"
    assert len(result.steps) == 3


def test_loop_blocks_a_tool_policy_refuses_and_does_not_execute_it(tmp_path):
    calls = []
    registry = ToolRegistry([Tool(
        name="publish_episode",
        description="Irreversible: would publish.",
        parameters={"type": "object", "properties": {}, "required": []},
        risk=ToolRisk.IRREVERSIBLE,
        executor=lambda **kwargs: calls.append("ran"),
    )])
    sink = PolicyAuditSink()
    engine = PolicyEngine(audit_sink=sink)
    result = run_tool_loop(
        registry=registry,
        policy=engine,
        plan=[{"tool": "publish_episode", "arguments": {}}],
        actor="horizon",
    )
    assert result.status == "blocked"
    assert "President" in result.message
    assert calls == []  # the executor was never entered
    assert sink.last(actor="horizon")["allowed"] is False


def test_loop_result_is_persisted_and_observable(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    out = tmp_path / "runs" / "run.jsonl"
    result = run_tool_loop(
        registry=default_registry(tmp_path),
        plan=[{"tool": "read_file", "arguments": {"path": "a.txt"}}],
        out_path=str(out),
        task="read a.txt",
    )
    assert result.status == "completed"
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["task"] == "read a.txt"
    assert record["status"] == "completed"
    assert record["steps"][0]["tool"] == "read_file"
    assert record["tools"] == ["read_file", "run_tests"]


def test_loop_policy_decisions_survive_in_the_audit_trail(tmp_path):
    _write(tmp_path, "a.txt", "hello")
    sink = PolicyAuditSink()
    run_tool_loop(
        registry=default_registry(tmp_path),
        policy=PolicyEngine(audit_sink=sink),
        plan=[{"tool": "read_file", "arguments": {"path": "a.txt"}}],
        actor="atlas",
    )
    entry = sink.last(actor="atlas")
    assert entry["tool"] == "read_file" and entry["allowed"] is True


# ------------------------------------------------------------ the LLM planner
def test_llm_planner_turns_a_model_reply_into_a_real_tool_call(tmp_path):
    _write(tmp_path, "a.txt", "from the model's perspective")
    backend = RecordingBackend([
        '{"tool": "read_file", "arguments": {"path": "a.txt"}}',
        '{"final": "read it"}',
    ])
    result = run_tool_loop(
        task="read a.txt",
        registry=default_registry(tmp_path),
        backend=backend,
        max_steps=4,
    )
    assert result.status == "completed"
    assert result.answer == "read it"
    assert result.steps[0].observation["output"]["content"] == "from the model's perspective"
    # the tool schema reached the model, so it could know what it may call
    assert "read_file" in backend.prompts[0][0]


def test_llm_planner_fails_loudly_on_an_unparseable_reply(tmp_path):
    backend = RecordingBackend(["[mock reply] I would read the file."])
    result = run_tool_loop(
        task="read a.txt",
        registry=default_registry(tmp_path),
        backend=backend,
        max_steps=2,
    )
    assert result.status == "completed"
    assert "no JSON tool call" in result.steps[0].observation["error"]


def test_llm_planner_reply_naming_an_unknown_tool_is_contained(tmp_path):
    backend = RecordingBackend(['{"tool": "rm_rf_everything", "arguments": {}}'])
    result = run_tool_loop(
        task="do something",
        registry=default_registry(tmp_path),
        backend=backend,
        max_steps=2,
    )
    assert result.status == "error"  # UnknownToolError, surfaced not swallowed
    assert "unknown tool" in result.message


# --------------------------------------------------- gate not bypassable, in-loop
def test_a_step_cannot_execute_a_tool_without_the_gate(tmp_path):
    """Even a planner that supplies its own executor cannot skip the gate."""
    executed = []

    class SneakyPlanner:
        def __call__(self, index, prior_steps):
            # Names a forbidden tool and supplies its own observation, hoping the
            # loop will treat that as the executed result.
            executed.append("planner-supplied observation")
            return {"tool": "delete_production_data", "observation": "deleted", "terminal": True}

    registry = ToolRegistry([Tool(
        name="delete_production_data",
        description="Irreversible.",
        parameters={"type": "object", "properties": {}, "required": []},
        risk=ToolRisk.IRREVERSIBLE,
        executor=lambda **kwargs: executed.append("executor"),
    )])
    result = run_agent_loop(
        SneakyPlanner(),
        max_steps=2,
        dispatcher=ToolDispatcher(registry, default_engine()),
    )
    assert result.status == "blocked"
    assert executed == ["planner-supplied observation"]  # only the planner ran
    assert "President" in result.message


def test_unregistered_tool_name_in_a_scripted_plan_is_rejected(tmp_path):
    result = run_tool_loop(
        registry=default_registry(tmp_path),
        plan=[{"tool": "read_secrets", "arguments": {}}],
    )
    assert result.status == "error"
    assert "unknown tool" in result.message
