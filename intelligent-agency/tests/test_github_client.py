"""Tests for the real GitHub transport (agency.github_client).

No network: the client's ``transport`` is injected, and an autouse fixture makes
any accidental ``urllib.request.urlopen`` an immediate test failure.
"""
import base64
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.github_client import GitHubAuthError, GitHubClient, GitHubError  # noqa: E402
from fake_github import FakeTransport  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a test attempted a real HTTP call")

    monkeypatch.setattr(urllib.request, "urlopen", boom)


def make_client(transport=None, repo="owner/repo", token="test-token", **kwargs):
    return GitHubClient(repo=repo, token=token, transport=transport or FakeTransport(), **kwargs)


# --------------------------------------------------------------------- auth
def test_missing_token_fails_loudly_and_specifically(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(GitHubAuthError) as excinfo:
        GitHubClient(repo="owner/repo", token="")
    assert "GITHUB_TOKEN" in str(excinfo.value)


def test_missing_repo_is_reported_clearly(monkeypatch):
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    with pytest.raises(GitHubAuthError) as excinfo:
        GitHubClient(repo="", token="test-token")
    assert "GITHUB_REPO" in str(excinfo.value)


def test_from_env_reads_token_and_repo(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/from-env")
    client = GitHubClient.from_env(transport=FakeTransport())
    assert client.repo == "owner/from-env"
    assert client.token == "env-token"


def test_bad_repo_slug_rejected():
    with pytest.raises(ValueError):
        GitHubClient(repo="not-a-slug", token="test-token", transport=FakeTransport())


# ------------------------------------------------------- the delivered flow
def test_branch_file_and_pull_request_round_trip():
    transport = FakeTransport()
    client = make_client(transport)

    client.create_branch("horizon/real-transport", from_branch="main")
    client.put_file("horizon/real-transport", "docs/note.md", "# hi\n", "horizon: add note")
    pr = client.open_pull_request("President Brief: add note", "horizon/real-transport", "main", "body")

    assert transport.branches["horizon/real-transport"] == "base-sha-0001"
    assert transport.files[("horizon/real-transport", "docs/note.md")]
    assert pr["number"] == 7 and pr["html_url"].endswith("/pull/7")
    assert transport.methods() == ["GET", "GET", "POST", "GET", "PUT", "POST"]
    assert transport.paths()[2].endswith("/git/refs")
    assert transport.paths()[4].endswith("/contents/docs/note.md")
    assert transport.paths()[5].endswith("/pulls")


def test_file_content_is_sent_base64_encoded():
    transport = FakeTransport()
    client = make_client(transport)
    client.put_file("horizon/enc", "a.txt", "hello world", "m")
    sent = transport.calls[1]["body"]
    assert base64.b64decode(sent["content"]).decode() == "hello world"
    assert sent["branch"] == "horizon/enc"


def test_existing_file_is_updated_with_its_sha():
    transport = FakeTransport(branches={"main": "s0"}, files={("horizon/up", "a.txt"): "sha-old"})
    client = make_client(transport)
    client.put_file("horizon/up", "a.txt", "new", "m")
    assert transport.calls[-1]["body"]["sha"] == "sha-old"


def test_create_branch_is_idempotent():
    transport = FakeTransport(branches={"main": "s0", "horizon/exists": "s9"})
    client = make_client(transport)
    client.create_branch("horizon/exists")
    assert transport.methods() == ["GET"]  # no POST


def test_missing_base_branch_is_loud():
    client = make_client(FakeTransport(branches={}))
    with pytest.raises(GitHubError) as excinfo:
        client.create_branch("horizon/x", from_branch="main")
    assert "main" in str(excinfo.value)


def test_http_failure_surfaces_status_and_body():
    transport = FakeTransport(forced_status={r"/pulls$": ("POST", 403, b'{"message":"forbidden"}')})
    client = make_client(transport)
    with pytest.raises(GitHubError) as excinfo:
        client.open_pull_request("t", "horizon/x", "main", "b")
    assert excinfo.value.status == 403
    assert "forbidden" in str(excinfo.value)


# ------------------------------------------------------------- hard refusals
def test_merge_is_impossible_and_never_reaches_the_network():
    transport = FakeTransport()
    client = make_client(transport)
    with pytest.raises(PermissionError) as excinfo:
        client.merge_pull_request(7)
    assert "merge" in str(excinfo.value).lower()
    assert transport.calls == []


@pytest.mark.parametrize("branch", ["main", "master", "production", "release"])
def test_protected_branches_are_never_written(branch):
    transport = FakeTransport(branches={"main": "s0", "master": "s0", "production": "s0", "release": "s0"})
    client = make_client(transport)
    with pytest.raises(PermissionError):
        client.create_branch(branch)
    with pytest.raises(PermissionError):
        client.put_file(branch, "a.txt", "x", "m")
    with pytest.raises(PermissionError):
        client.open_pull_request("t", branch, "main", "b")
    assert transport.calls == []


def test_non_review_branches_are_refused():
    client = make_client()
    with pytest.raises(PermissionError) as excinfo:
        client.put_file("feature/sneaky", "a.txt", "x", "m")
    assert "review branches" in str(excinfo.value)


def test_branch_prefix_is_configurable_but_defaults_to_horizon():
    client = make_client()
    assert client.branch_prefix == "horizon/"
    custom = make_client(transport=FakeTransport(), branch_prefix="agent/")
    custom.create_branch("agent/x")
    with pytest.raises(PermissionError):
        custom.create_branch("horizon/x")


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".github/workflows/release/deploy.yml",
        ".git/config",
        ".env",
        "config/secrets.yaml",
        "keys/private_key.pem",
        "deploy/credentials.json",
    ],
)
def test_workflow_and_secret_paths_are_refused(path):
    transport = FakeTransport()
    client = make_client(transport)
    with pytest.raises(PermissionError):
        client.put_file("horizon/x", path, "x", "m")
    assert transport.calls == []


def test_path_traversal_and_empty_paths_rejected():
    client = make_client()
    with pytest.raises(ValueError):
        client.put_file("horizon/x", "../../etc/passwd", "x", "m")
    with pytest.raises(ValueError):
        client.put_file("horizon/x", "", "x", "m")


def test_oversized_file_is_refused_before_the_request():
    transport = FakeTransport()
    client = make_client(transport)
    with pytest.raises(ValueError):
        client.put_file("horizon/big", "big.txt", "x" * 800_000, "m")
    assert transport.calls == []


def test_pr_into_its_own_head_is_refused():
    client = make_client()
    with pytest.raises(PermissionError):
        client.open_pull_request("t", "horizon/same", "horizon/same", "b")
