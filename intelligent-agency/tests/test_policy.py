"""Tests for the policy skeleton."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.policy import (
    AUDIT_PATH_ENV,
    PolicyAuditSink,
    PolicyEngine,
    ToolRisk,
    default_audit_sink,
    default_engine,
)


def test_read_tools_allowed():
    eng = default_engine()
    d = eng.check("local_file_read")
    assert d.allowed
    assert d.risk == ToolRisk.READ


def test_irreversible_blocked_without_president():
    eng = default_engine()
    d = eng.check("merge_pull_request")
    assert not d.allowed
    assert d.requires_president
    assert d.risk == ToolRisk.IRREVERSIBLE


def test_irreversible_allowed_with_president():
    eng = default_engine()
    d = eng.check("merge_pull_request", president_authorized=True)
    assert d.allowed


def test_network_allowlist():
    eng = default_engine(network_allowlist=["https://api.exchangerate.host"])
    ok = eng.check("http_get_allowlisted", target="https://api.exchangerate.host/latest")
    assert ok.allowed
    blocked = eng.check("http_get_allowlisted", target="https://evil.example/steal")
    assert not blocked.allowed


def test_require_raises():
    eng = default_engine()
    try:
        eng.require("spend_funds")
        assert False, "expected PermissionError"
    except PermissionError as e:
        assert "President" in str(e)


def test_audit_log_records():
    # A default engine shares one process-wide audit trail, so the trail is not
    # reset per call: assert the decision is recorded at the end of it.
    eng = default_engine()
    eng.check("memory_recall", actor="horizon")
    assert eng.audit_log[-1]["tool"] == "memory_recall"
    assert eng.audit_log[-1]["actor"] == "horizon"
    assert eng.audit_sink is default_audit_sink()


def test_isolated_engine_keeps_its_own_audit_log():
    # An explicitly built engine stays isolated unless a sink is injected.
    eng = PolicyEngine()
    eng.check("memory_recall", actor="horizon")
    assert [e["tool"] for e in eng.audit_log] == ["memory_recall"]
    assert eng.audit_sink is not default_audit_sink()


def test_default_engine_decision_survives_the_call_that_made_it():
    """The old bug: default_engine() built a fresh engine per call, so every
    decision was discarded the moment it was made. Now the trail is shared."""
    first = default_engine()
    first.check("memory_recall", actor="horizon")
    # A *different* engine, built after the first call returned, still sees it.
    second = default_engine()
    assert any(e["tool"] == "memory_recall" for e in second.audit_log)


def test_policy_decisions_are_persisted_to_a_greppable_file(tmp_path, monkeypatch):
    audit_path = tmp_path / "policy_audit.jsonl"
    monkeypatch.setenv(AUDIT_PATH_ENV, str(audit_path))

    engine = default_engine()
    engine.check("github_review_changeset", actor="horizon", target="horizon/improve-docs")

    # On disk, readable by anything (a later process included), one JSON per line.
    text = audit_path.read_text(encoding="utf-8")
    assert "github_review_changeset" in text
    persisted = json.loads([l for l in text.splitlines() if l.strip()][-1])
    assert persisted["tool"] == "github_review_changeset"
    assert persisted["target"] == "horizon/improve-docs"

    # And readable back through the sink API rather than by hand.
    sink = default_audit_sink()
    assert sink.path == str(audit_path)
    assert any(e["tool"] == "github_review_changeset" for e in sink.read_persisted())
    assert sink.last(actor="horizon")["tool"] == "github_review_changeset"


def test_audit_sink_without_a_path_stays_in_memory(tmp_path):
    sink = PolicyAuditSink()
    sink.record({"tool": "local_file_read"})
    assert sink.read_persisted() == []
    assert sink.last()["tool"] == "local_file_read"
