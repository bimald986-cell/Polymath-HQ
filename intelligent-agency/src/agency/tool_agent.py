"""A reachable, tool-using agent loop.

``run_agent_loop`` used to be a harness with no production caller: nothing in
the HQ could execute a tool, so nothing could verify its own work. This module
gives that loop a caller (``run_tool_loop``, reachable from
``cli.py loop ...``) and two planners:

* :class:`ScriptedPlanner` — a fixed list of tool calls. Deterministic, needs no
  model, and is what the tests exercise end to end.
* :class:`LLMToolPlanner` — the model is asked for a JSON tool call, which is
  then executed through the registry and the policy gate. The backend stays the
  single prompt-in/string-out ``LLMBackend`` (``llm.py:19-20``): the tool schema
  is rendered into the system prompt and the reply is parsed, so no new
  dependency and no vendor function-calling API is assumed.

Every run is observable: the :class:`~agency.agent_loop.LoopResult` is returned
and, when ``out_path`` is given, appended as one JSON line. Policy decisions go
to the shared audit sink (``HORIZON_POLICY_AUDIT_PATH`` when configured).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .agent_loop import LoopResult, LoopStep, run_agent_loop
from .builtin_tools import default_registry
from .llm import LLMBackend, get_backend
from .policy import PolicyEngine, default_engine
from .tools import ToolDispatcher, ToolRegistry

#: How much of a tool observation is fed back to the model.
MAX_OBSERVATION_CHARS = 4_000

TOOL_PROTOCOL_SYSTEM_PROMPT = """You are an HQ agent working inside one repository root.
You can call exactly these tools:
{tool_specs}

Reply with exactly one JSON object and nothing else:
  {{"tool": "<tool name>", "arguments": {{...}}}}   to call a tool
  {{"final": "<answer>"}}                            when you are done

Rules: use only the tools listed above; pass only arguments the tool declares;
base every claim on a tool result you actually received, never on memory.
"""


def parse_tool_call(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from a model reply, or ``None``.

    Tolerates surrounding prose and ``` fences by scanning for the first ``{``
    that starts a decodable object.
    """
    if not isinstance(text, str):
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


class ScriptedPlanner:
    """A planner that replays a fixed plan of tool calls.

    Each entry is ``{"tool": name, "arguments": {...}}`` or ``{"final": text}``.
    When the plan is exhausted the loop terminates and its answer is the
    observations it collected, so the run is still observable.
    """

    def __init__(self, calls: Sequence[Mapping[str, Any]]):
        self.calls = [dict(call) for call in calls]

    def __call__(self, index: int, prior_steps: List[LoopStep]) -> Dict[str, Any]:
        position = index - 1
        if position >= len(self.calls):
            return {
                "observation": [step.observation for step in prior_steps],
                "terminal": True,
                "answer": [step.observation for step in prior_steps],
            }
        call = self.calls[position]
        if "final" in call and "tool" not in call:
            return {"observation": call["final"], "terminal": True, "answer": call["final"]}
        return {
            "tool": call.get("tool"),
            "arguments": call.get("arguments") or {},
        }


class LLMToolPlanner:
    """Ask a backend for the next tool call, in the JSON protocol above."""

    def __init__(
        self,
        backend: LLMBackend,
        registry: ToolRegistry,
        *,
        task: str = "",
        max_observation_chars: int = MAX_OBSERVATION_CHARS,
    ):
        self.backend = backend
        self.registry = registry
        self.task = task
        self.max_observation_chars = max_observation_chars

    def system_prompt(self) -> str:
        specs = json.dumps(self.registry.specs(), indent=2, sort_keys=True)
        return TOOL_PROTOCOL_SYSTEM_PROMPT.format(tool_specs=specs)

    def user_prompt(self, prior_steps: List[LoopStep]) -> str:
        transcript = json.dumps(
            [{"index": s.index, "tool": s.tool, "observation": s.observation} for s in prior_steps],
            default=str,
        )
        return (
            f"Task: {self.task}\n\n"
            f"Results so far:\n{transcript[-self.max_observation_chars:]}"
        )

    def __call__(self, index: int, prior_steps: List[LoopStep]) -> Dict[str, Any]:
        raw = self.backend.complete(self.system_prompt(), self.user_prompt(prior_steps))
        call = parse_tool_call(raw)
        if call is None:
            return {
                "observation": {
                    "error": "the model reply contained no JSON tool call",
                    "reply": (raw or "")[:500],
                },
                "terminal": True,
                "answer": raw,
            }
        if "tool" not in call:
            final = call.get("final", call)
            return {"observation": final, "terminal": True, "answer": final}
        return {"tool": call.get("tool"), "arguments": call.get("arguments") or {}}


def persist_loop_result(path: str, payload: Mapping[str, Any]) -> str:
    """Append one JSON line describing a run. Returns the path written."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True, default=str) + "\n")
    return path


def run_tool_loop(
    *,
    task: str = "",
    registry: Optional[ToolRegistry] = None,
    backend: Optional[LLMBackend] = None,
    policy: Optional[PolicyEngine] = None,
    plan: Optional[Sequence[Mapping[str, Any]]] = None,
    max_steps: int = 6,
    actor: str = "horizon",
    president_authorized: bool = False,
    out_path: Optional[str] = None,
) -> LoopResult:
    """Run the bounded loop with real tools — the HQ's tool-use entry point.

    ``registry`` defaults to the built-in sandboxed tools; ``plan`` replays a
    fixed list of calls (no model needed), otherwise the configured backend is
    asked for each next call.
    """
    active_registry = registry if registry is not None else default_registry()
    active_policy = policy if policy is not None else default_engine()
    dispatcher = ToolDispatcher(active_registry, active_policy, actor=actor)
    planner: Any = ScriptedPlanner(plan) if plan is not None else LLMToolPlanner(
        backend if backend is not None else get_backend(), active_registry, task=task
    )
    result = run_agent_loop(
        planner,
        max_steps=max_steps,
        policy=dispatcher.policy,
        dispatcher=dispatcher,
        actor=actor,
        president_authorized=president_authorized,
    )
    if out_path:
        persist_loop_result(
            out_path,
            {
                "task": task,
                "actor": actor,
                "tools": active_registry.names(),
                "status": result.status,
                "answer": result.answer,
                "message": result.message,
                "steps": result.as_dict()["steps"],
            },
        )
    return result
