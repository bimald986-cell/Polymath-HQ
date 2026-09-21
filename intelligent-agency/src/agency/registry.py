"""Lightweight, dependency-free routing engine.

Scores a free-text query against a node's name/description/keywords using
token overlap. Keyword hits are weighted highest, then name, then
description. This lets the President 'find anything related to a field'
without any external service, and works fully offline. If you later install
embeddings you can swap :func:`score` for a semantic version -- the rest of
the code does not change.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .base import Node

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "to", "of", "for", "in", "on", "and", "or", "is",
    "how", "do", "i", "my", "can", "with", "what", "me", "you", "help",
    "need", "want", "please", "about", "this", "that", "it",
}


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def score(query: str, node: Node) -> float:
    """Return a relevance score for ``query`` against ``node``."""
    q = set(tokenize(query))
    if not q:
        return 0.0
    kw = set(tokenize(" ".join(node.keywords)))
    name = set(tokenize(node.name))
    desc = set(tokenize(node.description))

    hits = 0.0
    hits += 3.0 * len(q & kw)     # keyword match: strongest signal
    hits += 2.0 * len(q & name)   # name match
    hits += 1.0 * len(q & desc)   # description match
    return hits / len(q)          # normalise by query length


def rank(query: str, nodes: List[Node]) -> List[Tuple[Node, float]]:
    """Return ``nodes`` sorted by descending score (ties keep input order)."""
    scored = [(n, score(query, n)) for n in nodes]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored
