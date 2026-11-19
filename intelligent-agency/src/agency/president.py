"""The President: top-level overseer of directors with a direct advisor."""
from __future__ import annotations

from typing import Dict, List, Optional

from .advisor import PresidentAdvisor
from .base import Node, Role
from .director import Director
from .registry import rank


class President(Node):
    """Oversees directors and works directly with the President Advisor."""

    def __init__(
        self,
        name: str = "President",
        description: str = "Oversees all directors and their teams.",
        directors: Optional[List[Director]] = None,
        advisor: Optional[PresidentAdvisor] = None,
    ):
        super().__init__(
            name=name,
            role=Role.PRESIDENT,
            description=description,
            keywords=[],
            system_prompt=f"You are {name}, overseeing all directors and the President Advisor.",
        )
        self.directors: List[Director] = directors or []
        self.advisor = advisor

    def set_advisor(self, advisor: PresidentAdvisor) -> None:
        self.advisor = advisor

    def ask_advisor(self, topic: str, system_prompt: Optional[str] = None) -> str:
        if self.advisor is None:
            return "No President Advisor is configured."
        return self.advisor.advise(topic, system_prompt=system_prompt)

    def add_director(self, director: Director) -> None:
        self.directors.append(director)

    def find_directors(self, query: str, top_k: int = 3):
        ranked = rank(query, self.directors)
        return [(d, s) for d, s in ranked[:top_k]]

    def best_director(self, query: str) -> Optional[Director]:
        if not self.directors:
            return None
        director, top_score = rank(query, self.directors)[0]
        return director if top_score > 0 else self.directors[0]

    def route(self, query: str):
        """Pick ``(director, agent)`` for ``query`` without calling a model.

        This is the whole routing decision ``handle`` makes, exposed on its own so
        an interactive surface can find out *which* agent answered -- and read
        that agent's backend afterwards -- without duplicating the ranking rule
        or paying for a second model call.
        """
        director = self.best_director(query)
        if director is None:
            return None, None
        return director, director.best_agent(query)

    def handle(self, query: str, system_prompt: Optional[str] = None) -> Dict[str, str]:
        director, agent = self.route(query)
        if director is None:
            return {
                "president": self.name,
                "director": "(none)",
                "agent": "(none)",
                "answer": "No directors are configured yet.",
            }
        if agent is None:
            return {
                "president": self.name,
                "director": director.name,
                "agent": "(none)",
                "answer": f"The {director.name} team has no agents yet.",
            }
        return {
            "president": self.name,
            "director": director.name,
            "agent": agent.name,
            "answer": agent.handle(query, system_prompt=system_prompt),
        }

    def tree(self) -> str:
        lines = [f"President: {self.name}"]
        if self.advisor is not None:
            lines.append(f"  President Advisor: {self.advisor.name} -- {self.advisor.description}")
        for d in self.directors:
            lines.append(f"  Director: {d.name} -- {d.description}")
            for a in d.agents:
                lines.append(f"      Agent: {a.name} -- {a.description}")
        return "\n".join(lines)
