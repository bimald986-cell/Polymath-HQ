"""``http_get_allowlisted`` — the one real research tool.

Why this module exists
----------------------
``advisor.py:20`` grants Horizon a ``research`` authority and ``:49`` maps it to the
tool id ``http_get_allowlisted``; ``policy.py:48`` declares that id as a ``NETWORK``
risk. Until this module, no such tool existed: the registry held exactly two tools
(``read_file``, ``run_tests``), so an authority pointed at a capability that had
never been implemented, and ``core/public_api_allowlist.yaml`` was read by no
runtime code at all.

What it does, and what it refuses
---------------------------------
* **GET only.** Any other method is not implemented here; the request is built with
  no body and no method argument.
* **The allowlist decides.** Allowed hosts come from ``endpoints[].base_url`` in
  ``core/public_api_allowlist.yaml`` (default path; override with the
  ``HORIZON_PUBLIC_API_ALLOWLIST`` environment variable). A host that is not listed
  is refused **before any network call**, with a message naming the host and the
  allowlist file. A redirect is followed only when its target is allowed too.
* **A missing or malformed allowlist allows nothing.** There is no allow-all
  fallback: if the file cannot be read or has no usable endpoint, every request is
  refused.
* **No credentials of any kind.** No ``Authorization``, ``Cookie`` or proxy
  credentials are ever sent: the request carries only ``User-Agent`` and ``Accept``,
  environment proxies are disabled (a proxy URL can carry credentials), and nothing
  reads a token from the environment.
* **Bounded.** The body is read up to ``max_bytes`` (default
  :data:`MAX_RESPONSE_BYTES`), the socket is given a timeout, and nothing is written
  to disk — the body is returned to the caller as text.

The allowlist file's actual shape (as read on ``main`` at ``61d4e10``) is::

    version: 1
    updated: "2026-09-28"
    rules: [ ...prose rules... ]
    endpoints:
      - id: exchangerate_host
        name: ExchangeRate.host
        base_url: "https://api.exchangerate.host"
        category: currency
        auth: none
        rate_limit: ...
        use_for: [ratebridge_research]
        status: candidate
        notes: ...
    disabled_by_default: [ ...prose... ]

Only ``endpoints[].base_url`` grants access. ``rules`` and ``disabled_by_default``
are prose for humans; ``status``/``auth``/``rate_limit`` are metadata this tool does
not interpret. An endpoint whose ``base_url`` names an explicit port restricts the
tool to that port; one without a port allows any port on that host.
"""
from __future__ import annotations

import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .policy import ToolRisk
from .tools import Tool, ToolError

#: Environment variable naming an alternative allowlist file.
ALLOWLIST_ENV = "HORIZON_PUBLIC_API_ALLOWLIST"

#: The allowlist that ships with the HQ (``<repo>/core/public_api_allowlist.yaml``).
DEFAULT_ALLOWLIST_PATH = Path(__file__).resolve().parents[3] / "core" / "public_api_allowlist.yaml"

MAX_RESPONSE_BYTES = 200_000
DEFAULT_TIMEOUT = 10
MAX_TIMEOUT = 60
MAX_REDIRECTS = 5

#: The only headers this tool ever sends. Deliberately no Authorization/Cookie.
REQUEST_HEADERS = {
    "User-Agent": "PolymathHQ-ResearchTool/1.0 (+https://github.com/bimald986-cell/Polymath-HQ)",
    "Accept": "text/plain, text/html, application/json;q=0.9, */*;q=0.5",
}
ALLOWED_SCHEMES = ("http", "https")


class AllowlistError(ToolError):
    """A request refused because the allowlist does not permit it."""


class ToolNetworkError(ToolError):
    """A request that was allowed but could not be completed."""


@dataclass(frozen=True)
class Endpoint:
    """One allowlisted endpoint: the host (and optional port) it grants."""

    id: str
    name: str
    host: str
    port: Optional[int]
    base_url: str

    def allows(self, host: str, port: Optional[int]) -> bool:
        if host.casefold() != self.host.casefold():
            return False
        if self.port is None:
            return True
        return port == self.port


