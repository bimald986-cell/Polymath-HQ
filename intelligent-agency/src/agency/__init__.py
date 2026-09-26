"""Intelligent Agency: President + Horizon -> Directors -> Agents."""
from .base import Role, Node
from .agent import Agent
from .advisor import Authority, PresidentAdvisor
from .director import Director
from .president import President
from .registry import score, rank
from .loader import build_agency, load_config
from .llm import get_backend, LLMBackend, MockBackend, OpenAICompatibleBackend

__all__ = [
    "Role", "Node", "Agent", "Authority", "PresidentAdvisor", "Director", "President",
    "score", "rank", "build_agency", "load_config",
    "get_backend", "LLMBackend", "MockBackend", "OpenAICompatibleBackend",
]
__version__ = "0.2.0"
