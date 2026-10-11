"""Tests for GitHubPublisher: a validated change-set becomes a branch + PR.

Network is mocked via ``FakeTransport``; an autouse fixture fails any test that
tries a real HTTP call.
"""
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.github_client import GitHubClient  # noqa: E402
from agency.github_worker import (  # noqa: E402
    FileChange,
    GitHubGuard,
    GitHubPublisher,
    ReviewChangeSet,
    changeset_from_payload,
)
from agency.policy import default_engine  # noqa: E402
from fake_github import FakeTransport  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a test attempted a real HTTP call")

    monkeypatch.setattr(urllib.request, "urlopen", boom)


def build(transport=None, **kwargs):
    transport = transport or FakeTransport()
    client = GitHubClient(repo="owner/repo", token="test-token", transport=transport, **kwargs)
    return GitHubPublisher(client, **{"policy": default_engine()}), transport


def sample_change(branch="horizon/improve-docs"):
    return ReviewChangeSet(
        title="President Brief: tighten docs",
        branch=branch,
        summary="Docs drifted from the code.",
        files=[
            FileChange("docs/a.md", "# A\n", "horizon: update docs/a.md"),
            FileChange("docs/b.md", "# B\n", "horizon: update docs/b.md"),
        ],
        tests=["pytest -q"],
        risks=["None identified."],
    )


def test_publish_creates_branch_writes_files_and_opens_pr():
    publisher, transport = build()
    result = publisher.publish(sample_change())

    assert result.branch == "horizon/improve-docs"
    assert result.files == ["docs/a.md", "docs/b.md"]
    assert result.pr_url.endswith("/pull/7")
    assert result.pr_number == 7
    assert transport.branches["horizon/improve-docs"] == "base-sha-0001"
    assert set(transport.files) == {
        ("horizon/improve-docs", "docs/a.md"),
        ("horizon/improve-docs", "docs/b.md"),
    }

    pr = transport.pull_requests[0]
    assert pr["head"] == "horizon/improve-docs"
    assert pr["base"] == "main"
    assert "## President Brief" in pr["body"]
    assert "docs/a.md" in pr["body"]
    assert "Merge only if you approve." in pr["body"]


def test_publish_never_merges():
    publisher, transport = build()
    publisher.publish(sample_change())
    assert transport.merge_attempts == 0
    assert not any("merge" in call["path"] for call in transport.calls)
    with pytest.raises(PermissionError):
        publisher.client.merge_pull_request(7)


def test_publish_uses_configured_base_branch():
    transport = FakeTransport(branches={"develop": "dev-sha"})
    client = GitHubClient(repo="owner/repo", token="t", transport=transport)
    publisher = GitHubPublisher(client, base_branch="develop")
    publisher.publish(sample_change())
    assert transport.branches["horizon/improve-docs"] == "dev-sha"
    assert transport.pull_requests[0]["base"] == "develop"


def test_publish_refuses_protected_branch_before_any_request():
    publisher, transport = build()
    with pytest.raises(PermissionError):
        publisher.publish(sample_change(branch="main"))
    assert transport.calls == []


def test_publish_refuses_workflow_files_before_any_request():
    publisher, transport = build()
    change = ReviewChangeSet(
        "t",
        "horizon/x",
        "s",
        [FileChange(".github/workflows/ci.yml", "on: push\n", "m")],
    )
    with pytest.raises(PermissionError):
        publisher.publish(change)
    assert transport.calls == []


def test_publish_refuses_empty_changeset():
    publisher, transport = build()
    with pytest.raises(ValueError):
        publisher.publish(ReviewChangeSet("t", "horizon/empty", "s", []))
    assert transport.calls == []


def test_policy_allowlist_denial_blocks_publish():
    transport = FakeTransport()
    client = GitHubClient(repo="owner/repo", token="t", transport=transport)
    publisher = GitHubPublisher(client, policy=default_engine(network_allowlist=["github.com"]))
    with pytest.raises(PermissionError) as excinfo:
        publisher.publish(sample_change())
    assert "allowlist" in str(excinfo.value)
    assert transport.calls == []


def test_policy_decision_is_audited():
    engine = default_engine()
    transport = FakeTransport()
    client = GitHubClient(repo="owner/repo", token="t", transport=transport)
    GitHubPublisher(client, policy=engine).publish(sample_change())
    assert [entry["tool"] for entry in engine.audit_log] == ["github_review_changeset"]
    assert engine.audit_log[0]["allowed"] is True
    assert engine.audit_log[0]["target"] == "horizon/improve-docs"


def test_publisher_requires_a_client():
    with pytest.raises(ValueError):
        GitHubPublisher(None)


def test_changeset_from_explicit_payload():
    change = changeset_from_payload(
        {
            "title": "T",
            "branch": "horizon/from-payload",
            "summary": "S",
            "files": [{"path": "src/x.py", "content": "x=1", "message": "m"}],
            "tests": ["pytest -q"],
            "risks": ["low"],
        }
    )
    assert change.branch == "horizon/from-payload"
    assert change.files[0].path == "src/x.py"
    assert change.tests == ["pytest -q"]


def test_changeset_from_dashboard_command_payload():
    change = changeset_from_payload({"task": "Tighten the docs", "id": 4})
    assert change.branch == "horizon/proposal-4"
    assert change.files[0].path == "docs/horizon-proposals.md"
    assert "Tighten the docs" in change.files[0].content


def test_changeset_from_payload_applies_the_guard():
    with pytest.raises(PermissionError):
        changeset_from_payload({"task": "x", "branch": "main"})
    with pytest.raises(ValueError):
        changeset_from_payload({"nothing": "here"})


def test_publish_payload_end_to_end():
    publisher, transport = build()
    result = publisher.publish_payload({"task": "Do the thing", "id": 12})
    assert result.branch == "horizon/proposal-12"
    assert transport.pull_requests[0]["title"] == "Horizon proposal"
    assert "Do the thing" in transport.pull_requests[0]["body"]


def test_president_brief_body_still_comes_from_the_existing_guard():
    change = sample_change()
    body = GitHubGuard.president_brief(change)
    publisher, transport = build()
    publisher.publish(change)
    assert transport.pull_requests[0]["body"] == body
