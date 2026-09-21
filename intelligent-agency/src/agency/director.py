"""A Director: owns one domain and a team of agents."""
from __future__ import annotations

from typing import Dict, List, Optional

from .agent import Agent
from .base import Node, Role
from .registry import rank


class Director(Node):
    """Leads a single field (e.g. finance) and routes tasks to its agents."""

    def __init__(
        self,
        name: str,
        description: str = "",
        keywords: Optional[List[str]] = None,
        system_prompt: str = "",
        agents: Optional[List[Agent]] = None,
    ):
        super().__init__(
            name=name,
            role=Role.DIRECTOR,
            description=description,
            keywords=keywords or [],
            system_prompt=system_prompt or f"You are the {name} director.",
        )
        self.agents: List[Agent] = agents or []

    def add_agent(self, agent: Agent) -> None:
        self.agents.append(agent)

    def best_agent(self, task: str) -> Optional[Agent]:
        if not self.agents:
            return None
        ranked = rank(task, self.agents)
        top_agent, top_score = ranked[0]
        return top_agent if top_score > 0 else self.agents[0]

    def handle(self, task: str) -> Dict[str, str]:
        """Delegate the task to the most relevant agent."""
        agent = self.best_agent(task)
        if agent is None:
            return {
                "director": self.name,
                "agent": "(none)",
                "answer": f"The {self.name} team has no agents yet.",
            }
        return {
            "director": self.name,
            "agent": agent.name,
            "answer": agent.handle(task),
        }
