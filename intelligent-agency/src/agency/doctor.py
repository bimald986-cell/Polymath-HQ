"""``cli.py doctor``: one command that says what is ready and what is not.

A first-time user should not have to read the source to find out whether the HQ
can do anything. This module answers, item by item, using the *same* code the
runtime uses -- ``chat.provider_status`` for the provider, ``projects`` for the
registry, ``pricing`` for the rate table, ``builtin_tools`` for the tools -- so
the report cannot drift away from what a cycle would actually do.

Three properties are deliberate:

- **No network calls.** Nothing here opens a socket: a provider is inspected by
  building the backend object, not by calling it.
- **No writes.** The state store is opened read-only and ``immutable`` (so not
  even a WAL sidecar appears), and a store that does not exist yet is reported
  as "not created yet" rather than created to test it.
- **The GitHub token is reported as present or absent, and never printed.** No
  value, no prefix, no length: a doctor report is something a user pastes into
  an issue, so it must be safe to paste.

The exit code is non-zero only when something essential to *running a cycle* is
missing (the agency configuration, or a usable state store). A missing provider
is reported loudly and changes the verdict to "simulation", because the owner
has sanctioned running cycles on the mock backend; ``--require-live`` turns that
into a failure for anyone who needs a real cycle.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import chat, pricing, projects
from .builtin_tools import default_registry
from .loader import build_agency

READY = "READY"
NOT_READY = "NOT READY"
UNKNOWN = "UNKNOWN"

STATUS_WIDTH = 10
NAME_WIDTH = 16

#: Variables that carry a GitHub token. Only their presence is ever reported.
TOKEN_VARIABLES = ("GITHUB_TOKEN", "GH_TOKEN")


@dataclass(frozen=True)
class Check:
    """One line of the report: a name, a status and the reason for it."""

    name: str
    status: str
    detail: str
    #: True when a cycle cannot run at all without this. Only these set the
    #: exit code (unless ``--require-live`` is given).
    essential: bool = False


@dataclass
class DoctorReport:
    checks: List[Check] = field(default_factory=list)
    verdict: str = ""
    exit_code: int = 0

    def by_name(self, name: str) -> Optional[Check]:
        for check in self.checks:
            if check.name == name:
                return check
        return None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def render(self) -> str:
        lines = [
            "Polymath HQ doctor - what is ready and what is not",
            "(no network calls, no writes; the GitHub token is never shown)",
            "",
        ]
        for check in self.checks:
            lines.append(
                f"  {check.status:<{STATUS_WIDTH}} {check.name:<{NAME_WIDTH}} {check.detail}"
            )
        lines.append("")
        lines.append(f"Verdict: {self.verdict}")
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail, "essential": c.essential}
                for c in self.checks
            ],
            "verdict": self.verdict,
            "exit_code": self.exit_code,
        }


def check_agency_config(config_path: Optional[str] = None) -> Check:
    """The one thing nothing can run without: the org chart must load."""
    try:
        president = build_agency(config_path) if config_path else build_agency()
    except Exception as exc:
        return Check(
            "Agency config", NOT_READY,
            f"config/agency.yaml could not be loaded ({type(exc).__name__}: {exc}); "
            "no agent exists to answer or to run a cycle",
            essential=True,
        )
    directors = len(president.directors)
    agents = sum(len(director.agents) for director in president.directors)
    return Check(
        "Agency config", READY,
        f"{directors} director(s), {agents} agent(s) loaded"
        + (f"; advisor {president.advisor.name}" if president.advisor else "; no advisor"),
        essential=True,
    )


def check_provider() -> Check:
    """Whether a real model would answer, and whether a cycle would be live."""
    status = chat.provider_status()
    mode = status["analysis_mode"]
    if mode == "live":
        return Check(
            "Provider", READY,
            f"live - a cycle would be live and would use {status['model'] or 'the configured model'}",
        )
    if mode == "simulation":
        return Check(
            "Provider", NOT_READY,
            "none configured - a cycle would be a SIMULATION: the mock backend answers with "
            f"canned text. Set {chat.PROVIDER_VARIABLES}",
        )
    return Check("Provider", UNKNOWN, status["detail"])


def check_model() -> Check:
    """The exact model string a run would be priced under."""
    status = chat.provider_status()
    if status["model"]:
        return Check("Model", READY, status["model"])
    if status["analysis_mode"] == "simulation":
        return Check(
            "Model", NOT_READY,
            "none - the mock backend names no model, so a run cannot be priced "
            "(cost is reported as unknown, never as zero)",
        )
    return Check(
        "Model", UNKNOWN,
        "not known before a call: a router names the model that answered only after "
        "a provider answers",
    )


def check_registry(path: Optional[Path | str] = None) -> Check:
    """How many projects load, and whether any entry is unusable."""
    try:
        registry = projects.load_registry(path)
    except projects.ProjectError as exc:
        return Check("Project registry", NOT_READY, str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        return Check("Project registry", NOT_READY, f"{type(exc).__name__}: {exc}")
    if not registry:
        return Check(
            "Project registry", NOT_READY,
            "loads but registers no projects, so no project name can resolve to a repository",
        )
    names = ", ".join(sorted(registry))
    missing = [
        project_id for project_id, project in registry.items()
        if not str(project.github or "").strip()
        or not str(project.default_branch or "").strip()
    ]
    if missing:
        return Check(
            "Project registry", NOT_READY,
            f"{len(registry)} project(s), but {', '.join(sorted(missing))} is missing "
            "github or default_branch",
        )
    return Check(
        "Project registry", READY,
        f"{len(registry)} project(s), every entry has github + default_branch: {names}",
    )


def check_price_table(path: Optional[Any] = None) -> Check:
    """Whether runs can be priced -- and the honest answer when they cannot."""
    table, error = pricing.load_price_table_safely(path)
    if error:
        return Check("Price table", NOT_READY, f"unusable ({error}); every run reports cost unknown")
    if table is None or len(table) == 0:
        return Check(
            "Price table", READY,
            "empty on purpose: no rates are recorded, so every run reports cost as unknown "
            "rather than inventing one",
        )
    return Check("Price table", READY, f"{len(table)} rate entr(y/ies) present")


def _store_counts(path: Path):
    """``(runs, memory)`` counts read without writing to the database.

    ``mode=ro`` is tried first because it sees the WAL, which is where a live
    writer's rows are until it checkpoints; ``immutable=1`` is the fallback for a
    database whose sidecar files are gone. A missing table is reported as
    ``None`` -- "this store has no runs table yet" -- rather than as a failure.
    """
    last_error: Optional[Exception] = None
    for uri in (f"file:{path}?mode=ro", f"file:{path}?mode=ro&immutable=1"):
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=5)
        except sqlite3.Error as exc:  # pragma: no cover - depends on the file
            last_error = exc
            continue
        try:
            counts = []
            for table in ("runs", "memory"):
                try:
                    counts.append(connection.execute(f"select count(*) from {table}").fetchone()[0])
                except sqlite3.OperationalError:
                    counts.append(None)
            return tuple(counts)
        except sqlite3.DatabaseError as exc:  # pragma: no cover - defensive
            last_error = exc
        finally:
            connection.close()
    raise last_error if last_error else sqlite3.DatabaseError("could not read the store")


def _nearest_existing(path: Path) -> Path:
    """The closest existing ancestor of ``path`` (``path`` itself if it exists)."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return probe


