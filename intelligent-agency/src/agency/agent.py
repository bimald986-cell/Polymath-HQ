"""An Agent: the worker at the bottom of the hierarchy."""
from __future__ import annotations
from pathlib import Path

from typing import List, Optional

from .base import Node, Role
from .llm import LLMBackend, get_backend
from .portfolio_context import get_portfolio_context


class Agent(Node):
    """A single specialist. Given a task, it answers using the LLM backend."""

    def __init__(
        self,
        name: str,
        description: str = "",
        keywords: Optional[List[str]] = None,
        system_prompt: str = "",
        backend: Optional[LLMBackend] = None,
    ):
        super().__init__(
            name=name,
            role=Role.AGENT,
            description=description,
            keywords=keywords or [],
            system_prompt=system_prompt or f"You are {name}. {description}",
        )
        self._backend = backend

    @property
    def backend(self) -> LLMBackend:
        if self._backend is None:
            self._backend = get_backend()
        return self._backend

    def handle(self, task: str, system_prompt: Optional[str] = None) -> str:
        """Do the work and return the answer.

        ``system_prompt`` replaces this agent's own one-line auto-prompt for this
        turn only. The interactive surfaces (``agency.chat``) pass the persona
        and project-context prompt there, so a chat turn is answered by a routed
        agent -- the same path ``cli.py ask`` takes -- instead of by a second
        transport with a prompt of its own. Nothing else about the turn changes:
        the portfolio context and the evidence policy are appended either way.
        """
        context = get_portfolio_context(task)
        prompt = (system_prompt or self.system_prompt) + "\n\n" + context
        policy_file = (
            Path(__file__).resolve().parents[2]
            / "EVIDENCE_VERIFICATION_POLICY.md"
        )

        if policy_file.is_file():
            policy = policy_file.read_text(encoding="utf-8-sig")
            prompt += (
                "\n\nHQ EVIDENCE VERIFICATION POLICY:\n"
                + policy
            )

        return self.backend.complete(prompt, task)
