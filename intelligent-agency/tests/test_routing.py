"""Tests for the routing engine and the org hierarchy."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import build_agency
from agency.registry import score
from agency.base import Node, Role


def _pres():
    return build_agency()


def test_agency_builds():
    p = _pres()
    assert len(p.directors) >= 10
    assert all(len(d.agents) >= 1 for d in p.directors)


def test_score_prefers_keyword_hits():
    node = Node(name="Finance", role=Role.DIRECTOR,
                description="money stuff", keywords=["tax", "budget"])
    assert score("help me with my tax", node) > score("paint a picture", node)


def test_routes_agriculture():
    p = _pres()
    d = p.best_director("how do I fertilise my tomato crop")
    assert d.name == "Agriculture"


def test_routes_coding():
    p = _pres()
    d = p.best_director("debug this python api returning 500 errors")
    assert d.name == "Coding"


def test_routes_shares():
    p = _pres()
    d = p.best_director("should I buy this stock share on the market")
    assert d.name == "Shares & Trading"


def test_handle_returns_trace():
    p = _pres()
    res = p.handle("write a lesson plan about fractions")
    assert res["director"] == "Education"
    assert res["agent"]
    assert res["answer"]


def test_find_directors_ranked():
    p = _pres()
    top = p.find_directors("marketing campaign", top_k=3)
    assert top[0][0].name == "Marketing"
