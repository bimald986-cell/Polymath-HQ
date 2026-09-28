"""Horizon: the President's continuous-improvement advisor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .base import Node, Role
from .llm import LLMBackend, get_backend
from .policy import PolicyEngine, default_engine


@dataclass(frozen=True)
class Authority:
    """Repository authority granted to Horizon.

    Horizon may prepare and implement changes on non-protected branches and
    open/update pull requests. Merging remains a human President decision.
    """
    inspect: bool = True
    research: bool = True
    create_branch: bool = True
    create_files: bool = True
    modify_files: bool = True
    delete_files_on_work_branch: bool = True
    run_tests: bool = True
    open_pull_request: bool = True
    update_pull_request: bool = True
    merge_pull_request: bool = False
    push_directly_to_protected_branch: bool = False
    deploy_production: bool = False
    financial_execution: bool = False
    change_credentials_or_security_policy: bool = False


# Map Authority fields / action names onto PolicyEngine tool ids.
_ACTION_TO_TOOL = {
    "merge_pull_request": "merge_pull_request",
    "push_directly_to_protected_branch": "push_to_protected_branch",
    "deploy_production": "delete_production_data",  # treated as irreversible
    "financial_execution": "spend_funds",
    "change_credentials_or_security_policy": "execute_shell",
    "open_pull_request": "github_review_changeset",
    "update_pull_request": "github_review_changeset",
    "create_branch": "github_review_changeset",
    "create_files": "github_review_changeset",
    "modify_files": "github_review_changeset",
    "delete_files_on_work_branch": "github_review_changeset",
    "inspect": "local_file_read",
    "research": "http_get_allowlisted",
    "run_tests": "local_file_read",
}


class PresidentAdvisor(Node):
    """Direct advisor to the President with implementation authority on branches."""

    def __init__(
        self,
        name: str = "Horizon",
        description: str = "President Advisor for horizon scanning and continuous improvement.",
        backend: Optional[LLMBackend] = None,
        authority: Optional[Authority] = None,
        policy: Optional[PolicyEngine] = None,
    ):
        prompt = (
            f"You are {name}, President Advisor of Polymath HQ. "
            "Continuously look for evidence-backed ways to improve HQ. Challenge assumptions, "
            "study relevant advances, connect lessons across projects, and implement worthwhile "
            "changes on review branches. Never merge your own pull requests. Every proposed merge "
            "must include a short President Brief explaining what changed, why, evidence/tests, "
            "risk, rollback, and the decision requested. Distinguish facts, inference and uncertainty."
        )
        super().__init__(
            name=name,
            role=Role.PRESIDENT_ADVISOR,
            description=description,
            keywords=["improve", "research", "future", "horizon", "capability", "innovation", "audit"],
            system_prompt=prompt,
        )
        self._backend = backend
        self.authority = authority or Authority()
        self.policy = policy or default_engine()

    @property
    def backend(self) -> LLMBackend:
        if self._backend is None:
            self._backend = get_backend()
        return self._backend

    def advise(self, topic: str) -> str:
        return self.backend.complete(self.system_prompt, topic)

    def permissions(self) -> Dict[str, bool]:
        return dict(self.authority.__dict__)

    def can(self, action: str, *,
            president_authorized: bool = False,
            target: Optional[str] = None) -> bool:
        """Authority flag AND PolicyEngine must both allow the action."""
        if not bool(self.permissions().get(action, False)):
            return False
        tool = _ACTION_TO_TOOL.get(action)
        if tool is None:
            return True
        decision = self.policy.check(
            tool,
            president_authorized=president_authorized,
            target=target,
            actor=self.name,
        )
        return decision.allowed

    def require_action(self, action: str, *,
                       president_authorized: bool = False,
                       target: Optional[str] = None) -> None:
        """Raise PermissionError if Authority or PolicyEngine denies."""
        if not bool(self.permissions().get(action, False)):
            raise PermissionError(f"Authority denied: {action}")
        tool = _ACTION_TO_TOOL.get(action)
        if tool is None:
            return
        self.policy.require(
            tool,
            president_authorized=president_authorized,
            target=target,
            actor=self.name,
        )

    def president_brief(
        self,
        title: str,
        summary: str,
        changes: List[str],
        tests: List[str],
        risks: List[str],
        rollback: str,
    ) -> str:
        """Generate the standard short brief attached to Horizon's merge requests."""
        bullets = lambda items: "\n".join(f"- {item}" for item in items) or "- None"
        return (
            f"## President Brief: {title}\n\n"
            f"**Why this matters:** {summary}\n\n"
            f"### What changed\n{bullets(changes)}\n\n"
            f"### Verification\n{bullets(tests)}\n\n"
            f"### Risks / trade-offs\n{bullets(risks)}\n\n"
            f"### Rollback\n{rollback}\n\n"
            "### Decision requested\nReview the evidence and changes. Merge only if you approve.\n"
        )
