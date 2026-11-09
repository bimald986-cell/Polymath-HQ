"""The dashboard chat runs on the HQ's own path, or says plainly that it cannot.

The defect these tests guard
----------------------------
``dashboard.py`` used to answer ``POST /api/chat`` with its own HTTP call to
``http://127.0.0.1:11434/api/chat``. That call consulted no router, no policy
engine and no audit trail: the turn left no record anywhere, a mock answer was
indistinguishable from a model answer, and the chat only worked at all if Ollama
happened to be running. A user opening the control room could not tell what they
were reading.

What is asserted here
---------------------
1. A chat turn reaches the *configured provider* and leaves the same durable run
   record the rest of the HQ leaves (``runs`` table, ``analysis_mode``, cost).
2. With no provider configured the answer is labelled ``simulation``, the notice
   names the environment variable to set, and the turn is never priced as spend
   or written to durable memory.
3. A mock reply cannot be reported as a live answer even if it carries token
   counts -- classification is by backend, not by usage presence.
4. The dashboard module holds no model transport of its own: no ``urllib``, no
   ``urlopen``, no endpoint constant, and ``do_POST`` calls the shared path.
5. Local Ollama keeps working, but only as a configured provider, through its
   OpenAI-compatible ``/v1`` endpoint -- proven against a local stub.
6. ``cli.py ask`` takes the same path, so the two surfaces cannot drift.

Every test is hermetic: providers are local stub servers on an ephemeral
127.0.0.1 port, or a captured ``urlopen``; state lives in ``tmp_path``.
"""
from __future__ import annotations

import ast
import contextlib
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agency.agent as agent_module  # noqa: E402
import dashboard  # noqa: E402
from agency import chat  # noqa: E402
from agency.llm import (  # noqa: E402
    MockBackend,
    OpenAICompatibleBackend,
    get_backend,
)
from agency.model_router import FallbackBackend  # noqa: E402
from agency.memory_context import HEADER as RECALL_HEADER  # noqa: E402
from agency.runtime import HorizonRuntime  # noqa: E402
from agency.state import StateStore  # noqa: E402

