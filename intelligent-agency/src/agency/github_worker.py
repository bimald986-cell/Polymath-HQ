"""Guarded GitHub implementation plan for Horizon.

This module deliberately produces a declarative change request. The deployment
adapter is responsible for authenticating and executing it. Merge is never an
allowed operation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import re

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
    def validate(cls, change: ReviewChangeSet) -> None:
        if change.branch in cls.protected or not change.branch.startswith("horizon/"):
            raise PermissionError("Horizon may write only to horizon/* review branches")
        if not re.fullmatch(r"horizon/[A-Za-z0-9._/-]+", change.branch):
            raise ValueError("invalid Horizon branch")
        for f in change.files:
            p=f.path.replace('\\','/')
            if p.startswith('.github/workflows/') or p.startswith('.git/'):
                raise PermissionError("runtime may not modify workflow/security control files autonomously")
            if any(token in p.lower() for token in ('.env','secret','credential','private_key')):
                raise PermissionError("runtime may not modify secret/credential material")

    @staticmethod
    def president_brief(change: ReviewChangeSet) -> str:
        bullets=lambda xs: '\n'.join(f'- {x}' for x in xs) if xs else '- None'
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
