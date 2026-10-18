"""Tool contract, registry and the mandatory policy gate.

This is the HQ's first real *tool-use channel*: a declared tool (name,
description, JSON-schema-ish parameter spec, risk level, executor) can be
resolved from a registry and executed — but only through
:meth:`ToolDispatcher.dispatch`, which consults ``PolicyEngine.check`` **inside
the dispatch path itself**.

Design change from the earlier convention
-----------------------------------------
Before this module, the only policy gate on a tool call lived in
``run_agent_loop`` (``agent_loop.py:87``) and it fired only ``if tool:`` was
truthy in a dict the *caller* supplied. A caller that simply omitted the
``"tool"`` key executed its own executor with no gate, no risk class and no
audit entry — the gate was opt-in by convention.

Here the gate is not a convention and not a separate step a caller can forget:
the dispatcher is the only code that calls an executor, and it always checks
policy first, under the tool's *declared* risk. A denied tool never reaches its
executor (see ``tests/test_tools.py``), and every decision lands in the
:class:`~agency.policy.PolicyAuditSink`, so it survives the call.

Nothing here can merge, publish, spend or act irreversibly: the tools shipped
in ``builtin_tools.py`` read files and run the test suite inside one configured
repository root, and the ``ToolRisk`` classes that would permit more are still
blocked by the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .policy import PolicyDecision, PolicyEngine, ToolRisk, default_engine


class ToolError(Exception):
    """Base class for tool-layer failures."""


class UnknownToolError(ToolError):
    """Raised when a name does not resolve to a registered tool."""

    def __init__(self, name: str, known: Sequence[str] = ()):
        self.name = name
        self.known = list(known)
        known_txt = ", ".join(sorted(self.known)) if self.known else "<none registered>"
        super().__init__(f"unknown tool {name!r}: not in the registry (known tools: {known_txt})")


class ToolArgumentError(ToolError):
    """Raised when arguments fail the tool's declared parameter spec."""


class ToolSandboxError(ToolError):
    """Raised when a tool is asked to work outside its configured sandbox."""


# JSON types accepted by the parameter spec, mapped to the Python types we accept.
_JSON_TYPES: Dict[str, tuple] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
}


@dataclass
class ToolResult:
    """Outcome of one tool invocation, successful, denied or failed."""

    tool: str
    ok: bool
    output: Any = None
    error: Optional[str] = None
    denied: bool = False
    decision: Optional[Dict[str, Any]] = None
    risk: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "denied": self.denied,
            "risk": self.risk,
            "output": self.output,
            "error": self.error,
            "decision": self.decision,
        }


@dataclass(frozen=True)
class Tool:
    """A declared capability: metadata, risk class and the executor.

    ``parameters`` is a JSON-schema-ish object::

        {"type": "object",
         "properties": {"path": {"type": "string", "description": "..."}},
         "required": ["path"]}

    ``executor(**arguments)`` is called with validated keyword arguments and
    returns a JSON-serialisable value (or a :class:`ToolResult` to control the
    outcome itself).
    """

    name: str
    description: str
    parameters: Mapping[str, Any]
    risk: ToolRisk
    executor: Callable[..., Any]
    tags: tuple = field(default_factory=tuple)

    def spec(self) -> Dict[str, Any]:
        """The declaration handed to a planner/model, plus the risk class."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "risk": self.risk.value,
            "tags": list(self.tags),
        }

    def validate_arguments(self, arguments: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """Validate and normalise arguments against this tool's spec."""
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            raise ToolArgumentError(
                f"{self.name}: arguments must be an object, got {type(arguments).__name__}"
            )
        spec = dict(self.parameters or {})
        properties = dict(spec.get("properties") or {})
        required = list(spec.get("required") or [])
        cleaned: Dict[str, Any] = {}
        for key, value in arguments.items():
            if key not in properties:
                raise ToolArgumentError(
                    f"{self.name}: unexpected argument {key!r} "
                    f"(accepted: {', '.join(sorted(properties)) or '<none>'})"
                )
            cleaned[key] = _check_type(self.name, key, value, properties[key])
        missing = [key for key in required if key not in cleaned]
        if missing:
            raise ToolArgumentError(
                f"{self.name}: missing required argument(s): {', '.join(missing)}"
            )
        return cleaned


