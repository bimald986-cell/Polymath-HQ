"""A registered project must resolve to a repository, or fail explicitly.

The defect this guards
----------------------
Audit ``HQ_AUDIT_03_PROJECT_FLOW.md`` §2: ``core/projects.yaml`` was read by one
never-invoked script that filtered most projects out by type, mentioned in a
prompt string by the scheduled cycle, and otherwise ignored — while
``github_client.py`` took its target from ``GITHUB_REPO``/``--repo`` only. A
registered project did nothing at runtime.

What is asserted here
---------------------
1. Resolution by id, by display name, by alias, and by a case/whitespace variant.
2. Word-bounded matching: a project name inside a longer word does not match, so
   the two-letter aliases in the shipped registry (``mm``, ``al``, ``rb``) cannot
   fire on ordinary prose and ``astrolab`` cannot match inside "astrolabes".
3. The three failures are distinguishable and none of them guesses: unknown
   project, malformed registry, missing required field. An ambiguous mention is a
   fourth, also refused.
4. Everything comes from the YAML: a project that exists only in a temporary
   registry resolves, and a project that exists only in the *shipped* registry
   stops resolving when that file is replaced. No Python-side project knowledge.
5. The default path works from the repository root and from ``intelligent-agency/``
   (the CI working directory), and ``HORIZON_PROJECTS_REGISTRY`` overrides it.

No network: this module performs none, and the tests assert nothing about whether
a repository exists — only about what the registry says.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import projects as projects_module  # noqa: E402
from agency.projects import (  # noqa: E402
    AmbiguousProjectError,
    MissingFieldError,
    Project,
    RegistryError,
    UnknownProjectError,
    find_mentions,
    load_registry,
    registry_path,
    resolve,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIPPED_REGISTRY = REPO_ROOT / "core" / "projects.yaml"

VALID_ENTRY = (
    "  zebra-labs:\n"
    "    name: Zebra Labs\n"
    "    aliases: [zebra, zl]\n"
    "    github: owner/zebra-labs\n"
    "    default_branch: trunk\n"
    "    type: product\n"
)


def write_registry(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "projects.yaml"
    path.write_text(body, encoding="utf-8")
    return path


# --------------------------------------------------------------- the happy path
def test_resolves_by_id():
    project = resolve("mind-mythos")
    assert isinstance(project, Project)
    assert project.id == "mind-mythos"
    assert project.github == "bimald986-cell/mind-mythos"
    assert project.default_branch == "main"
    assert project.type == "content-brand"
    # The name is the registry's, not a title-cased id.
    assert project.name == "Mind & Mythos"


def test_resolves_by_display_name():
    assert resolve("Mind & Mythos").id == "mind-mythos"


@pytest.mark.parametrize("alias", ["M&M", "mm", "Mind and Mythos"])
def test_resolves_by_alias(alias):
    assert resolve(alias).id == "mind-mythos"


def test_resolves_by_exact_case_and_whitespace_variant():
    assert resolve("MIND-MYTHOS").id == "mind-mythos"
    assert resolve("  mind   &    mythos  ").id == "mind-mythos"
    assert resolve("mm").id == resolve("MM").id


def test_alias_of_one_project_does_not_shadow_another():
    """``al`` is AstroLab's alias; ``rb`` is RateBridge's. Each resolves to its own."""
    assert resolve("al").id == "astrolab-v6"
    assert resolve("rb").id == "ratebridge"
    assert resolve("al").github != resolve("rb").github


# ------------------------------------------------------------- word boundaries
@pytest.mark.parametrize(
    "query",
    [
        "astrolabes",  # contains the alias "astrolab"
        "also",  # contains the alias "al"
        "mindfulness",  # contains nothing, but shares a prefix with "mind-mythos"
        "mind-mythos-extra",  # "-" is a word character, so this is a different token
        "hmm",  # contains the alias "mm"
        "ratebridge2",
    ],
)
def test_a_project_name_inside_a_longer_word_does_not_match(query):
    with pytest.raises(UnknownProjectError):
        resolve(query)


def test_a_word_bounded_mention_inside_a_phrase_does_match():
    """The rule above must not be satisfied by refusing every phrase."""
    assert resolve("please tighten the mind-mythos docs").id == "mind-mythos"
    assert resolve("what about astrolab this week?").id == "astrolab-v6"


def test_a_phrase_naming_two_projects_is_ambiguous_not_a_coin_flip():
    with pytest.raises(AmbiguousProjectError) as excinfo:
        resolve("compare mind-mythos with astrolab")
    message = str(excinfo.value)
    assert "mind-mythos" in message and "astrolab-v6" in message
    assert "name exactly one" in message


def test_find_mentions_returns_every_match_in_registry_order():
    ids = [p.id for p in find_mentions("mind-mythos and astrolab and ratebridge")]
    assert ids == ["mind-mythos", "astrolab-v6", "ratebridge"]
    assert find_mentions("nothing to see here") == []


# ------------------------------------------------------------------- the errors
def test_unknown_project_is_refused_and_names_the_registry():
    with pytest.raises(UnknownProjectError) as excinfo:
        resolve("project-that-does-not-exist")
    message = str(excinfo.value)
    assert "project-that-does-not-exist" in message
    assert str(SHIPPED_REGISTRY) in message
    # It offers what *is* registered rather than inventing a target.
    assert "mind-mythos" in message


def test_empty_query_is_refused_rather_than_defaulting():
    with pytest.raises(UnknownProjectError):
        resolve("   ")


@pytest.mark.parametrize(
    "body",
    [
        "projects: [this is not a mapping]\n",
        "- just\n- a\n- list\n",
        "nothing_here: {}\n",
        "projects:\n  broken: not-a-mapping\n",
        "projects:\n  broken:\n    github: not-a-repo\n    default_branch: main\n",
        "projects:\n  broken:\n    github: owner/name\n    default_branch: main\n    aliases: just-a-string\n",
        # Two projects claiming one alias: the second would shadow the first.
        (
            "projects:\n"
            "  first:\n    name: First\n    aliases: [shared]\n"
            "    github: owner/first\n    default_branch: main\n"
            "  second:\n    name: Second\n    aliases: [shared]\n"
            "    github: owner/second\n    default_branch: main\n"
        ),
    ],
)
def test_malformed_registry_is_refused(tmp_path, body):
    path = write_registry(tmp_path, body)
    with pytest.raises(RegistryError):
        load_registry(path)


def test_unreadable_registry_is_refused_by_path(tmp_path):
    missing = tmp_path / "absent.yaml"
    with pytest.raises(RegistryError) as excinfo:
        load_registry(missing)
    assert str(missing) in str(excinfo.value)


@pytest.mark.parametrize("field", ["github", "default_branch"])
def test_missing_required_field_names_the_field_and_the_project(tmp_path, field):
    lines = {
        "github": "    github: owner/zebra-labs\n",
        "default_branch": "    default_branch: trunk\n",
    }
    body = "projects:\n  zebra-labs:\n    name: Zebra Labs\n" + "".join(
        line for key, line in lines.items() if key != field
    )
    path = write_registry(tmp_path, body)
    with pytest.raises(MissingFieldError) as excinfo:
        load_registry(path)
    message = str(excinfo.value)
    assert field in message and "zebra-labs" in message and str(path) in message


def test_an_empty_registry_resolves_nothing(tmp_path):
    """Empty is not malformed — it is simply a registry that knows no project."""
    path = write_registry(tmp_path, "projects: {}\n")
    assert load_registry(path) == {}
    with pytest.raises(UnknownProjectError) as excinfo:
        resolve("mind-mythos", path)
    assert str(path) in str(excinfo.value)


def test_missing_field_error_is_a_registry_error():
    """Callers that only catch ``RegistryError`` still see the refusal."""
    assert issubclass(MissingFieldError, RegistryError)


# ------------------------------------------------- the YAML is the only source
def test_a_project_that_exists_only_in_the_registry_resolves(tmp_path):
    path = write_registry(tmp_path, "projects:\n" + VALID_ENTRY)
    project = resolve("zebra", path)
    assert project.id == "zebra-labs"
    assert project.github == "owner/zebra-labs"
    assert project.default_branch == "trunk"


def test_the_code_holds_no_project_knowledge_of_its_own(tmp_path):
    """Replace the registry and the shipped names stop resolving: no Python map."""
    path = write_registry(tmp_path, "projects:\n" + VALID_ENTRY)
    with pytest.raises(UnknownProjectError):
        resolve("mind-mythos", path)


def test_every_shipped_entry_resolves_to_its_own_yaml_github():
    """The resolver's answers are the file's answers, entry by entry."""
    raw = projects_module.load_raw_registry(SHIPPED_REGISTRY)
    assert raw, "the shipped registry should not be empty"
    registry = load_registry(SHIPPED_REGISTRY)
    assert set(registry) == {str(k) for k in raw}
    for project_id, entry in raw.items():
        assert registry[project_id].github == entry["github"]
        assert registry[project_id].default_branch == entry["default_branch"]


def test_hq_itself_is_registered_and_resolves():
    """The one repository this work may actually touch is a registry entry."""
    project = resolve("polymath-hq")
    assert project.github == "bimald986-cell/Polymath-HQ"
    assert project.default_branch == "main"


# ------------------------------------------------------------ capsules, paths
def test_capsule_defaults_to_the_project_id_and_can_be_overridden(tmp_path):
    body = (
        "projects:\n"
        "  astro:\n    github: owner/astro\n    default_branch: main\n"
        "  shop:\n    capsule: sajilo-retail.md\n    github: owner/shop\n"
        "    default_branch: main\n"
    )
    registry = load_registry(write_registry(tmp_path, body))
    assert registry["astro"].capsule == "astro.md"
    assert registry["shop"].capsule == "sajilo-retail.md"


def test_capsule_existence_is_reported_not_assumed(tmp_path):
    body = (
        "projects:\n"
        "  real:\n    capsule: mind-mythos.md\n    github: owner/real\n"
        "    default_branch: main\n"
        "  absent:\n    capsule: no-such-capsule.md\n    github: owner/absent\n"
        "    default_branch: main\n"
    )
    registry = load_registry(write_registry(tmp_path, body))
    assert registry["real"].capsule_exists() is True
    assert registry["absent"].capsule_exists() is False
    assert registry["absent"].capsule_path.name == "no-such-capsule.md"


def test_registry_path_honours_the_environment_override(tmp_path, monkeypatch):
    path = write_registry(tmp_path, "projects:\n" + VALID_ENTRY)
    monkeypatch.setenv(projects_module.PROJECTS_ENV, str(path))
    assert registry_path() == path
    assert resolve("zebra").github == "owner/zebra-labs"
    # An explicit argument still wins over the environment.
    monkeypatch.setenv(projects_module.PROJECTS_ENV, str(tmp_path / "other.yaml"))
    assert resolve("zebra", path).id == "zebra-labs"


@pytest.mark.parametrize("cwd", [REPO_ROOT, REPO_ROOT / "intelligent-agency"])
def test_default_path_works_from_the_repo_root_and_from_intelligent_agency(cwd, monkeypatch):
    """The CI working directory is ``intelligent-agency/``; the module must not
    depend on the process's cwd."""
    monkeypatch.chdir(cwd)
    monkeypatch.delenv(projects_module.PROJECTS_ENV, raising=False)
    assert resolve("mind-mythos").github == "bimald986-cell/mind-mythos"


def test_the_module_performs_no_network_io(monkeypatch):
    """Resolution is a file read. If anything here reached the network, this fails."""
    import urllib.request

    def boom(*args, **kwargs):
        raise AssertionError("projects.resolve attempted a network call")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert resolve("mind-mythos").github == "bimald986-cell/mind-mythos"


def test_module_source_has_no_embedded_repository_names():
    """A guard against a fourth hardcoded map: repo targets come from the YAML."""
    source = Path(projects_module.__file__).read_text(encoding="utf-8")
    raw = projects_module.load_raw_registry(SHIPPED_REGISTRY)
    for entry in raw.values():
        github = str(entry.get("github") or "")
        if github:
            assert github not in source, f"{github} is hardcoded in projects.py"
