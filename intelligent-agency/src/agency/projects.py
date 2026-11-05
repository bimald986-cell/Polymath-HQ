"""A registered project name -> the repository Horizon may act on.

Why this module exists
----------------------
Audit finding (``/home/team/shared/audit/HQ_AUDIT_03_PROJECT_FLOW.md`` §2-§3): a
project registered in ``core/projects.yaml`` did **nothing** at runtime. The only
reader was ``scripts/capability_scan.py`` — a script nothing invokes, which also
filters most projects out by ``type``; the scheduled cycle named the file inside a
prompt string on a path with no tool access; and ``GitHubClient`` took its target
from ``GITHUB_REPO``/``--repo`` only. So "register Mind & Mythos and let Horizon
work on it" was not something the code could do.

This module is the one place that turns a project *name* into a concrete
repository and default branch, read **entirely** from the registry file. It holds
no project knowledge of its own: no name list, no alias list, no repository name.
Add a project to ``core/projects.yaml`` and it resolves here; remove one and it
stops resolving. No code change.

What it does not do
-------------------
* **No network I/O.** Resolution is a file read plus string matching. Nothing here
  contacts GitHub, so a registry entry naming a repository that does not exist
  still resolves — this module answers "what does the registry say", never "does
  the repository exist". Existence is the transport's problem, and the audit found
  that assuming it is how a run ends in a 404 halfway through a publish.
* **No guessing.** There is no default project, no fuzzy "closest match" and no
  repository-name synthesis. An unknown name is an error, not a fallback.
* **No writes.** Read-only.

Failure modes are distinct types so a caller can act on them separately
------------------------------------------------------------------------
``UnknownProjectError``  the name matched nothing in the registry.
``AmbiguousProjectError`` the text matched more than one project (e.g. a sentence
                         naming two). Never resolved by picking one.
``RegistryError``        the registry itself is unusable: missing file, invalid
                         YAML, no ``projects:`` mapping, an entry that is not a
                         mapping, a ``github`` that is not ``owner/repo``, or one
                         alias claimed by two projects (which would let one project
                         shadow another).
``MissingFieldError``    a registry entry omits a required field (``github`` or
                         ``default_branch``). A subclass of ``RegistryError``.

Matching rules
--------------
A query is matched case-insensitively and with whitespace collapsed, first
exactly against a project's id, display name or aliases, then — for a query that
is a longer phrase — as a **word-bounded** mention. Word-bounded matters because
the shipped registry has two- and three-letter aliases (``mm``, ``al``, ``rb``,
``dsh``): ``al`` must match "al" and must not match "also", and ``astrolab`` must
not match inside "astrolabes". ``-`` counts as a word character, so ``mind-mythos``
does not match inside ``mind-mythos-extra``.

Path resolution
---------------
``<repo>/core/projects.yaml`` is found relative to this module, so it works from
the repository root, from ``intelligent-agency/`` (the CI working directory) and
from an installed console entry point alike. ``HORIZON_PROJECTS_REGISTRY``
overrides the path, matching the convention already used by
``HORIZON_PRICE_TABLE`` (``pricing.py``) and ``HORIZON_PUBLIC_API_ALLOWLIST``
(``public_api.py``).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

#: Environment variable naming an alternative registry file.
PROJECTS_ENV = "HORIZON_PROJECTS_REGISTRY"

#: The registry that ships with the HQ (``<repo>/core/projects.yaml``).
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "core" / "projects.yaml"

#: Capsules live here; the registry names the file, this directory is fixed.
CAPSULE_DIR = Path(__file__).resolve().parents[3] / "memory" / "projects"

#: ``github`` must already be ``owner/repo``; nothing is repaired or guessed.
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

#: Word boundary for mention matching. ``-`` is deliberately a word character so
#: that ``mind-mythos`` cannot match inside ``mind-mythos-extra``.
_BOUNDARY_LEFT = r"(?<![0-9a-z_-])"
_BOUNDARY_RIGHT = r"(?![0-9a-z_-])"

#: Fields a project must declare to be a usable publish target.
REQUIRED_FIELDS = ("github", "default_branch")


class ProjectError(Exception):
    """Base class for every failure this module raises."""


class RegistryError(ProjectError):
    """``core/projects.yaml`` is missing, unreadable or malformed."""


class MissingFieldError(RegistryError):
    """A registry entry omits ``github`` or ``default_branch``."""


class UnknownProjectError(ProjectError):
    """No project in the registry matches the query."""


class AmbiguousProjectError(ProjectError):
    """The query matches more than one project; refusing to pick one."""


def _normalize(text: Any) -> str:
    """Case-folded, whitespace-collapsed form used for every comparison."""
    return re.sub(r"\s+", " ", str(text).strip()).casefold()


def registry_path(path: Optional[Path | str] = None) -> Path:
    """``path`` if given, else ``HORIZON_PROJECTS_REGISTRY``, else the shipped file."""
    if path is not None:
        return Path(path)
    override = os.getenv(PROJECTS_ENV, "").strip()
    return Path(override) if override else DEFAULT_REGISTRY_PATH


@dataclass(frozen=True)
class Project:
    """One registry entry, typed. Constructed only by :func:`load_registry`."""

    id: str
    name: str
    aliases: Tuple[str, ...]
    github: str
    default_branch: str
    type: Optional[str] = None
    capsule: str = ""
    notes: str = ""
    source: str = ""

    @property
    def capsule_path(self) -> Path:
        """Where the capsule would be. The file is not required to exist."""
        return CAPSULE_DIR / self.capsule

    def capsule_exists(self) -> bool:
        return bool(self.capsule) and self.capsule_path.is_file()

    def keys(self) -> Tuple[str, ...]:
        """Every normalized string that identifies this project."""
        raw = (self.id, self.name, *self.aliases)
        seen: List[str] = []
        for key in raw:
            normalized = _normalize(key)
            if normalized and normalized not in seen:
                seen.append(normalized)
        return tuple(seen)


def load_raw_registry(path: Optional[Path | str] = None) -> Dict[str, Any]:
    """The ``projects:`` mapping, exactly as YAML gives it, or :class:`RegistryError`.

    This is the tolerant shape used by display code (``portfolio_context``) which
    wants the raw records; :func:`load_registry` is the strict, typed view.
    """
    resolved = registry_path(path)
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(f"project registry not found: {resolved} ({exc.strerror or exc})") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RegistryError(f"project registry is not valid YAML: {resolved} ({exc})") from exc
    if not isinstance(raw, dict):
        raise RegistryError(
            f"project registry must be a mapping with a 'projects:' key: {resolved}"
        )
    projects = raw.get("projects")
    if not isinstance(projects, dict):
        raise RegistryError(f"project registry has no 'projects:' mapping: {resolved}")
    return projects


def load_registry(path: Optional[Path | str] = None) -> Dict[str, Project]:
    """Every project in the registry, validated. Raises on anything unusable.

    Validation is load-time and strict on purpose: the registry is a small curated
    file, and a half-written entry must stop a run rather than silently resolve to
    a project with no repository. Every message names the file and the entry.
    """
    resolved = registry_path(path)
    raw = load_raw_registry(resolved)
    projects: Dict[str, Project] = {}

    for project_id, entry in raw.items():
        pid = str(project_id)
        if not isinstance(entry, dict):
            raise RegistryError(
                f"project {pid!r} must be a mapping of fields, got "
                f"{type(entry).__name__}: {resolved}"
            )

        missing = [f for f in REQUIRED_FIELDS if not str(entry.get(f) or "").strip()]
        if missing:
            raise MissingFieldError(
                f"project {pid!r} is missing required field(s) {', '.join(missing)} "
                f"in {resolved}; a project without a repository cannot be a target"
            )

        github = str(entry["github"]).strip()
        if not _REPO_RE.fullmatch(github):
            raise RegistryError(
                f"project {pid!r}: github {github!r} is not 'owner/repo' in {resolved}"
            )

        aliases_raw = entry.get("aliases") or []
        if isinstance(aliases_raw, str) or not isinstance(aliases_raw, (list, tuple)):
            raise RegistryError(
                f"project {pid!r}: aliases must be a list of strings in {resolved}"
            )
        aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip())

        projects[pid] = Project(
            id=pid,
            name=str(entry.get("name") or pid).strip(),
            aliases=aliases,
            github=github,
            default_branch=str(entry["default_branch"]).strip(),
            type=(str(entry["type"]).strip() if entry.get("type") else None),
            capsule=str(entry.get("capsule") or f"{pid}.md").strip(),
            notes=str(entry.get("notes") or "").strip(),
            source=str(resolved),
        )

    _refuse_shadowed_keys(projects, resolved)
    return projects


def _refuse_shadowed_keys(projects: Mapping[str, Project], source: Path | str) -> None:
    """One alias may not belong to two projects.

    ``project_capsule_index`` in ``portfolio_context`` uses ``setdefault``, so a
    duplicated alias silently gives every mention to whichever project happened to
    be listed first. That is exactly the shadowing this module refuses.
    """
    owner: Dict[str, str] = {}
    for project in projects.values():
        for key in project.keys():
            previous = owner.setdefault(key, project.id)
            if previous != project.id:
                raise RegistryError(
                    f"projects {previous!r} and {project.id!r} both claim {key!r} in "
                    f"{source}; one would shadow the other"
                )


def _matches(haystack: str, needle: str) -> bool:
    """Word-bounded, case-insensitive search for an already-normalized needle."""
    pattern = f"{_BOUNDARY_LEFT}{re.escape(needle)}{_BOUNDARY_RIGHT}"
    return re.search(pattern, haystack) is not None


def find_mentions(text: str, path: Optional[Path | str] = None) -> List[Project]:
    """Every project mentioned in ``text``, in registry order. May be empty."""
    resolved = registry_path(path)
    projects = load_registry(resolved)
    haystack = _normalize(text)
    return [
        project
        for project in projects.values()
        if any(_matches(haystack, key) for key in project.keys())
    ]


def resolve(query: str, path: Optional[Path | str] = None) -> Project:
    """Turn a project id, name or alias into its :class:`Project`.

    Exact (case-insensitive) match first, then a word-bounded mention inside a
    longer phrase. Ambiguity is an error rather than a coin flip.
    """
    resolved = registry_path(path)
    projects = load_registry(resolved)
    text = _normalize(query)

    if not text:
        raise UnknownProjectError(
            f"no project name given; {resolved} registers: {', '.join(sorted(projects))}"
        )

    for project in projects.values():
        if text in project.keys():
            return project

    mentioned = find_mentions(text, resolved)
    if len(mentioned) == 1:
        return mentioned[0]
    if mentioned:
        names = ", ".join(sorted(f"{p.id!r}" for p in mentioned))
        raise AmbiguousProjectError(
            f"project name {query!r} matches several projects ({names}) in {resolved}; "
            "name exactly one"
        )
    raise UnknownProjectError(
        f"unknown project {query!r}: not registered in {resolved}. "
        f"Registered projects: {', '.join(sorted(projects))}"
    )
