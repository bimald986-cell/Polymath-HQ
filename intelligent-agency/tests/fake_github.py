"""In-memory GitHub API stand-in for tests.

No test in this repository may make a real HTTP call. Every GitHub test injects
:class:`FakeTransport` as the client's ``transport``, so the whole request path
(URL building, auth header, payload shape, status handling) is exercised
without leaving the process.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Dict, Optional


class FakeTransport:
    """Records calls and answers the endpoints ``GitHubClient`` uses."""

    def __init__(
        self,
        branches: Optional[Dict[str, str]] = None,
        files: Optional[Dict[tuple, str]] = None,
        pr_number: int = 7,
        pr_url: str = "https://github.test/owner/repo/pull/7",
        forced_status: Optional[Dict[str, tuple]] = None,
    ):
        self.branches: Dict[str, str] = dict(
            {"main": "base-sha-0001"} if branches is None else branches
        )
        self.files: Dict[tuple, str] = dict(files or {})
        self.pr_number = pr_number
        self.pr_url = pr_url
        self.forced_status = forced_status or {}
        self.calls: list[Dict[str, Any]] = []
        self.pull_requests: list[Dict[str, Any]] = []
        self.merge_attempts = 0

    # ------------------------------------------------------------------ helpers
    def paths(self) -> list[str]:
        return [c["path"] for c in self.calls]

    def methods(self) -> list[str]:
        return [c["method"] for c in self.calls]

    def _record(self, method: str, path: str, headers: Dict[str, str], body):
        # A real client must always authenticate and never send an empty body on writes.
        assert headers.get("Authorization", "").startswith("Bearer "), "client must send a token"
        self.calls.append({"method": method, "path": path, "body": body, "headers": headers})

    @staticmethod
    def _json(status: int, payload: Dict[str, Any]) -> tuple:
        return status, json.dumps(payload).encode()

    # --------------------------------------------------------------- transport
    def __call__(self, method, url, headers, data, timeout):
        body = json.loads(data) if data else None
        marker = "/repos/"
        path = url[url.index(marker):] if marker in url else url
        query = ""
        if "?" in path:
            path, query = path.split("?", 1)
        self._record(method, path, headers, body)
        params = urllib.parse.parse_qs(query)

        for pattern, forced in self.forced_status.items():
            if re.search(pattern, path) and method == forced[0]:
                return forced[1], forced[2]

        m = re.fullmatch(r"/repos/[^/]+/[^/]+/git/ref/heads/(.+)", path)
        if m and method == "GET":
            branch = urllib.parse.unquote(m.group(1))
            sha = self.branches.get(branch)
            if sha:
                return self._json(200, {"ref": f"refs/heads/{branch}", "object": {"sha": sha}})
            return self._json(404, {"message": "Not Found"})

        if path.endswith("/git/refs") and method == "POST":
            name = str(body["ref"]).split("refs/heads/", 1)[-1]
            if name in self.branches:
                return self._json(422, {"message": "Reference already exists"})
            self.branches[name] = str(body["sha"])
            return self._json(201, {"ref": body["ref"], "object": {"sha": body["sha"]}})

        m = re.fullmatch(r"/repos/[^/]+/[^/]+/contents/(.+)", path)
        if m:
            rel = urllib.parse.unquote(m.group(1))
            if method == "GET":
                ref = (params.get("ref") or [""])[0]
                sha = self.files.get((urllib.parse.unquote(ref), rel))
                if sha:
                    return self._json(200, {"path": rel, "sha": sha})
                return self._json(404, {"message": "Not Found"})
            if method == "PUT":
                key = (str(body["branch"]), rel)
                if key in self.files and body.get("sha") != self.files[key]:
                    return self._json(409, {"message": "sha mismatch"})
                self.files[key] = f"sha-{len(self.files) + 1}"
                return self._json(201, {"content": {"path": rel}, "commit": {"sha": "c0ffee"}})

        if path.endswith("/pulls") and method == "POST":
            self.pull_requests.append(dict(body))
            return self._json(
                201,
                {
                    "number": self.pr_number,
                    "html_url": self.pr_url,
                    "state": "open",
                    "head": {"ref": body["head"]},
                    "base": {"ref": body["base"]},
                },
            )

        m = re.fullmatch(r"/repos/[^/]+/[^/]+/pulls/\d+/merge", path)
        if m:
            self.merge_attempts += 1
            return self._json(200, {"merged": True})

        return self._json(500, {"message": f"FakeTransport: unhandled {method} {path}"})
