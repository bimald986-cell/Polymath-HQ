"""``--project NAME`` must make a registered project select the repository.

The defect this guards
----------------------
``horizon_worker_main.py`` could only publish to a repository passed as
``--repo``/``GITHUB_REPO``. ``core/projects.yaml`` registered Mind & Mythos, and
that registration changed nothing about where a run could write
(``HQ_AUDIT_03_PROJECT_FLOW.md`` §2: "a registered project does nothing at
runtime").

What is asserted here
---------------------
1. ``--project`` takes the repository **and** the default branch from the
   registry entry, proven against ``bimald986-cell/Polymath-HQ`` — a real,
   registered repository. The unreachable ``mind-mythos`` entry is never used as
   a fixture.
2. An explicit ``--repo`` still wins, but two disagreeing flags are refused
   rather than resolved silently; the same goes for a contradicting
   ``GITHUB_REPO`` environment variable.
3. An unknown ``--project`` refuses **before any network call**, naming the
   project and the registry file. ``urllib.request.urlopen`` is patched to raise,
   so a run that reached the network would fail with an assertion, not exit 2.
4. A registry capsule that is missing is reported in the run summary instead of
   being skipped silently.
5. With neither flag, behaviour is unchanged: the summary keeps its exact old
   shape and ``GITHUB_REPO`` still decides.

Hermetic: no real network, no ``gh``, no GitHub token beyond a placeholder
string, and every write goes to a temporary database.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import projects as projects_module  # noqa: E402
from agency.horizon_worker_main import (  # noqa: E402
    build_publisher,
    main,
    resolve_publish_target,
)
from agency.projects import ProjectError, UnknownProjectError  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_REGISTRY = REPO_ROOT / "core" / "projects.yaml"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Any HTTP call in these tests is a bug, so make one fail loudly."""

    def boom(*args, **kwargs):
        raise AssertionError("a test attempted a real HTTP call")

    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.fixture(autouse=True)
