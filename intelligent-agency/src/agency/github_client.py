"""Real GitHub transport for the HQ runtime.

Standard library only (``urllib.request``), matching ``llm.py``: this repository
carries no third-party HTTP dependency and must not grow one.

The token is read from the ``GITHUB_TOKEN`` environment variable. It is never
hardcoded, never logged and never written to disk.

Hard refusals — enforced here, in code, not only in the prompt:

* **Merge is impossible.** :meth:`GitHubClient.merge_pull_request` always raises,
  whatever the policy or authorization arguments say. Merging stays a human
  President decision (``docs/MIND_MYTHOS_INTEGRATION.md``, authority boundary).
* **Protected branches are never written to** (``main``, ``master``,
  ``production``, ``release``); the runtime writes only to its configured review
  branch prefix (``horizon/`` by default).
* **Workflow / security / secret files are never touched**
  (``.github/workflows/``, ``.git/``, ``*.env``, ``*secret*``, ``*credential*``,
  ``*private_key*``).

Every request goes through an injectable ``transport`` callable so tests can
exercise the full client with zero network access.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

API_DEFAULT = "https://api.github.com"
DEFAULT_TIMEOUT = 30

# A transport receives (method, url, headers, body_bytes_or_None, timeout) and
# returns (status_code, response_body_bytes).
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], Tuple[int, bytes]]


class GitHubError(RuntimeError):
    """A GitHub API call failed (or was refused by the transport layer)."""

    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body

    def as_dict(self) -> Dict[str, Any]:
        return {"error": str(self), "status": self.status}


class GitHubAuthError(GitHubError):
    """No usable credential is configured. Raised loudly and specifically."""


def _urllib_transport(
    method: str,
    url: str,
    headers: Dict[str, str],
    data: Optional[bytes],
    timeout: float,
) -> Tuple[int, bytes]:
    """Default transport: one ``urllib.request`` call per API request."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:  # status + body matter for callers
        return int(exc.code), exc.read() or b""


