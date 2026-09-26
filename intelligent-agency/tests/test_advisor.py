"""Tests for Horizon President Advisor."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import PresidentAdvisor, Role, build_agency


def test_horizon_is_wired_directly_to_president():
    p = build_agency()
    assert isinstance(p.advisor, PresidentAdvisor)
    assert p.advisor.name == "Horizon"
    assert p.advisor.role == Role.PRESIDENT_ADVISOR
    assert "President Advisor: Horizon" in p.tree()


def test_horizon_can_implement_but_not_merge():
    h = PresidentAdvisor()
    assert h.can("create_branch")
    assert h.can("create_files")
    assert h.can("modify_files")
    assert h.can("run_tests")
    assert h.can("open_pull_request")
    assert h.can("update_pull_request")
    assert not h.can("merge_pull_request")
    assert not h.can("push_directly_to_protected_branch")


def test_president_brief_is_easy_to_review():
    h = PresidentAdvisor()
    brief = h.president_brief(
        title="Example improvement",
        summary="Reduces repeated work.",
        changes=["Added reusable workflow"],
        tests=["pytest passed"],
        risks=["Small configuration change"],
        rollback="Revert the pull request.",
    )
    assert "President Brief" in brief
    assert "What changed" in brief
    assert "Verification" in brief
    assert "Risks / trade-offs" in brief
    assert "Decision requested" in brief