PROVIDER_ENV = (
    "AGENCY_LLM", "AGENCY_LLM_BASE_URL", "AGENCY_LLM_API_KEY", "AGENCY_LLM_MODEL",
    "AGENCY_PRIMARY_BASE_URL", "AGENCY_PRIMARY_API_KEY", "AGENCY_PRIMARY_MODEL",
    "AGENCY_SECONDARY_BASE_URL", "AGENCY_SECONDARY_API_KEY", "AGENCY_SECONDARY_MODEL",
    "AGENCY_ALLOW_LOCAL_OLLAMA", "AGENCY_OLLAMA_MODEL", "HORIZON_DB_PATH",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class _StubProvider:
    """A real local HTTP server standing in for an OpenAI-compatible provider."""

    def __init__(self, answer="STUB ANSWER", usage=None):
        outer = self
        self.requests = []
        self.answer = answer
        self.usage = usage if usage is not None else {
            "prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168,
        }

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append(
                    {"path": self.path, "headers": dict(self.headers), "body": body}
                )
                payload = json.dumps({
                    "choices": [{"message": {"content": outer.answer}}],
                    "usage": outer.usage,
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}/v1"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self.server.shutdown()
        self.server.server_close()
        return False


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self._payload


def _configure_live(monkeypatch, base_url, model="stub-model", key="stub-key"):
    monkeypatch.setenv("AGENCY_LLM", "openai")
    monkeypatch.setenv("AGENCY_LLM_BASE_URL", base_url)
    monkeypatch.setenv("AGENCY_LLM_API_KEY", key)
    monkeypatch.setenv("AGENCY_LLM_MODEL", model)


@contextlib.contextmanager
def _dashboard_server():
    """The real dashboard handler, serving on an ephemeral loopback port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _post_chat(base_url, messages, persona="hq"):
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps({"persona": persona, "messages": messages}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode())


# --------------------------------------------------------------------------
# 1. The live path: configured provider, same run record as everything else.
# --------------------------------------------------------------------------


def test_dashboard_chat_answers_through_the_configured_provider(clean_env, tmp_path):
    """POST /api/chat reaches the provider the environment configures."""
    store_path = tmp_path / "horizon.db"
    clean_env.setenv("HORIZON_DB_PATH", str(store_path))
    with _StubProvider(answer="REAL MODEL ANSWER") as stub:
        _configure_live(clean_env, stub.base_url)
        with _dashboard_server() as base:
            status, body = _post_chat(
                base, [{"role": "user", "content": "What should I work on today?"}]
            )
        assert status == 200, body
        assert body["answer"] == "REAL MODEL ANSWER"
        assert body["analysis_mode"] == "live"
        assert body["model"] == "stub-model"
        assert body["notice"] == ""

        assert len(stub.requests) == 1
        sent = stub.requests[0]
        assert sent["path"] == "/v1/chat/completions"
        assert sent["headers"]["Authorization"] == "Bearer stub-key"
        assert sent["body"]["model"] == "stub-model"
        # The dashboard's own system prompt (persona + project block) is what
        # reaches the model; the routed agent did not replace it.
        assert sent["body"]["messages"][0]["role"] == "system"
        assert dashboard.PROJECT_CONTEXT_HEADER in sent["body"]["messages"][0]["content"]
        assert "What should I work on today?" in sent["body"]["messages"][1]["content"]

    runs = StateStore(str(store_path)).recent_runs()
    assert len(runs) == 1, runs
    run = runs[0]
    assert run["kind"] == chat.CHAT_RUN_KIND
    assert run["analysis_mode"] == "live"
    assert run["status"] == "ok"
    assert run["usage"]["prompt_tokens"] == 123
    assert run["cost"] is not None
    # The price table ships empty on purpose, so a live run is unpriced, not free.
    assert run["cost"]["status"] == "unknown"
    assert run["cost"]["amount"] is None


def test_a_chat_turn_makes_exactly_one_call_to_the_configured_provider(clean_env, tmp_path):
    """No second transport: the only HTTP call is the configured provider's."""
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(request.full_url)
        return _FakeResponse(json.dumps({
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }).encode())

    clean_env.setattr("urllib.request.urlopen", fake_urlopen)
    _configure_live(clean_env, "http://127.0.0.1:9/v1")
    turn = chat.answer_turn("hello", state_path_override=str(tmp_path / "h.db"))
    assert turn.status == "ok", turn.as_dict()
    assert seen == ["http://127.0.0.1:9/v1/chat/completions"], seen


def test_chat_turn_and_runtime_cycle_leave_the_same_kind_of_record(clean_env, tmp_path):
    """One run record for the whole HQ -- a chat turn is a kind, not a new log."""
    store = StateStore(str(tmp_path / "horizon.db"))
    runtime = HorizonRuntime(
        build_horizon(), interval_seconds=3600, state_dir=str(tmp_path / "state"), memory=store
    )
    runtime.run_once("audit the repo")
    chat.answer_turn("hello", store=store)

    runs = store.recent_runs()
    kinds = {run["kind"] for run in runs}
    assert kinds == {"horizon_runtime_cycle", chat.CHAT_RUN_KIND}, kinds
    for run in runs:
        assert run["analysis_mode"] in ("simulation", "live", "unknown")
        assert isinstance(run["cost"], dict) and "status" in run["cost"]


def build_horizon():
    """A President Advisor whose backend is the mock, built without a provider."""
    from agency.loader import build_agency

    return build_agency().advisor


# --------------------------------------------------------------------------
# 2. No provider: labelled simulation, actionable notice, never priced.
# --------------------------------------------------------------------------


def test_no_provider_is_labelled_a_simulation_with_an_actionable_notice(clean_env, tmp_path):
    store_path = tmp_path / "horizon.db"
    clean_env.setenv("HORIZON_DB_PATH", str(store_path))
    with _dashboard_server() as base:
        status, body = _post_chat(base, [{"role": "user", "content": "hello"}])

    assert status == 200, body
    assert body["analysis_mode"] == "simulation"
    assert body["notice"].startswith("SIMULATION")
    assert "AGENCY_LLM" in body["notice"]
    assert "AGENCY_LLM_API_KEY" in body["notice"]
    assert body["answer"].startswith("[mock reply]")
    assert body["model"] is None

    run = StateStore(str(store_path)).recent_runs()[0]
    assert run["analysis_mode"] == "simulation"
    assert run["cost"]["status"] == "unknown"
    assert run["cost"]["amount"] is None


def test_a_mock_reply_cannot_be_labelled_a_real_answer(clean_env, tmp_path):
    """Even a mock that reports token counts stays a simulation and stays unpriced.

    Classification is by backend (``analysis_mode_for``), not by whether a usage
    envelope arrived, so this fails if someone decides "it has token counts, so
    it was a real answer".
    """
    def fake_get_backend():
        backend = MockBackend()
        backend.last_usage = {
            "status": "known", "prompt_tokens": 10, "completion_tokens": 5,
            "total_tokens": 15, "note": "",
        }
        return backend

    clean_env.setattr(agent_module, "get_backend", fake_get_backend)
    store = StateStore(str(tmp_path / "horizon.db"))
    turn = chat.answer_turn("hello", store=store)

    assert turn.analysis_mode == "simulation"
    assert turn.is_live is False
    assert turn.notice.startswith("SIMULATION")
    assert "AGENCY_LLM" in turn.notice
    assert turn.model is None

    run = store.recent_runs()[0]
    assert run["analysis_mode"] == "simulation"
    assert run["cost"]["status"] == "unknown"
    assert run["cost"]["amount"] is None
    # A simulation is never learned from.
    assert store.recall() == []


def test_misconfigured_provider_says_which_variable_and_produces_no_canned_answer(clean_env, tmp_path):
    clean_env.setenv("AGENCY_LLM", "openai")  # no AGENCY_LLM_API_KEY
    turn = chat.answer_turn("hello", state_path_override=str(tmp_path / "h.db"))

    assert turn.status == "error"
    assert turn.analysis_mode != "live"
    assert "AGENCY_LLM_API_KEY" in turn.answer
    assert not turn.answer.startswith("[mock reply]")
    assert turn.notice.startswith("ERROR")


# --------------------------------------------------------------------------
# 3. The dashboard module cannot grow a transport of its own again.
# --------------------------------------------------------------------------


def test_the_dashboard_module_holds_no_model_transport_of_its_own():
    """Structural guard: no HTTP client, no endpoint constant, shared path only."""
    source = Path(dashboard.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "urllib.request" not in imported, "the dashboard must not make HTTP calls"
    assert not imported & {"urllib", "requests", "httpx", "http.client", "socket"}, imported

    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "urlopen" not in called_attrs

    module_constants = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "OLLAMA" not in module_constants, "no hardcoded model endpoint"
    assert "DEFAULT_MODEL" not in module_constants

    do_post = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "do_POST"
    )
    assert "answer_turn" in {
        node.func.attr
        for node in ast.walk(do_post)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }, "POST /api/chat must answer through the shared chat path"


def test_the_dashboard_labels_a_simulation_in_the_ui_not_only_in_the_json():
    """The page itself must not present placeholder text as an answer."""
    assert "SIMULATION" in dashboard.SCRIPT
    assert "placeholder text, not a model answer" in dashboard.SCRIPT


# --------------------------------------------------------------------------
# 4. Memory recall reaches the model, as it does on every other path.
# --------------------------------------------------------------------------


def test_recalled_memory_reaches_the_model_and_is_framed_as_untrusted(clean_env, tmp_path):
    store = StateStore(str(tmp_path / "horizon.db"))
    store.remember(
        "hq/fact-zebra", "hq", {"answer": "ZEBRA-FACT: the pilot starts in March."},
        provenance="test", confidence="high", status="confirmed",
    )
    with _StubProvider() as stub:
        _configure_live(clean_env, stub.base_url)
        turn = chat.answer_turn("what is planned?", store=store)
        assert turn.status == "ok", turn.as_dict()
        user_message = stub.requests[0]["body"]["messages"][1]["content"]
        assert "ZEBRA-FACT" in user_message
        assert RECALL_HEADER in user_message


# --------------------------------------------------------------------------
# 5. Local Ollama: a configured provider, not a second transport.
# --------------------------------------------------------------------------


def test_local_ollama_is_reached_through_its_openai_compatible_endpoint(clean_env, tmp_path):
    """Ollama works because it is configured, on the same transport as any provider."""
    clean_env.setenv("AGENCY_LLM", "router")
    clean_env.setenv("AGENCY_ALLOW_LOCAL_OLLAMA", "1")
    clean_env.setenv("AGENCY_OLLAMA_MODEL", "qwen2.5:3b")

    backend = get_backend()
    assert isinstance(backend, FallbackBackend)
    ollama = dict(backend.backends)["ollama"]
    assert isinstance(ollama, OpenAICompatibleBackend)
    assert ollama.base_url == "http://127.0.0.1:11434/v1"
    assert ollama.model == "qwen2.5:3b"

    # The same transport speaks to a stand-in /v1 endpoint, so the only thing
    # Ollama needs is to be configured -- not a code path of its own.
    with _StubProvider(answer="OLLAMA-STYLE") as stub:
        stub_backend = OpenAICompatibleBackend(stub.base_url, "ollama", "qwen2.5:3b")
        assert stub_backend.complete("sys", "user") == "OLLAMA-STYLE"
        assert stub.requests[-1]["path"] == "/v1/chat/completions"
        # ... and the URL the Ollama provider is configured with is the same
        # shape: base_url + /chat/completions.
        assert ollama.base_url.rstrip("/") + "/chat/completions" == "http://127.0.0.1:11434/v1/chat/completions"


def test_a_router_that_answers_is_classified_live(clean_env, tmp_path):
    """A fallback router is 'live' when the provider that answered is real.

    The router is built in-process rather than from ``AGENCY_PRIMARY_*`` because
    that path deliberately requires an HTTPS endpoint for remote providers (an
    existing guard, untouched here) and the stub is plain HTTP.
    """
    with _StubProvider(answer="ROUTED") as stub:
        fallback = FallbackBackend([
            ("primary", OpenAICompatibleBackend(stub.base_url, "k", "stub-model")),
        ])
        clean_env.setattr(agent_module, "get_backend", lambda: fallback)
        turn = chat.answer_turn("hello", state_path_override=str(tmp_path / "h.db"))
        assert turn.answer == "ROUTED", turn.as_dict()
        assert turn.analysis_mode == "live"
        assert turn.model == "stub-model"
        assert stub.requests[-1]["headers"]["Authorization"] == "Bearer k"


# --------------------------------------------------------------------------
# 6. The CLI takes the same path, so the surfaces cannot drift.
# --------------------------------------------------------------------------


def test_cli_ask_uses_the_same_path_and_records_the_turn(clean_env, tmp_path, capsys):
    import cli

    store_path = tmp_path / "horizon.db"
    clean_env.setenv("HORIZON_DB_PATH", str(store_path))
    with _StubProvider(answer="CLI ANSWER") as stub:
        _configure_live(clean_env, stub.base_url)
        assert cli.main(["ask", "what", "should", "I", "do"]) == 0
        out = capsys.readouterr().out
        assert "CLI ANSWER" in out
        assert "Mode     : live" in out
        assert stub.requests[0]["path"] == "/v1/chat/completions"

    run = StateStore(str(store_path)).recent_runs()[0]
    assert run["kind"] == chat.CHAT_RUN_KIND
    assert run["analysis_mode"] == "live"
