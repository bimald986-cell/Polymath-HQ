"""The President: the single top-level overseer of all directors."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import Node, Role
from .director import Director
from .registry import rank


class President(Node):
    """Oversees every director and dispatches each request to the right field."""

    def __init__(
        self,
        name: str = "President",
        description: str = "Oversees all directors and their teams.",
        directors: Optional[List[Director]] = None,
    ):
        super().__init__(
            name=name,
            role=Role.PRESIDENT,
            description=description,
            keywords=[],
            system_prompt=f"You are {name}, overseeing all directors.",
        )
        self.directors: List[Director] = directors or []

    def add_director(self, director: Director) -> None:
        self.directors.append(director)

    def find_directors(self, query: str, top_k: int = 3):
        """Return the top-k directors most related to a field/query, with scores."""
        ranked = rank(query, self.directors)
        return [(d, s) for d, s in ranked[:top_k]]

    def best_director(self, query: str) -> Optional[Director]:
        if not self.directors:
            return None
        director, top_score = rank(query, self.directors)[0]
        return director if top_score > 0 else self.directors[0]

    def handle(self, query: str) -> Dict[str, str]:
        """Route a request down the hierarchy and return a full trace."""
        director = self.best_director(query)
        if director is None:
            return {
                "president": self.name,
                "director": "(none)",
                "agent": "(none)",
                "answer": "No directors are configured yet.",
            }
        result = director.handle(query)
        result["president"] = self.name
        return result

    def tree(self) -> str:
        """Human-readable org chart."""
        lines = [f"President: {self.name}"]
        for d in self.directors:
            lines.append(f"  Director: {d.name} -- {d.description}")
            for a in d.agents:
                lines.append(f"      Agent: {a.name} -- {a.description}")
        return "\n".join(lines)
