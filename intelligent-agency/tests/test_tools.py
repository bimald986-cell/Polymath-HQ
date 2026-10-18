"""Tests for the tool contract, registry and the mandatory policy gate."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import pytest  # noqa: E402

from agency.policy import PolicyEngine, PolicyAuditSink, ToolRisk, default_engine
from agency.tools import (
    Tool,
    ToolArgumentError,
    ToolDispatcher,
    ToolRegistry,
    ToolResult,
    UnknownToolError,
)


def _echo_tool(name="echo", risk=ToolRisk.READ, calls=None, result=None):
    """A tool whose executor records that it ran."""

    def executor(text: str) -> object:
        if calls is not None:
            calls.append(text)
        return result if result is not None else {"echo": text}

    return Tool(
        name=name,
        description="Echo back the given text.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        risk=risk,
        executor=executor,
    )


# --------------------------------------------------------------- registry (stage 1)
def test_registry_resolves_registered_tool_and_lists_specs():
    registry = ToolRegistry([_echo_tool()])
    assert registry.names() == ["echo"]
    tool = registry.resolve("echo")
    assert tool.risk is ToolRisk.READ
    spec = registry.specs()[0]
    assert spec["name"] == "echo"
    assert spec["risk"] == "read"
    assert spec["parameters"]["required"] == ["text"]
    assert "echo" in registry
    assert len(registry) == 1


def test_registry_rejects_unknown_tool_with_clear_error():
    registry = ToolRegistry([_echo_tool()])
    with pytest.raises(UnknownToolError) as excinfo:
        registry.resolve("no_such_tool")
    message = str(excinfo.value)
    assert "no_such_tool" in message
    assert "echo" in message  # names what *is* available


def test_registry_rejects_duplicate_and_malformed_tools():
    registry = ToolRegistry([_echo_tool()])
    with pytest.raises(ValueError):
        registry.register(_echo_tool())
    with pytest.raises(TypeError):
        registry.register("not-a-tool")  # type: ignore[arg-type]


def test_arguments_are_validated_against_the_declared_spec():
    tool = _echo_tool()
    assert tool.validate_arguments({"text": "hi"}) == {"text": "hi"}
    with pytest.raises(ToolArgumentError):
        tool.validate_arguments({})
    with pytest.raises(ToolArgumentError):
        tool.validate_arguments({"text": 5})
    with pytest.raises(ToolArgumentError):
        tool.validate_arguments({"text": "hi", "surprise": 1})
    with pytest.raises(ToolArgumentError):
        tool.validate_arguments([("text", "hi")])  # type: ignore[arg-type]


# ------------------------------------------------------------ mandatory gate (stage 2)
def test_dispatch_runs_executor_when_policy_allows():
    calls = []
    dispatcher = ToolDispatcher(ToolRegistry([_echo_tool(calls=calls)]))
    result = dispatcher.dispatch("echo", {"text": "hello"})
    assert result.ok is True
    assert result.output == {"echo": "hello"}
    assert calls == ["hello"]
    assert result.decision["allowed"] is True
    assert result.risk == "read"


def test_denied_tool_never_executes_its_executor():
    calls = []
    registry = ToolRegistry([_echo_tool(name="merge_pull_request", risk=ToolRisk.IRREVERSIBLE, calls=calls)])
    dispatcher = ToolDispatcher(registry, default_engine())
    result = dispatcher.dispatch("merge_pull_request", {"text": "now"})
    assert result.ok is False
    assert result.denied is True
    assert result.decision["requires_president"] is True
    assert "President" in result.error
    assert calls == []  # the executor was never entered


def test_denial_is_recorded_in_the_audit_trail():
    sink = PolicyAuditSink()
    engine = PolicyEngine(audit_sink=sink)
    registry = ToolRegistry([_echo_tool(name="spend_funds", risk=ToolRisk.IRREVERSIBLE)])
    dispatcher = ToolDispatcher(registry, engine, actor="atlas")
    dispatcher.dispatch("spend_funds", {"text": "100"})
    entry = sink.last(actor="atlas")
    assert entry is not None
    assert entry["tool"] == "spend_funds"
    assert entry["allowed"] is False


def test_gate_uses_the_risk_the_tool_declares_not_the_default():
    """A registered tool's own risk class is what the engine classifies it by."""
    tool = _echo_tool(name="local_file_read_custom", risk=ToolRisk.IRREVERSIBLE)
    dispatcher = ToolDispatcher(ToolRegistry([tool]))
    assert dispatcher.policy.classify("local_file_read_custom") is ToolRisk.IRREVERSIBLE
    assert dispatcher.dispatch("local_file_read_custom", {"text": "x"}).denied is True


def test_gate_cannot_be_bypassed_by_a_caller_that_omits_the_tool_name():
    """The deliberate change from the old ``if tool:`` convention.

    ``run_agent_loop`` only checked policy when the caller supplied a truthy
    ``"tool"`` key. Here there is no separate declaration step: the dispatcher
    is the only route to an executor and it always checks. A caller that wants
    the executor to run anyway must go *around* the dispatcher, which no
    production path does.
    """
    calls = []
    registry = ToolRegistry([_echo_tool(name="delete_production_data", risk=ToolRisk.IRREVERSIBLE, calls=calls)])
    dispatcher = ToolDispatcher(registry, default_engine())
    # No "tool" declaration exists to forget — the name is the call.
    result = dispatcher.dispatch("delete_production_data", {"text": "everything"})
    assert result.denied is True
    assert calls == []
    # And an executor that raises is contained, never propagated as success.
    def boom(**kwargs):
        raise RuntimeError("kaboom")

    registry.register(Tool(name="boom", description="d", parameters={"type": "object"},
                           risk=ToolRisk.READ, executor=boom))
    failed = dispatcher.dispatch("boom")
    assert failed.ok is False and failed.denied is False and "kaboom" in failed.error


def test_unknown_tool_is_rejected_by_the_dispatcher():
    dispatcher = ToolDispatcher(ToolRegistry([_echo_tool()]))
    with pytest.raises(UnknownToolError):
        dispatcher.dispatch("ghost", {})


def test_invalid_arguments_do_not_reach_the_executor():
    calls = []
    dispatcher = ToolDispatcher(ToolRegistry([_echo_tool(calls=calls)]))
    result = dispatcher.dispatch("echo", {"text": 12})
    assert result.ok is False
    assert "must be string" in result.error
    assert calls == []


def test_executor_may_return_a_tool_result_directly():
    def executor(text: str) -> ToolResult:
        return ToolResult(tool="", ok=False, error="nothing to do")

    registry = ToolRegistry([Tool(name="picky", description="d", parameters={
        "type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
    }, risk=ToolRisk.READ, executor=executor)])
    result = ToolDispatcher(registry).dispatch("picky", {"text": "x"})
    assert result.ok is False
    assert result.error == "nothing to do"
    assert result.tool == "picky"  # filled in by the dispatcher
    assert result.risk == "read"