def check_state_store(path: Optional[str] = None) -> Check:
    """Where run records land, and whether that path is usable -- without writing."""
    resolved = Path(path or chat.state_path())
    if resolved.exists():
        try:
            runs, memory = _store_counts(resolved)
        except sqlite3.DatabaseError as exc:
            return Check(
                "State store", NOT_READY,
                f"{resolved} exists but could not be read as a database ({exc})",
                essential=True,
            )
        runs_text = "no runs table yet" if runs is None else f"{runs} run record(s)"
        memory_text = "no memory table yet" if memory is None else f"{memory} memory row(s)"
        return Check(
            "State store", READY,
            f"{resolved} opens (read-only check): {runs_text}, {memory_text}",
            essential=True,
        )
    ancestor = _nearest_existing(resolved.parent)
    if not ancestor.is_dir() or not os.access(str(ancestor), os.W_OK):
        return Check(
            "State store", NOT_READY,
            f"{resolved} does not exist and cannot be created under {ancestor}; "
            "no run could be recorded",
            essential=True,
        )
    return Check(
        "State store", READY,
        f"{resolved} not created yet - the first run will create it",
        essential=True,
    )


def check_tools(repo_root: Optional[str] = None) -> Check:
    """The tools an agent can actually call, through the policy gate."""
    try:
        registry = default_registry(repo_root)
        specs = registry.specs()
    except Exception as exc:
        return Check("Tools", NOT_READY, f"the tool registry could not be built ({exc})")
    names = []
    for spec in specs:
        name = spec.get("name") if isinstance(spec, dict) else getattr(spec, "name", None)
        if name:
            names.append(str(name))
    if not names:
        return Check("Tools", NOT_READY, "no tools are registered")
    return Check("Tools", READY, f"{len(names)} registered: {', '.join(sorted(names))}")