def _check_type(tool: str, key: str, value: Any, property_spec: Mapping[str, Any]) -> Any:
    declared = (property_spec or {}).get("type")
    if declared:
        expected = _JSON_TYPES.get(str(declared))
        if expected is None:
            raise ToolArgumentError(f"{tool}: unknown declared type {declared!r} for {key!r}")
        if str(declared) == "integer" and isinstance(value, bool):
            raise ToolArgumentError(f"{tool}: {key!r} must be an integer, got bool")
        if not isinstance(value, expected):
            raise ToolArgumentError(
                f"{tool}: {key!r} must be {declared}, got {type(value).__name__}"
            )
    choices = (property_spec or {}).get("enum")
    if choices and value not in choices:
        raise ToolArgumentError(
            f"{tool}: {key!r} must be one of {list(choices)}, got {value!r}"
        )
    for bound, op in (("minimum", "<"), ("maximum", ">")):
        limit = (property_spec or {}).get(bound)
        if limit is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if (op == "<" and value < limit) or (op == ">" and value > limit):
            raise ToolArgumentError(f"{tool}: {key!r} must not be {op} {limit}, got {value!r}")
    return value


class ToolRegistry:
    """Name → :class:`Tool` resolution. Unknown names are a clear error."""

    def __init__(self, tools: Optional[Sequence[Tool]] = None):
        self._tools: Dict[str, Tool] = {}
        for tool in tools or ():
            self.register(tool)

    # ---------------------------------------------------------------- mutate
    def register(self, tool: Tool) -> Tool:
        if not isinstance(tool, Tool):
            raise TypeError(f"expected a Tool, got {type(tool).__name__}")
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("tool name must be a non-empty string")
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        if not callable(tool.executor):
            raise TypeError(f"tool {tool.name!r} has no callable executor")
        if not isinstance(tool.risk, ToolRisk):
            raise TypeError(f"tool {tool.name!r} risk must be a ToolRisk, got {tool.risk!r}")
        self._tools[tool.name] = tool
        return tool

    # ---------------------------------------------------------------- read
    def resolve(self, name: str) -> Tool:
        try:
            return self._tools[str(name)]
        except KeyError:
            raise UnknownToolError(str(name), sorted(self._tools)) from None

    def names(self) -> List[str]:
        return sorted(self._tools)

    def specs(self) -> List[Dict[str, Any]]:
        return [self._tools[name].spec() for name in self.names()]

    def risks(self) -> Dict[str, ToolRisk]:
        return {name: tool.risk for name, tool in self._tools.items()}

    def __contains__(self, name: object) -> bool:
        return str(name) in self._tools

    def __len__(self) -> int:
        return len(self._tools)


class ToolDispatcher:
    """The only path from a tool *name* to an executor — always policy-checked.

    The registry is the source of truth for a registered tool's risk class: it
    is written into the engine's risk map at construction, so ``classify()``
    returns the risk the tool *declares* rather than the cautious ``NETWORK``
    default for an unknown name.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        policy: Optional[PolicyEngine] = None,
        *,
        actor: str = "horizon",
    ):
        self.registry = registry
        self.policy = policy or default_engine()
        for name, risk in registry.risks().items():
            self.policy.tool_risks[name] = risk
        self.actor = actor

    # ---------------------------------------------------------------- gate
    def dispatch(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        actor: Optional[str] = None,
        president_authorized: bool = False,
        target: Optional[str] = None,
    ) -> ToolResult:
        """Resolve, gate, validate and run one tool call.

        Raises :class:`UnknownToolError` for an unregistered name. A policy
        denial returns ``ToolResult(ok=False, denied=True)`` — and the executor
        is never entered.
        """
        tool = self.registry.resolve(name)  # unknown -> UnknownToolError
        decision: PolicyDecision = self.policy.check(
            tool.name,
            president_authorized=president_authorized,
            target=target,
            actor=actor or self.actor,
        )
        if not decision.allowed:
            return ToolResult(
                tool=tool.name,
                ok=False,
                denied=True,
                error=decision.reason,
                decision=decision.as_dict(),
                risk=decision.risk.value,
            )
        try:
            kwargs = tool.validate_arguments(arguments)
        except ToolArgumentError as exc:
            return ToolResult(
                tool=tool.name,
                ok=False,
                error=str(exc),
                decision=decision.as_dict(),
                risk=decision.risk.value,
            )
        try:
            raw = tool.executor(**kwargs)
        except ToolError as exc:
            return ToolResult(
                tool=tool.name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                decision=decision.as_dict(),
                risk=decision.risk.value,
            )
        except Exception as exc:  # an executor bug is a failed tool call, not a crash
            return ToolResult(
                tool=tool.name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                decision=decision.as_dict(),
                risk=decision.risk.value,
            )
        if isinstance(raw, ToolResult):
            if not raw.tool:
                raw.tool = tool.name
            raw.decision = raw.decision or decision.as_dict()
            raw.risk = raw.risk or decision.risk.value
            return raw
        return ToolResult(
            tool=tool.name,
            ok=True,
            output=raw,
            decision=decision.as_dict(),
            risk=decision.risk.value,
        )
