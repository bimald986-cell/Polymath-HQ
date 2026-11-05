"""``http_get_allowlisted``: the tool the ``research`` authority names.

Every test here is hermetic — the only network peer is an HTTP server this file
starts on ``127.0.0.1`` — so CI needs no internet access and cannot pass by
accident.

The tests are written to be able to fail:

* deleting the allowlist check makes the refusal tests red;
* deleting the redirect check makes the redirect test red;
* sending an ``Authorization`` header makes the no-credentials test red;
* removing the byte cap or the timeout makes the bound tests red.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import public_api  # noqa: E402
from agency.advisor import Authority, _ACTION_TO_TOOL  # noqa: E402
from agency.builtin_tools import default_registry  # noqa: E402
from agency.policy import default_engine  # noqa: E402
from agency.public_api import (  # noqa: E402
    AllowlistError,
    ToolNetworkError,
    fetch,
    load_allowlist,
)
from agency.tools import ToolDispatcher  # noqa: E402


# ----------------------------------------------------------------- local server
class _Recorder:
    """What the server actually received, so the test can inspect real headers."""

    def __init__(self):
        self.requests = []

    def last(self):
        assert self.requests, "the server received no request"
        return self.requests[-1]


class _Handler(BaseHTTPRequestHandler):
    recorder = None  # set per fixture
    body = b'{"answer": 42}'
    slow_seconds = 0.0
    big_body_bytes = 0
    redirect_to = None
    redirect_from = "/start"

    def do_GET(self):  # noqa: N802 - the BaseHTTPRequestHandler API
        self.__class__.recorder.requests.append(
            {
                "path": self.path,
                "headers": {key: value for key, value in self.headers.items()},
            }
        )
        if self.redirect_to and self.path == self.redirect_from:
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.slow_seconds:
            time.sleep(self.slow_seconds)
        body = self.body
        if self.big_body_bytes:
            body = b"x" * self.big_body_bytes
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the test output clean
        pass


@pytest.fixture
def server():
    recorder = _Recorder()

    class Handler(_Handler):
        pass

    Handler.recorder = recorder
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, recorder, Handler
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _allowlist(tmp_path: Path, *base_urls: str) -> Path:
    path = tmp_path / "allowlist.yaml"
    entries = "".join(
        f"  - id: endpoint_{index}\n"
        f"    name: Endpoint {index}\n"
        f"    base_url: \"{base_url}\"\n"
        f"    category: test\n"
        f"    auth: none\n"
        f"    status: candidate\n"
        for index, base_url in enumerate(base_urls)
    )
    path.write_text(
        "version: 1\n"
        "rules:\n"
        "  - prose rules grant nothing\n"
        "endpoints:\n" + entries + "disabled_by_default:\n  - Any endpoint not listed above\n",
        encoding="utf-8",
    )
    return path


# ------------------------------------------------------- refusal before network
def test_a_host_not_on_the_allowlist_is_refused_before_any_network_call(tmp_path, monkeypatch):
    allowlist = _allowlist(tmp_path, "https://api.frankfurter.app")
    opened = []
    monkeypatch.setattr(
        public_api.urllib.request.OpenerDirector,
        "open",
        lambda *args, **kwargs: opened.append(args),
    )

    with pytest.raises(AllowlistError) as excinfo:
        fetch("https://not-allowlisted.example/secret", allowlist_path=allowlist)

    message = str(excinfo.value)
    assert "not-allowlisted.example" in message  # names the host
    assert str(allowlist) in message  # names the allowlist
    assert opened == [], "a refused host must not reach the network at all"


def test_a_redirect_to_a_host_that_is_not_allowlisted_is_refused(tmp_path, server):
    httpd, recorder, handler = server
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    handler.redirect_to = "http://evil.example/collected"
    try:
        with pytest.raises(AllowlistError) as excinfo:
            fetch(f"http://127.0.0.1:{httpd.server_port}/start", allowlist_path=allowlist)
    finally:
        handler.redirect_to = None
    assert "evil.example" in str(excinfo.value)
    assert recorder.last()["path"] == "/start"  # the redirect target was never requested


def test_a_redirect_to_an_allowlisted_url_is_followed(tmp_path, server):
    httpd, recorder, handler = server
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    handler.redirect_to = f"http://127.0.0.1:{httpd.server_port}/final"
    try:
        result = fetch(f"http://127.0.0.1:{httpd.server_port}/start", allowlist_path=allowlist)
    finally:
        handler.redirect_to = None
    assert result["status"] == 200
    assert result["final_url"].endswith("/final")
    assert [entry["path"] for entry in recorder.requests] == ["/start", "/final"]


# -------------------------------------------------------------- hermetic success
def test_hermetic_successful_fetch_returns_the_body_as_text(tmp_path, server):
    httpd, recorder, handler = server
    handler.body = b'{"rate": 1.23, "source": "test-server"}'
    allowlist = _allowlist(tmp_path, f"http://127.0.0.1:{httpd.server_port}")

    result = fetch(f"http://127.0.0.1:{httpd.server_port}/rates", allowlist_path=allowlist)

    assert result["status"] == 200
    assert json.loads(result["text"]) == {"rate": 1.23, "source": "test-server"}
    assert result["truncated"] is False
    assert result["allowlisted_endpoint"] == "endpoint_0"
    assert recorder.last()["path"] == "/rates"


def test_nothing_is_written_to_disk(tmp_path, server, monkeypatch):
    httpd, _recorder, _handler = server
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    fetch(f"http://127.0.0.1:{httpd.server_port}/rates", allowlist_path=allowlist)

    assert list(workdir.iterdir()) == []


# ------------------------------------------------------- allowlist failure modes
def test_a_missing_allowlist_refuses_everything(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(
        public_api.urllib.request.OpenerDirector,
        "open",
        lambda *args, **kwargs: opened.append(args),
    )
    with pytest.raises(AllowlistError) as excinfo:
        fetch("http://127.0.0.1:1/anything", allowlist_path=tmp_path / "does-not-exist.yaml")
    assert "missing or unreadable" in str(excinfo.value)
    assert opened == []


def test_a_malformed_allowlist_refuses_everything(tmp_path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("endpoints: [ {this is: not, valid: yaml\n", encoding="utf-8")
    with pytest.raises(AllowlistError):
        load_allowlist(broken)

    shapeless = tmp_path / "shapeless.yaml"
    shapeless.write_text("version: 1\nrules:\n  - no endpoints key at all\n", encoding="utf-8")
    with pytest.raises(AllowlistError) as excinfo:
        load_allowlist(shapeless)
    assert "endpoints" in str(excinfo.value)


def test_an_allowlist_with_no_usable_endpoint_refuses_everything(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text(
        "version: 1\nendpoints:\n  - id: broken\n    base_url: \"not a url\"\n", encoding="utf-8"
    )
    with pytest.raises(AllowlistError):
        load_allowlist(path)


def test_the_env_var_selects_the_allowlist(tmp_path, server, monkeypatch):
    httpd, _recorder, _handler = server
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    monkeypatch.setenv(public_api.ALLOWLIST_ENV, str(allowlist))
    assert public_api.allowlist_path_from_env() == allowlist
    result = fetch(f"http://127.0.0.1:{httpd.server_port}/x")
    assert result["status"] == 200


# ------------------------------------------------------------------- bounds
def test_the_response_size_cap_is_enforced(tmp_path, server):
    httpd, _recorder, handler = server
    handler.big_body_bytes = 50_000
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    try:
        result = fetch(
            f"http://127.0.0.1:{httpd.server_port}/big", allowlist_path=allowlist, max_bytes=100
        )
    finally:
        handler.big_body_bytes = 0
    assert result["truncated"] is True
    assert result["returned_bytes"] == 100
    assert len(result["text"]) == 100


def test_the_time_cap_is_enforced(tmp_path, server):
    httpd, _recorder, handler = server
    handler.slow_seconds = 2.0
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    started = time.monotonic()
    try:
        with pytest.raises(ToolNetworkError) as excinfo:
            fetch(
                f"http://127.0.0.1:{httpd.server_port}/slow",
                allowlist_path=allowlist,
                timeout=0.3,
            )
    finally:
        handler.slow_seconds = 0.0
    elapsed = time.monotonic() - started
    assert "timed out" in str(excinfo.value)
    assert elapsed < 2.0, f"the timeout did not bound the request (took {elapsed:.1f}s)"


# --------------------------------------------------------------- no credentials
def test_no_credential_header_or_environment_secret_is_sent(tmp_path, server, monkeypatch):
    httpd, recorder, handler = server
    handler.body = b"ok"
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    secrets = {
        "GITHUB_TOKEN": "ghp_do_not_leak_me",
        "AGENCY_LLM_API_KEY": "sk-do-not-leak-me",
        "HORIZON_API_TOKEN": "horizon-secret-value",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)

    fetch(f"http://127.0.0.1:{httpd.server_port}/rates", allowlist_path=allowlist)

    headers = recorder.last()["headers"]
    lowered = {name.casefold(): value for name, value in headers.items()}
    for forbidden in ("authorization", "proxy-authorization", "cookie", "x-api-key"):
        assert forbidden not in lowered, f"{forbidden} was sent: {headers}"
    for name, value in secrets.items():
        for header, sent in headers.items():
            assert value not in str(sent), f"{name} leaked into header {header}"
    assert "PolymathHQ-ResearchTool" in headers.get("User-Agent", "")


def test_a_url_carrying_credentials_is_refused(tmp_path):
    allowlist = _allowlist(tmp_path, "http://127.0.0.1")
    with pytest.raises(AllowlistError) as excinfo:
        fetch("http://user:pass@127.0.0.1/x", allowlist_path=allowlist)
    assert "credentials" in str(excinfo.value)


# --------------------------------------------------- reachable and registered
def test_the_research_authority_now_names_a_tool_that_exists(tmp_path):
    """``advisor.py:49`` maps the authority to ``http_get_allowlisted``; it exists."""
    assert Authority().research is True
    assert _ACTION_TO_TOOL["research"] == "http_get_allowlisted"
    registry = default_registry(tmp_path)
    assert "http_get_allowlisted" in registry
    spec = registry.resolve("http_get_allowlisted").spec()
    assert spec["risk"] == "network"
    assert spec["parameters"]["required"] == ["url"]
    assert spec["parameters"]["properties"]["timeout_seconds"]["maximum"] == public_api.MAX_TIMEOUT


def test_the_tool_runs_through_the_policy_gate_and_reports_a_refusal(tmp_path, monkeypatch):
    allowlist = _allowlist(tmp_path, "https://api.frankfurter.app")
    monkeypatch.setenv(public_api.ALLOWLIST_ENV, str(allowlist))
    dispatcher = ToolDispatcher(default_registry(tmp_path), default_engine(), actor="horizon")

    result = dispatcher.dispatch(
        "http_get_allowlisted", {"url": "https://not-allowlisted.example/x"}
    )

    assert result.ok is False
    assert result.denied is False  # policy allowed it; the allowlist refused it
    assert result.risk == "network"
    assert result.decision["allowed"] is True
    assert "not-allowlisted.example" in result.error


def test_the_tool_refuses_an_argument_it_cannot_honour(tmp_path, monkeypatch):
    allowlist = _allowlist(tmp_path, "https://api.frankfurter.app")
    monkeypatch.setenv(public_api.ALLOWLIST_ENV, str(allowlist))
    dispatcher = ToolDispatcher(default_registry(tmp_path), default_engine(), actor="horizon")

    result = dispatcher.dispatch(
        "http_get_allowlisted", {"url": "https://api.frankfurter.app/x", "timeout_seconds": 9999}
    )

    assert result.ok is False
    assert "timeout_seconds" in result.error


def test_the_shipped_allowlist_parses_and_grants_hosts():
    """The real file is the one that decides; it must stay loadable."""
    endpoints = load_allowlist(public_api.DEFAULT_ALLOWLIST_PATH)
    assert endpoints, "the shipped allowlist must list at least one endpoint"
    hosts = {endpoint.host for endpoint in endpoints}
    assert "api.frankfurter.app" in hosts