def clean_github_env(monkeypatch):
    """Neither a real token nor a stray target may leak into a test."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.delenv(projects_module.PROJECTS_ENV, raising=False)


def write_registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "projects.yaml"
    path.write_text(body, encoding="utf-8")
    return path


# ------------------------------------------------------ the resolver helper
def test_project_selects_repository_and_branch_from_the_registry():
    project, repo, branch = resolve_publish_target("polymath-hq")
    assert project is not None and project.id == "polymath-hq"
    assert repo == "bimald986-cell/Polymath-HQ"
    assert branch == "main"


def test_project_can_be_named_by_alias():
    project, repo, _ = resolve_publish_target("Polymath")
    assert project is not None and repo == "bimald986-cell/Polymath-HQ"


def test_no_flags_keeps_the_old_behaviour():
    assert resolve_publish_target() == (None, None, "main")
    assert resolve_publish_target(None, "owner/explicit") == (None, "owner/explicit", "main")


def test_agreeing_repo_and_project_are_accepted():
    _, repo, branch = resolve_publish_target("polymath-hq", "bimald986-cell/Polymath-HQ")
    assert repo == "bimald986-cell/Polymath-HQ"
    # GitHub repository names are case-insensitive, so a case variant agrees too.
    _, repo, _ = resolve_publish_target("polymath-hq", "Bimald986-Cell/polymath-hq")
    assert repo == "bimald986-cell/Polymath-HQ"


def test_disagreeing_repo_and_project_are_an_error_not_a_pick():
    with pytest.raises(ProjectError) as excinfo:
        resolve_publish_target("polymath-hq", "owner/somewhere-else")
    message = str(excinfo.value)
    assert "owner/somewhere-else" in message
    assert "bimald986-cell/Polymath-HQ" in message
    assert "contradicts" in message


def test_unknown_project_raises_before_anything_else():
    with pytest.raises(UnknownProjectError):
        resolve_publish_target("project-that-is-not-registered")


# ------------------------------------------------------------- the CLI path
def _run(tmp_path, *args):
    return main(["--once", "--allow-mock-llm", "--db", str(tmp_path / "q.db"), *args])


def test_main_publishes_to_the_registry_repository(tmp_path, capsys, monkeypatch):
    """The wiring proof: --project names a real registered repository."""
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")
    rc = _run(tmp_path, "--publish-github", "--project", "polymath-hq")
    captured = capsys.readouterr()

    assert rc == 0
    assert "GitHub publishing enabled for bimald986-cell/Polymath-HQ" in captured.out
    assert "on base branch main" in captured.out
    assert "Project polymath-hq -> bimald986-cell/Polymath-HQ" in captured.out

    summary = json.loads(captured.out.strip().splitlines()[-1])
    assert summary["project"] == {
        "id": "polymath-hq",
        "repo": "bimald986-cell/Polymath-HQ",
        "default_branch": "main",
        "capsule": str(projects_module.CAPSULE_DIR / "polymath-hq.md"),
        # The capsule ships with the repository, so this run reports the path.
        "capsule_exists": True,
    }
    # The worker still ran a cycle; the project flag changed only the target.
    assert summary["processed"] is True


def test_main_uses_the_registry_default_branch(tmp_path, capsys, monkeypatch):
    """A registry entry whose default_branch is not 'main' must be honoured."""
    registry = write_registry(
        tmp_path,
        "projects:\n"
        "  hq-trunk:\n"
        "    name: HQ Trunk\n"
        "    github: bimald986-cell/Polymath-HQ\n"
        "    default_branch: trunk\n",
    )
    monkeypatch.setenv(projects_module.PROJECTS_ENV, str(registry))
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")

    rc = _run(tmp_path, "--publish-github", "--project", "hq-trunk")
    captured = capsys.readouterr()
    assert rc == 0
    assert "on base branch trunk" in captured.out
    summary = json.loads(captured.out.strip().splitlines()[-1])
    assert summary["project"]["default_branch"] == "trunk"


def test_main_refuses_an_unknown_project_before_any_network_call(tmp_path, capsys):
    """Exit 2, name the project and the registry file, and never touch the wire."""
    rc = _run(tmp_path, "--publish-github", "--project", "mind-mythos-ii")
    captured = capsys.readouterr()

    assert rc == 2
    assert "mind-mythos-ii" in captured.err
    assert str(SHIPPED_REGISTRY) in captured.err
    assert "GITHUB_TOKEN" not in captured.err  # refused before the client is built
    assert captured.out == ""


def test_main_refuses_two_disagreeing_flags(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")
    rc = _run(
        tmp_path,
        "--publish-github",
        "--project",
        "polymath-hq",
        "--repo",
        "owner/other",
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "owner/other" in captured.err and "bimald986-cell/Polymath-HQ" in captured.err
    assert "GitHub publishing enabled" not in captured.out


def test_main_refuses_a_contradicting_github_repo_environment(tmp_path, capsys, monkeypatch):
    """A silently overridden GITHUB_REPO would be the same silent pick."""
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/from-the-environment")
    rc = _run(tmp_path, "--publish-github", "--project", "polymath-hq")
    captured = capsys.readouterr()
    assert rc == 2
    assert "owner/from-the-environment" in captured.err


def test_main_reports_a_missing_capsule_instead_of_skipping_it(tmp_path, capsys, monkeypatch):
    registry = write_registry(
        tmp_path,
        "projects:\n"
        "  ghost:\n"
        "    name: Ghost\n"
        "    capsule: no-such-capsule.md\n"
        "    github: owner/ghost\n"
        "    default_branch: main\n",
    )
    monkeypatch.setenv(projects_module.PROJECTS_ENV, str(registry))
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")

    rc = _run(tmp_path, "--publish-github", "--project", "ghost")
    captured = capsys.readouterr()
    assert rc == 0
    assert "Project capsule missing:" in captured.err
    assert "no-such-capsule.md" in captured.err
    summary = json.loads(captured.out.strip().splitlines()[-1])
    assert summary["project"]["capsule_exists"] is False


def test_main_reports_an_existing_capsule_path(tmp_path, capsys, monkeypatch):
    registry = write_registry(
        tmp_path,
        "projects:\n"
        "  real:\n"
        "    name: Real\n"
        "    capsule: mind-mythos.md\n"
        "    github: owner/real\n"
        "    default_branch: main\n",
    )
    monkeypatch.setenv(projects_module.PROJECTS_ENV, str(registry))
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")

    rc = _run(tmp_path, "--publish-github", "--project", "real")
    captured = capsys.readouterr()
    assert rc == 0
    assert "Project capsule: " in captured.out
    assert "mind-mythos.md" in captured.out
    summary = json.loads(captured.out.strip().splitlines()[-1])
    assert summary["project"]["capsule_exists"] is True


def test_a_run_without_project_keeps_the_old_summary_shape(tmp_path, capsys, monkeypatch):
    """No --project: the JSON is byte-for-byte what it was before this change."""
    db = str(tmp_path / "queue.db")
    rc = main(["--once", "--db", db, "--worker-id", "cli", "--allow-mock-llm"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload == {"db": db, "processed": True, "worker_id": "cli"}


def test_github_repo_still_decides_without_project(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/env-target")
    rc = _run(tmp_path, "--publish-github")
    captured = capsys.readouterr()
    assert rc == 0
    assert "GitHub publishing enabled for owner/env-target" in captured.out
    assert "on base branch main" in captured.out


# ----------------------------------------------------------- the boundary
def test_project_resolution_cannot_reach_a_merge(monkeypatch):
    """Naming a project changes the target only: the boundary is untouched.

    ``GitHubClient.merge_pull_request`` exists purely to raise, so the assertion
    is on the refusal, not on the method's absence.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "placeholder-token")
    publisher = build_publisher("bimald986-cell/Polymath-HQ", base_branch="main")
    assert not hasattr(publisher, "merge")
    with pytest.raises(PermissionError):
        publisher.client.merge_pull_request("bimald986-cell/Polymath-HQ", 1)
