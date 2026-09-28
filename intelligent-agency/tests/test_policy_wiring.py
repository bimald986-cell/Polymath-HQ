"""Integration tests: PolicyEngine wired into GitHub guard and Horizon advisor."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.github_worker import FileChange, GitHubGuard, ReviewChangeSet
from agency.advisor import PresidentAdvisor, Authority
from agency.policy import PolicyEngine, default_engine


def test_guard_allows_horizon_branch_with_policy():
    GitHubGuard.validate(
        ReviewChangeSet(
            "t",
            "horizon/improve-x",
            "s",
            [FileChange("src/x.py", "x=1", "m")],
        )
    )


def test_guard_blocks_main_via_policy_and_path_rules():
    with pytest.raises(PermissionError):
        GitHubGuard.validate(ReviewChangeSet("t", "main", "s"))


def test_guard_deny_merge_without_president():
    with pytest.raises(PermissionError):
        GitHubGuard.deny_merge()


def test_guard_deny_merge_with_president_flag():
    # Policy allows the tool when president_authorized=True;
    # product still must not auto-merge — this only tests the policy gate.
    GitHubGuard.deny_merge(president_authorized=True)


def test_advisor_cannot_merge_by_default():
    h = PresidentAdvisor()
    assert h.can("merge_pull_request") is False
    with pytest.raises(PermissionError):
        h.require_action("merge_pull_request")


def test_advisor_can_open_pr():
    h = PresidentAdvisor()
    assert h.can("open_pull_request") is True
    h.require_action("open_pull_request", target="horizon/x")


def test_shared_policy_audit_log():
    eng = default_engine()
    h = PresidentAdvisor(policy=eng)
    h.can("inspect")
    h.can("merge_pull_request")
    tools = [e["tool"] for e in eng.audit_log]
    assert "local_file_read" in tools
    assert "merge_pull_request" in tools