class GitHubClient:
    """Minimal, guard-railed GitHub REST client: branch, file, pull request."""

    PROTECTED_BRANCHES = frozenset({"main", "master", "production", "release"})
    FORBIDDEN_PATH_PREFIXES = (".github/workflows/", ".git/")
    FORBIDDEN_PATH_TOKENS = (".env", "secret", "credential", "private_key")
    MAX_FILE_BYTES = 900_000  # GitHub contents API ceiling is ~1 MB; stay under it.

    def __init__(
        self,
        repo: Optional[str] = None,
        token: Optional[str] = None,
        *,
        api_base: str = API_DEFAULT,
        branch_prefix: str = "horizon/",
        transport: Optional[Transport] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        resolved_token = (token if token is not None else os.getenv("GITHUB_TOKEN", "")).strip()
        if not resolved_token:
            raise GitHubAuthError(
                "GITHUB_TOKEN is not configured: cannot create branches, write files or open "
                "pull requests. Set GITHUB_TOKEN to a token with repo write scope "
                "(merge is not required and is never used)."
            )
        resolved_repo = (repo if repo is not None else os.getenv("GITHUB_REPO", "")).strip()
        if not resolved_repo:
            raise GitHubAuthError(
                "No target repository configured: pass repo='owner/name' or set GITHUB_REPO."
            )
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", resolved_repo):
            raise ValueError(f"repo must be 'owner/name', got {resolved_repo!r}")
        if not branch_prefix.endswith("/"):
            raise ValueError("branch_prefix must end with '/'")

        self.repo = resolved_repo
        self.token = resolved_token
        self.api_base = api_base.rstrip("/")
        self.branch_prefix = branch_prefix
        self.timeout = timeout
        self._transport = transport or _urllib_transport
        # Kept for auditability: which calls this client actually made.
        self.calls: list[Dict[str, Any]] = []

    @classmethod
    def from_env(cls, repo: Optional[str] = None, **kwargs: Any) -> "GitHubClient":
        """Build from ``GITHUB_TOKEN`` / ``GITHUB_REPO``; raises if unset."""
        return cls(repo=repo, **kwargs)

    # ------------------------------------------------------------------ guards
    def assert_writable_branch(self, branch: str) -> None:
        if not branch or not isinstance(branch, str):
            raise ValueError("branch name is required")
        if branch in self.PROTECTED_BRANCHES:
            raise PermissionError(
                f"refusing to write to protected branch {branch!r}: "
                "the runtime never writes to a protected branch"
            )
        if not branch.startswith(self.branch_prefix):
            raise PermissionError(
                f"refusing to write to branch {branch!r}: the runtime writes only to "
                f"{self.branch_prefix}* review branches"
            )

    def assert_writable_path(self, path: str) -> str:
        normalised = (path or "").replace("\\", "/")
        while normalised.startswith("./"):
            normalised = normalised[2:]
        if not normalised or normalised.endswith("/"):
            raise ValueError(f"invalid file path: {path!r}")
        if ".." in normalised.split("/"):
            raise ValueError(f"invalid file path: {path!r}")
        if normalised.startswith(self.FORBIDDEN_PATH_PREFIXES):
            raise PermissionError(
                f"refusing to modify {normalised}: workflow and Git control files are "
                "out of bounds for autonomous runtime writes"
            )
        lowered = normalised.lower()
        if any(token in lowered for token in self.FORBIDDEN_PATH_TOKENS):
            raise PermissionError(
                f"refusing to modify {normalised}: secret/credential material is out of bounds"
            )
        return normalised

    # ----------------------------------------------------------------- request
    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        ok_statuses: Tuple[int, ...] = (200, 201, 204),
        allow_404: bool = False,
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.api_base}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "polymath-hq-horizon",
            "Content-Type": "application/json",
        }
        status, raw = self._transport(method, url, headers, body, self.timeout)
        text = raw.decode("utf-8", "replace") if raw else ""
        self.calls.append({"method": method, "url": url, "status": status})
        if allow_404 and status == 404:
            return None
        if status not in ok_statuses:
            raise GitHubError(
                f"{method} {path} failed with HTTP {status}: {text[:400]}", status=status, body=text
            )
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    # ------------------------------------------------------------------ reads
    def get_branch_sha(self, branch: str) -> Optional[str]:
        data = self._request(
            "GET",
            f"/repos/{self.repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}",
            allow_404=True,
        )
        if not data:
            return None
        obj = data.get("object") or {}
        sha = obj.get("sha")
        return str(sha) if sha else None

    def get_file_sha(self, branch: str, path: str) -> Optional[str]:
        data = self._request(
            "GET",
            f"/repos/{self.repo}/contents/{urllib.parse.quote(path, safe='/')}"
            f"?ref={urllib.parse.quote(branch, safe='')}",
            allow_404=True,
        )
        if not data:
            return None
        sha = data.get("sha")
        return str(sha) if sha else None

    # ------------------------------------------------------------------ writes
    def create_branch(self, branch: str, from_branch: str = "main") -> str:
        """Create ``branch`` from ``from_branch``. Idempotent: existing branch is kept."""
        self.assert_writable_branch(branch)
        if self.get_branch_sha(branch):
            return branch
        sha = self.get_branch_sha(from_branch)
        if not sha:
            raise GitHubError(f"base branch {from_branch!r} not found in {self.repo}")
        self._request(
            "POST",
            f"/repos/{self.repo}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
            ok_statuses=(201,),
        )
        return branch

    def put_file(self, branch: str, path: str, content: str, message: str) -> Dict[str, Any]:
        """Create or update one file on ``branch`` via the contents API."""
        self.assert_writable_branch(branch)
        safe_path = self.assert_writable_path(path)
        encoded = base64.b64encode(content.encode("utf-8")).decode()
        if len(encoded) > self.MAX_FILE_BYTES:
            raise ValueError(
                f"refusing to write {safe_path}: {len(encoded)} bytes exceeds the "
                f"{self.MAX_FILE_BYTES}-byte contents API limit"
            )
        payload: Dict[str, Any] = {
            "message": message or f"horizon: update {safe_path}",
            "content": encoded,
            "branch": branch,
        }
        existing = self.get_file_sha(branch, safe_path)
        if existing:
            payload["sha"] = existing
        result = self._request(
            "PUT",
            f"/repos/{self.repo}/contents/{urllib.parse.quote(safe_path, safe='/')}",
            payload,
            ok_statuses=(200, 201),
        )
        return result or {}

    def open_pull_request(
        self,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
    ) -> Dict[str, Any]:
        """Open a pull request from ``head`` into ``base``. Never merges it."""
        self.assert_writable_branch(head)
        if head == base:
            raise PermissionError("refusing to open a pull request whose head is its base")
        result = self._request(
            "POST",
            f"/repos/{self.repo}/pulls",
            {"title": title, "head": head, "base": base, "body": body, "draft": draft},
            ok_statuses=(201,),
        )
        return result or {}

    def merge_pull_request(self, *args: Any, **kwargs: Any) -> None:
        """Hard stop. The runtime has no merge capability, by design."""
        raise PermissionError(
            "refusing to merge: merge authority belongs to the human President "
            "(docs/MIND_MYTHOS_INTEGRATION.md authority boundary). "
            "GitHubClient exposes no merge capability."
        )
