"""Tool-call policy skeleton for Intelligent Agency / Horizon.

Inspired by multi-layer policy patterns (study fork: automaton) but reimplemented
in Python with no Conway Cloud, wallet, or self-replication dependencies.

Rules:
- Classify every tool by risk level.
- Block irreversible actions unless President-level authorization is present.
- Log decisions with provenance for audit.

Audit durability: every engine writes its decisions to a
:class:`PolicyAuditSink`. ``default_engine()`` hands out a *shared* sink, so a
decision survives the call that produced it, and the sink appends each entry as
a JSON line to ``HORIZON_POLICY_AUDIT_PATH`` when that is configured (the
durable worker sets it next to the queue DB). See ``docs/POLICY_ENGINE.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import os
import time


class ToolRisk(str, Enum):
    READ = "read"
    WRITE_LOCAL = "write_local"
    NETWORK = "network"
    IRREVERSIBLE = "irreversible"


# Default risk map for known tools. Unknown tools default to NETWORK (cautious).
# Implemented ids (see ``builtin_tools.py``, the tool-use channel): ``read_file``
# covers the intended ``local_file_read`` capability, and ``run_tests`` is new.
# Both are also declared by the tool itself: ``ToolDispatcher`` writes a
# registered tool's declared risk into this map, so the tool, not the caller,
# decides how it is classified.
DEFAULT_TOOL_RISKS: Dict[str, ToolRisk] = {
    "local_file_read": ToolRisk.READ,
    "read_file": ToolRisk.READ,
    "run_tests": ToolRisk.WRITE_LOCAL,
    "memory_recall": ToolRisk.READ,
    "memory_remember": ToolRisk.WRITE_LOCAL,
    "enqueue_work": ToolRisk.WRITE_LOCAL,
    "github_review_changeset": ToolRisk.NETWORK,
    "http_get_allowlisted": ToolRisk.NETWORK,
    "http_get_arbitrary": ToolRisk.IRREVERSIBLE,
    "merge_pull_request": ToolRisk.IRREVERSIBLE,
    "push_to_protected_branch": ToolRisk.IRREVERSIBLE,
    "execute_shell": ToolRisk.IRREVERSIBLE,
    "spend_funds": ToolRisk.IRREVERSIBLE,
    "delete_production_data": ToolRisk.IRREVERSIBLE,
}


@dataclass
class PolicyDecision:
    allowed: bool
    tool: str
    risk: ToolRisk
    reason: str
    requires_president: bool = False
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "tool": self.tool,
            "risk": self.risk.value,
            "reason": self.reason,
            "requires_president": self.requires_president,
            "timestamp": self.timestamp,
        }


class PolicyAuditSink:
    """Append-only audit trail for policy decisions.

    An engine writes every decision here. The sink keeps the entries in memory
    *and*, when ``path`` is set, appends each one as a JSON line so the trail
    outlives the process. ``default_engine()`` shares one sink per process, so a
    decision is still readable after the call that produced it returned.
    """

    def __init__(self, path: Optional[str] = None, entries: Optional[List[Dict[str, Any]]] = None):
        self.path = path
        self.entries: List[Dict[str, Any]] = entries if entries is not None else []

    def record(self, entry: Dict[str, Any]) -> None:
        self.entries.append(entry)
        if not self.path:
            return
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def read_persisted(self) -> List[Dict[str, Any]]:
        """Read the durable JSONL trail back (empty when nothing is persisted)."""
        if not self.path or not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def last(self, *, actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        for entry in reversed(self.entries):
            if actor is None or entry.get("actor") == actor:
                return entry
        return None


class PolicyEngine:
    """Minimal multi-layer gate for tool calls.

    Layer 1 — risk classification
    Layer 2 — hard blocks (irreversible without President flag)
    Layer 3 — optional allowlist for network tools
    """

    def __init__(
        self,
        tool_risks: Optional[Dict[str, ToolRisk]] = None,
        network_allowlist: Optional[List[str]] = None,
        audit_log: Optional[List[Dict[str, Any]]] = None,
        audit_sink: Optional[PolicyAuditSink] = None,
    ):
        self.tool_risks = dict(DEFAULT_TOOL_RISKS)
        if tool_risks:
            self.tool_risks.update(tool_risks)
        self.network_allowlist = set(network_allowlist or [])
        if audit_sink is not None:
            self.audit_sink = audit_sink
        else:
            # A private sink by default: an explicitly built engine is isolated
            # unless the caller injects a shared one.
            self.audit_sink = PolicyAuditSink(entries=audit_log)
        # ``audit_log`` stays the engine's view of the trail it writes to.
        self.audit_log: List[Dict[str, Any]] = self.audit_sink.entries

    def classify(self, tool: str) -> ToolRisk:
        return self.tool_risks.get(tool, ToolRisk.NETWORK)

    def check(
        self,
        tool: str,
        *,
        president_authorized: bool = False,
        target: Optional[str] = None,
        actor: str = "horizon",
    ) -> PolicyDecision:
        risk = self.classify(tool)

        # Layer 2 — irreversible requires explicit President authorization
        if risk == ToolRisk.IRREVERSIBLE and not president_authorized:
            decision = PolicyDecision(
                allowed=False,
                tool=tool,
                risk=risk,
                reason="Irreversible action blocked: President authorization required",
                requires_president=True,
            )
            self._log(decision, actor=actor, target=target)
            return decision

        # Layer 3 — network allowlist when configured and target provided
        if risk == ToolRisk.NETWORK and self.network_allowlist and target:
            if not self._target_allowed(target):
                decision = PolicyDecision(
                    allowed=False,
                    tool=tool,
                    risk=risk,
                    reason=f"Target not on network allowlist: {target}",
                    requires_president=False,
                )
                self._log(decision, actor=actor, target=target)
                return decision

        decision = PolicyDecision(
            allowed=True,
            tool=tool,
            risk=risk,
            reason="Allowed by policy",
            requires_president=False,
        )
        self._log(decision, actor=actor, target=target)
        return decision

    def require(self, tool: str, **kwargs: Any) -> PolicyDecision:
        """Like check(), but raises PermissionError when denied."""
        decision = self.check(tool, **kwargs)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return decision

    def _target_allowed(self, target: str) -> bool:
        t = target.lower().strip()
        for allowed in self.network_allowlist:
            a = allowed.lower().strip()
            if t == a or t.startswith(a.rstrip("/") + "/") or a in t:
                return True
        return False

    def _log(self, decision: PolicyDecision, actor: str, target: Optional[str]) -> None:
        entry = decision.as_dict()
        entry["actor"] = actor
        entry["target"] = target
        self.audit_sink.record(entry)


# Shared by every engine ``default_engine()`` hands out, so a decision is still
# there once the call that produced it has returned (and, when a path is
# configured, once the process has exited).
_DEFAULT_AUDIT_SINK: Optional[PolicyAuditSink] = None

# Where the durable trail goes when the environment names it. The durable
# worker defaults it to ``<queue dir>/policy_audit.jsonl`` (see
# ``horizon_worker_main.build_worker``).
AUDIT_PATH_ENV = "HORIZON_POLICY_AUDIT_PATH"


def policy_audit_path() -> Optional[str]:
    """The configured durable audit path, or ``None`` when not configured."""
    return os.getenv(AUDIT_PATH_ENV, "").strip() or None


def default_audit_sink() -> PolicyAuditSink:
    """The process-wide audit sink shared by default engines."""
    global _DEFAULT_AUDIT_SINK
    if _DEFAULT_AUDIT_SINK is None:
        _DEFAULT_AUDIT_SINK = PolicyAuditSink()
    # Re-resolve each call so a launch-time configuration (the worker) is
    # honoured even if an engine was built earlier in the process.
    _DEFAULT_AUDIT_SINK.path = policy_audit_path()
    return _DEFAULT_AUDIT_SINK


def default_engine(network_allowlist: Optional[List[str]] = None) -> PolicyEngine:
    """Build an engine whose audit trail survives the call that wrote it."""
    return PolicyEngine(network_allowlist=network_allowlist, audit_sink=default_audit_sink())
