"""Tests for the policy skeleton."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.policy import PolicyEngine, ToolRisk, default_engine


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
    eng = default_engine()
    eng.check("memory_recall", actor="horizon")
    assert len(eng.audit_log) == 1
    assert eng.audit_log[0]["tool"] == "memory_recall"
