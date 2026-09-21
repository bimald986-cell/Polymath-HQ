"""Core roles and the shared Node base class for every actor in the agency."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Role(str, Enum):
    """Where an actor sits in the org chart."""
    PRESIDENT = "president"
    DIRECTOR = "director"
    AGENT = "agent"


@dataclass
class Node:
    """Base class shared by President, Director and Agent.

    ``keywords`` power the routing engine: a query is matched against the
    name, description and keywords of every node to decide who should handle
    it. ``system_prompt`` is the persona/instructions handed to the LLM.
    """
    name: str
    role: Role
    description: str = ""
    keywords: List[str] = field(default_factory=list)
    system_prompt: str = ""

    def match_text(self) -> str:
        """All the text used when scoring this node against a query."""
        return " ".join([self.name, self.description, " ".join(self.keywords)])

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{self.role.value}:{self.name}>"
