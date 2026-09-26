"""Horizon: the President's continuous-improvement advisor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .base import Node, Role
from .llm import LLMBackend, get_backend


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


class PresidentAdvisor(Node):
    """Direct advisor to the President with implementation authority on branches."""

    def __init__(
        self,
        name: str = "Horizon",
        description: str = "President Advisor for horizon scanning and continuous improvement.",
        backend: Optional[LLMBackend] = None,
        authority: Optional[Authority] = None,
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

    @property
    def backend(self) -> LLMBackend:
        if self._backend is None:
            self._backend = get_backend()
        return self._backend

    def advise(self, topic: str) -> str:
        return self.backend.complete(self.system_prompt, topic)

    def permissions(self) -> Dict[str, bool]:
        return dict(self.authority.__dict__)

    def can(self, action: str) -> bool:
        return bool(self.permissions().get(action, False))

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