def check_github_token() -> Check:
    """Presence only. The value is never read into the report, not even a prefix."""
    for name in TOKEN_VARIABLES:
        if os.getenv(name, "").strip():
            return Check(
                "GitHub token", READY,
                f"{name} is set (value not shown); the worker can open branches and pull requests",
            )
    return Check(
        "GitHub token", NOT_READY,
        f"no {' or '.join(TOKEN_VARIABLES)} set; publishing to a project will be refused. "
        "Read-only inspection and chat still work",
    )


def _also_not_ready(checks: List[Check]) -> str:
    """A short clause naming the non-essential gaps, so READY is never misleading."""
    gaps = [check.name for check in checks if check.status == NOT_READY and not check.essential]
    if not gaps:
        return ""
    return (
        " Also not ready (does not block a cycle): " + ", ".join(gaps) + "."
    )


def diagnose(
    *,
    config_path: Optional[str] = None,
    registry_path: Optional[Path | str] = None,
    state_path: Optional[str] = None,
    repo_root: Optional[str] = None,
    price_table_path: Optional[Any] = None,
    require_live: bool = False,
) -> DoctorReport:
    """Run every check and decide the verdict and exit code."""
    checks = [
        check_agency_config(config_path),
        check_provider(),
        check_model(),
        check_registry(registry_path),
        check_price_table(price_table_path),
        check_state_store(state_path),
        check_tools(repo_root),
        check_github_token(),
    ]
    report = DoctorReport(checks=checks)

    blocked = [check for check in checks if check.essential and check.status == NOT_READY]
    if blocked:
        report.exit_code = 1
        report.verdict = (
            f"NOT READY - {blocked[0].name.lower()}: {blocked[0].detail}. "
            "Nothing can run a cycle until this is fixed."
        )
        return report

    provider = report.by_name("Provider")
    live = provider is not None and provider.status == READY
    if require_live and not live:
        report.exit_code = 1
        report.verdict = (
            "NOT READY (--require-live) - no real provider is configured, so a cycle would "
            f"be a simulation. Set {chat.PROVIDER_VARIABLES}."
        )
        return report

    if live:
        model = report.by_name("Model")
        report.verdict = (
            f"READY - a cycle will run live on {model.detail if model else 'the configured model'}. "
            "It may open pull requests; merging still needs you."
            + _also_not_ready(checks)
        )
        return report

    report.verdict = (
        "READY TO RUN, IN SIMULATION - a cycle will run and record itself, but every answer "
        "will be canned placeholder text, not reasoning. Set "
        f"{chat.PROVIDER_VARIABLES} to make it real."
        + _also_not_ready(checks)
    )
    return report
