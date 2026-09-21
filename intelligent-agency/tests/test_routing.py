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
    assert len(p.directors) >= 25
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


def test_routes_healthcare():
    p = _pres()
    d = p.best_director("what does this symptom and diagnosis usually mean")
    assert d.name == "Healthcare"


def test_routes_legal():
    p = _pres()
    d = p.best_director("review this NDA contract clause for compliance")
    assert d.name == "Legal"


def test_routes_ai():
    p = _pres()
    d = p.best_director("design a RAG pipeline with an llm agent")
    assert d.name == "AI & Intelligence"


def test_routes_cybersecurity():
    p = _pres()
    d = p.best_director("phishing malware vulnerability encryption")
    assert d.name == "Cybersecurity"


def test_routes_data_analytics():
    p = _pres()
    d = p.best_director("build an etl warehouse dashboard metric")
    assert d.name == "Data & Analytics"


def test_routes_engineering():
    p = _pres()
    d = p.best_director("structural load beam foundation civil engineering")
    assert d.name == "Engineering"


def test_routes_environment():
    p = _pres()
    d = p.best_director("climate carbon emissions sustainability")
    assert d.name == "Environment & Climate"


def test_routes_government():
    p = _pres()
    d = p.best_director("public policy legislation governance ministry")
    assert d.name == "Government & Policy"


def test_routes_real_estate():
    p = _pres()
    d = p.best_director("property lease rent tenant valuation")
    assert d.name == "Real Estate"


def test_routes_media():
    p = _pres()
    d = p.best_director("journalism news reporter editor article")
    assert d.name == "Media & Journalism"


def test_routes_languages():
    p = _pres()
    d = p.best_director("translation grammar vocabulary localization")
    assert d.name == "Languages & Translation"


def test_routes_psychology():
    p = _pres()
    d = p.best_director("psychology cognition behaviour motivation bias")
    assert d.name == "Psychology"


def test_routes_philosophy():
    p = _pres()
    d = p.best_director("philosophy ethics moral logic epistemology")
    assert d.name == "Philosophy & Ethics"


def test_routes_career_services():
    p = _pres()
    d = p.best_director("rewrite my resume cv linkedin interview job search")
    assert d.name == "Career Services"


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