def allowlist_path_from_env() -> Path:
    """``HORIZON_PUBLIC_API_ALLOWLIST`` when set, else the shipped allowlist."""
    raw = os.getenv(ALLOWLIST_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_ALLOWLIST_PATH


def load_allowlist(path: Optional[os.PathLike | str] = None) -> List[Endpoint]:
    """Parse the allowlist. A file that cannot be used raises :class:`AllowlistError`.

    There is deliberately no "empty allowlist means allow everything" path: a
    missing, unreadable, malformed or endpoint-less file allows nothing.
    """
    target = Path(path).expanduser() if path is not None else allowlist_path_from_env()
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AllowlistError(
            f"public API allowlist {target} is missing or unreadable ({exc.strerror or exc}); "
            "refusing every request, because an allowlist that cannot be read allows nothing"
        ) from None
    except yaml.YAMLError as exc:
        raise AllowlistError(
            f"public API allowlist {target} is not valid YAML ({exc}); "
            "refusing every request, because an allowlist that cannot be parsed allows nothing"
        ) from None

    if not isinstance(raw, dict):
        raise AllowlistError(
            f"public API allowlist {target} has no top-level mapping; refusing every request"
        )
    entries = raw.get("endpoints")
    if not isinstance(entries, list):
        raise AllowlistError(
            f"public API allowlist {target} has no `endpoints:` list; refusing every request"
        )

    endpoints: List[Endpoint] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        base_url = str(entry.get("base_url") or "").strip()
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
            continue
        try:
            port = parsed.port
        except ValueError:  # a malformed port grants nothing
            continue
        endpoints.append(
            Endpoint(
                id=str(entry.get("id") or base_url),
                name=str(entry.get("name") or entry.get("id") or base_url),
                host=parsed.hostname,
                port=port,
                base_url=base_url,
            )
        )

    if not endpoints:
        raise AllowlistError(
            f"public API allowlist {target} lists no usable http(s) endpoint; "
            "refusing every request"
        )
    return endpoints


def _match_endpoint(url: str, endpoints: List[Endpoint], target: Path) -> Endpoint:
    """The allowlisted endpoint covering ``url``, or :class:`AllowlistError`."""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        raise AllowlistError(
            f"refusing GET {url!r}: the port is malformed. Allowed hosts are defined in {target}."
        ) from None
    for endpoint in endpoints:
        if endpoint.allows(host, port):
            return endpoint
    allowed = ", ".join(sorted({f"{e.host}{f':{e.port}' if e.port else ''}" for e in endpoints}))
    raise AllowlistError(
        f"refusing GET {url!r}: host {host!r} is not on the public API allowlist {target} "
        f"(allowed hosts: {allowed or '<none>'})"
    )


def _validate_url(url: str) -> str:
    """Reject anything that is not a plain, credential-free http(s) URL."""
    if not isinstance(url, str) or not url.strip():
        raise AllowlistError("url must be a non-empty string")
    candidate = url.strip()
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise AllowlistError(
            f"refusing {candidate!r}: only http and https URLs can be fetched (got scheme {parsed.scheme or '<none>'!r})"
        )
    if not parsed.hostname:
        raise AllowlistError(f"refusing {candidate!r}: it has no host")
    if parsed.username or parsed.password:
        raise AllowlistError(
            f"refusing {candidate!r}: credentials in a URL are not accepted; this tool never authenticates"
        )
    return candidate


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when the new URL is allowed too."""

    def __init__(self, endpoints: List[Endpoint], target: Path):
        super().__init__()
        self.endpoints = endpoints
        self.target = target
        self.max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _match_endpoint(newurl, self.endpoints, self.target)  # raises AllowlistError
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(endpoints: List[Endpoint], target: Path) -> urllib.request.OpenerDirector:
    """An opener that follows only allowlisted redirects and uses no proxy credentials."""
    return urllib.request.build_opener(
        _AllowlistRedirectHandler(endpoints, target),
        # An environment proxy URL may carry credentials; this tool sends none.
        urllib.request.ProxyHandler({}),
    )


def fetch(
    url: str,
    *,
    allowlist_path: Optional[os.PathLike | str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> Dict[str, Any]:
    """GET an allowlisted URL and return its body as text. Writes nothing to disk."""
    candidate = _validate_url(url)
    target = Path(allowlist_path).expanduser() if allowlist_path is not None else allowlist_path_from_env()
    endpoints = load_allowlist(target)
    endpoint = _match_endpoint(candidate, endpoints, target)  # refuses before any network call

    limit = int(max_bytes)
    if limit < 1:
        raise ToolNetworkError("max_bytes must be >= 1")
    wait = float(timeout)
    if wait <= 0 or wait > MAX_TIMEOUT:
        raise ToolNetworkError(f"timeout must be > 0 and <= {MAX_TIMEOUT} seconds, got {timeout!r}")

    request = urllib.request.Request(candidate, headers=dict(REQUEST_HEADERS), method="GET")
    opener = _opener(endpoints, target)
    try:
        with opener.open(request, timeout=wait) as response:
            status = getattr(response, "status", None) or response.getcode()
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(limit + 1)
    except AllowlistError:
        raise
    except urllib.error.HTTPError as exc:
        raise ToolNetworkError(f"HTTP {exc.code} from {candidate}") from None
    except socket.timeout:
        raise ToolNetworkError(f"request to {candidate} timed out after {wait:g}s") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout) or "timed out" in str(reason):
            raise ToolNetworkError(f"request to {candidate} timed out after {wait:g}s") from None
        raise ToolNetworkError(f"request to {candidate} failed: {reason}") from None
    except OSError as exc:
        raise ToolNetworkError(f"request to {candidate} failed: {exc}") from None

    truncated = len(raw) > limit
    body = raw[:limit]
    charset = _charset_from(content_type)
    return {
        "url": candidate,
        "final_url": final_url,
        "status": status,
        "allowlisted_endpoint": endpoint.id,
        "content_type": content_type,
        "bytes": len(body),
        "returned_bytes": len(body),
        "truncated": truncated,
        "text": body.decode(charset, errors="replace"),
    }


def _charset_from(content_type: str) -> str:
    for part in (content_type or "").split(";")[1:]:
        key, _, value = part.partition("=")
        if key.strip().casefold() == "charset" and value.strip():
            return value.strip().strip('"') or "utf-8"
    return "utf-8"


# ---------------------------------------------------------------- declarations
HTTP_GET_PARAMETERS: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": (
                "Absolute http(s) URL. Its host must be listed in core/public_api_allowlist.yaml; "
                "anything else is refused before a network call."
            ),
        },
        "timeout_seconds": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_TIMEOUT,
            "description": f"Hard wall-clock limit for the request (default {DEFAULT_TIMEOUT}).",
        },
        "max_bytes": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_RESPONSE_BYTES,
            "description": f"Body cap in bytes (default and maximum {MAX_RESPONSE_BYTES}).",
        },
    },
    "required": ["url"],
}


def http_get_allowlisted_tool(allowlist_path: Optional[os.PathLike | str] = None) -> Tool:
    """The ``http_get_allowlisted`` tool, bound to one allowlist file."""
    bound = Path(allowlist_path).expanduser() if allowlist_path is not None else None

    def executor(
        url: str,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> Dict[str, Any]:
        return fetch(
            url,
            allowlist_path=bound if bound is not None else allowlist_path_from_env(),
            timeout=timeout_seconds,
            max_bytes=max_bytes,
        )

    return Tool(
        name="http_get_allowlisted",
        description=(
            "GET a URL whose host is on the public API allowlist. Read-only, no credentials, "
            "bounded by timeout and byte cap, nothing written to disk."
        ),
        parameters=HTTP_GET_PARAMETERS,
        risk=ToolRisk.NETWORK,
        executor=executor,
        tags=("network", "research", "read"),
    )
