"""Guarded GitHub change-sets for Horizon, and the publisher that ships them.

The guard decides *whether* a change-set may exist; :class:`GitHubPublisher`
is the adapter that turns an approved change-set into a review branch plus a
pull request through :class:`agency.github_client.GitHubClient`. Merge is never
an allowed operation, in the guard or in the client.

PolicyEngine is consulted before path/branch validation so irreversible tools
(merge, push to protected branches) are denied unless President-authorized.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import re

from .policy import PolicyEngine, default_engine


@dataclass
class FileChange:
    path: str
    content: str
    message: str


@dataclass
class ReviewChangeSet:
    title: str
    branch: str
    summary: str
    files: List[FileChange] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    rollback: str = "Revert the pull request."


class GitHubGuard:
    protected = {"main", "master", "production", "release"}

    @classmethod
    def validate(
        cls,
        change: ReviewChangeSet,
        *,
        policy: Optional[PolicyEngine] = None,
        president_authorized: bool = False,
        actor: str = "horizon",
    ) -> None:
        eng = policy or default_engine()

        # Policy layer: preparing a review changeset is NETWORK-class (opens PR path).
        eng.require(
            "github_review_changeset",
            president_authorized=president_authorized,
            target=change.branch,
            actor=actor,
        )

        # Explicitly deny merge / protected push even if someone names the tool wrong later.
        if change.branch in cls.protected:
            eng.require(
                "push_to_protected_branch",
                president_authorized=president_authorized,
                target=change.branch,
                actor=actor,
            )

        if change.branch in cls.protected or not change.branch.startswith("horizon/"):
            raise PermissionError("Horizon may write only to horizon/* review branches")
        if not re.fullmatch(r"horizon/[A-Za-z0-9._/-]+", change.branch):
            raise ValueError("invalid Horizon branch")
        for f in change.files:
            p = f.path.replace("\\", "/")
            if p.startswith(".github/workflows/") or p.startswith(".git/"):
                raise PermissionError(
                    "runtime may not modify workflow/security control files autonomously"
                )
            if any(token in p.lower() for token in (".env", "secret", "credential", "private_key")):
                raise PermissionError("runtime may not modify secret/credential material")

    @classmethod
    def deny_merge(
        cls,
        *,
        policy: Optional[PolicyEngine] = None,
        president_authorized: bool = False,
        actor: str = "horizon",
    ) -> None:
        """Hard stop for any code path that tries to merge."""
        eng = policy or default_engine()
        eng.require(
            "merge_pull_request",
            president_authorized=president_authorized,
            actor=actor,
        )

    @staticmethod
    def president_brief(change: ReviewChangeSet) -> str:
        bullets = lambda xs: "\n".join(f"- {x}" for x in xs) if xs else "- None"
        return f"""## President Brief: {change.title}

**Why this matters:** {change.summary}

### Files changed
{bullets([f.path for f in change.files])}

### Verification
{bullets(change.tests)}

### Risks / trade-offs
{bullets(change.risks)}

### Rollback
{change.rollback}

### Decision requested
Review this Horizon-created change. Merge only if you approve.
"""


@dataclass
class PublishResult:
    """What actually landed on GitHub: a review branch and an open pull request."""

    branch: str
    files: List[str]
    pull_request: Dict[str, Any] = field(default_factory=dict)

    @property
    def pr_url(self) -> str:
        return str(self.pull_request.get("html_url", ""))

    @property
    def pr_number(self) -> Optional[int]:
        number = self.pull_request.get("number")
        return int(number) if isinstance(number, int) else None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "branch": self.branch,
            "files": list(self.files),
            "pull_request": self.pull_request,
        }


def changeset_from_payload(payload: Dict[str, Any], *, branch: Optional[str] = None) -> ReviewChangeSet:
    """Build a ReviewChangeSet from a queued work-item payload.

    Accepts either an explicit change-set shape (``title``/``branch``/``files``)
    or a bare ``task`` command from the dashboard, which becomes a one-file
    proposal note on a deterministic review branch.
    """
    if not isinstance(payload, dict):
        raise ValueError("work payload must be an object")
    if payload.get("files"):
        files = [
            FileChange(
                path=str(f["path"]),
                content=str(f.get("content", "")),
                message=str(f.get("message", f"horizon: update {f['path']}")),
            )
            for f in payload["files"]
        ]
        change = ReviewChangeSet(
            title=str(payload.get("title") or "Horizon change-set"),
            branch=str(branch or payload.get("branch") or ""),
            summary=str(payload.get("summary") or ""),
            files=files,
            tests=[str(t) for t in payload.get("tests", [])],
            risks=[str(r) for r in payload.get("risks", [])],
            rollback=str(payload.get("rollback") or "Revert the pull request."),
        )
    else:
        task = str(payload.get("task") or payload.get("command") or "").strip()
        if not task:
            raise ValueError("work payload has neither files nor a task")
        item_id = payload.get("id")
        slug = branch or str(payload.get("branch") or "") or (
            f"horizon/proposal-{item_id if item_id is not None else 'adhoc'}"
        )
        change = ReviewChangeSet(
            title=str(payload.get("title") or "Horizon proposal"),
            branch=slug,
            summary=task,
            files=[
                FileChange(
                    path=str(payload.get("path") or "docs/horizon-proposals.md"),
                    content=f"# Horizon proposal\n\n{task}\n",
                    message="horizon: record proposal",
                )
            ],
            tests=["Human review required before merge."],
        )
    GitHubGuard.validate(change)
    return change


class GitHubPublisher:
    """Turn a validated change-set into a real branch + pull request.

    Order of operations, none of which can be skipped:

    1. :meth:`GitHubGuard.validate` — the existing policy and path/branch rules,
       always consulted first, so policy can never be bypassed by the publisher.
    2. create the review branch (idempotent),
    3. write each file,
    4. open the pull request with the President Brief as its body.

    Merging is not implemented anywhere on this path.
    """

    def __init__(
        self,
        client,
        *,
        base_branch: str = "main",
        policy: Optional[PolicyEngine] = None,
        actor: str = "horizon",
    ):
        if client is None:
            raise ValueError("GitHubPublisher requires a GitHubClient")
        self.client = client
        self.base_branch = base_branch
        self.policy = policy or default_engine()
        self.actor = actor

    def publish(
        self,
        change: ReviewChangeSet,
        *,
        president_authorized: bool = False,
        draft: bool = False,
    ) -> PublishResult:
        # 1. policy + branch/path guard, unchanged and unbypassable.
        GitHubGuard.validate(
            change,
            policy=self.policy,
            president_authorized=president_authorized,
            actor=self.actor,
        )
        if not change.files:
            raise ValueError("change-set has no files to publish")
        # 2-4. execute it.
        self.client.create_branch(change.branch, from_branch=self.base_branch)
        written: List[str] = []
        for f in change.files:
            self.client.put_file(change.branch, f.path, f.content, f.message)
            written.append(f.path)
        pr = self.client.open_pull_request(
            title=change.title,
            head=change.branch,
            base=self.base_branch,
            body=GitHubGuard.president_brief(change),
            draft=draft,
        )
        return PublishResult(branch=change.branch, files=written, pull_request=pr)

    def publish_payload(
        self,
        payload: Dict[str, Any],
        *,
        branch: Optional[str] = None,
        president_authorized: bool = False,
    ) -> PublishResult:
        """Publish directly from a queued work-item payload."""
        return self.publish(
            changeset_from_payload(payload, branch=branch),
            president_authorized=president_authorized,
        )
