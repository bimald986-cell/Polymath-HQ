"""Tool-call policy skeleton for Intelligent Agency / Horizon.

Inspired by multi-layer policy patterns (study fork: automaton) but reimplemented
in Python with no Conway Cloud, wallet, or self-replication dependencies.

Rules:
- Classify every tool by risk level.
- Block irreversible actions unless President-level authorization is present.
- Log decisions with provenance for audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class ToolRisk(str, Enum):
    READ = "read"
    WRITE_LOCAL = "write_local"
    NETWORK = "network"
    IRREVERSIBLE = "irreversible"


# Default risk map for known tools. Unknown tools default to NETWORK (cautious).
DEFAULT_TOOL_RISKS: Dict[str, ToolRisk] = {
    "local_file_read": ToolRisk.READ,
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
    ):
        self.tool_risks = dict(DEFAULT_TOOL_RISKS)
        if tool_risks:
            self.tool_risks.update(tool_risks)
        self.network_allowlist = set(network_allowlist or [])
        self.audit_log: List[Dict[str, Any]] = audit_log if audit_log is not None else []

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
        self.audit_log.append(entry)


def default_engine(network_allowlist: Optional[List[str]] = None) -> PolicyEngine:
    return PolicyEngine(network_allowlist=network_allowlist)
