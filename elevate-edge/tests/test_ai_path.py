"""The AI path must be honest: no hidden mock, no env-var health, no fake 200.

Each test here fails if the behaviour it names is reverted (the mutation is given
in the docstring and in the PR body).
"""
from __future__ import annotations

import pytest

import app as elevate


class StubBackend:
    """A provider that counts the requests it receives."""

    def __init__(self, text: str = "A real model answer", model: str = "stub-model"):
        self.text = text
        self.model = model
        self.base_url = "https://provider.invalid/v1"
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


class ExplodingBackend(StubBackend):
    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        raise RuntimeError("HTTP 401 from https://provider.invalid/v1 — internal detail")


@pytest.fixture
def client():
    elevate.app.config.update(TESTING=True)
    try:
        yield elevate.app.test_client()
    finally:
        elevate.app.config.pop("ELEVATE_BACKEND_FACTORY", None)


def use(client, backend):
    elevate.app.config["ELEVATE_BACKEND_FACTORY"] = lambda: backend
    return backend


BULLETS = {"role": "HR Generalist", "notes": "Cut time-to-fill by 20%."}


def test_backend_package_imports_on_a_clean_install():
    """Mutation: drop PyYAML from requirements.txt -> import fails -> this fails."""
    assert elevate._AGENCY_IMPORT_ERROR is None, elevate._AGENCY_IMPORT_ERROR
    assert elevate.get_backend is not None


def test_health_reports_the_backend_that_answers(client):
    """Mutation: report os.environ['AGENCY_LLM'] instead -> 'mock'/'simulation', not 'live'."""
    use(client, StubBackend(model="stub-model"))
    body = client.get("/api/health").get_json()
    assert body["llm_mode"] == "live"
    assert body["model"] == "stub-model"
    assert body["ai"]["live"] is True


def test_health_is_not_fooled_by_the_environment(client, monkeypatch):
    """Mutation: echo env vars (the old bug) -> reports 'openai' while the mock answers."""
    monkeypatch.setenv("AGENCY_LLM", "openai")
    monkeypatch.setenv("AGENCY_LLM_MODEL", "gpt-4o-mini")
    use(client, elevate.MockBackend())
    body = client.get("/api/health").get_json()
    assert body["llm_mode"] == "simulation"
    assert body["model"] == "none"


def test_ai_call_with_no_provider_is_not_a_200(client):
    """Mutation: restore the mock fallback -> 200 with canned text."""
    use(client, elevate.MockBackend())
    resp = client.post("/api/ai/bullets", json=BULLETS)
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["ai_available"] is False
    assert body["analysis_mode"] == "simulation"
    assert "text" not in body


def test_ai_call_with_a_broken_backend_import_is_not_a_200(client, monkeypatch):
    """Mutation: swallow the import error and answer from a local mock -> 200."""
    monkeypatch.setattr(elevate, "get_backend", None)
    monkeypatch.setattr(elevate, "_AGENCY_IMPORT_ERROR", ImportError("No module named 'yaml'"))
    resp = client.post("/api/ai/star", json={"role": "HR", "question": "Q", "notes": "N"})
    assert resp.status_code == 503
    assert resp.get_json()["analysis_mode"] == "unavailable"


def test_ai_call_returns_the_model_text_when_a_provider_answers(client):
    """Mutation: never call the provider -> text missing or the stub records no call."""
    stub = use(client, StubBackend(text="REAL MODEL TEXT"))
    resp = client.post("/api/ai/bullets", json=BULLETS)
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "REAL MODEL TEXT"
    assert len(stub.calls) == 1


def test_provider_failure_is_generic_and_not_a_200(client):
    """Mutation: `return jsonify({'error': str(exc)}), 500` -> the URL leaks to the caller."""
    use(client, ExplodingBackend())
    resp = client.post("/api/ai/bullets", json=BULLETS)
    assert resp.status_code == 502
    body = resp.get_json()
    assert "provider.invalid" not in resp.get_data(as_text=True)
    assert body["error"] == "The AI provider failed. Please try again later."


def test_non_string_fields_are_a_400_not_a_500(client):
    """Mutation: `(data.get('notes') or '').strip()` -> AttributeError -> 500."""
    use(client, StubBackend())
    assert client.post("/api/ai/bullets", json={"notes": 123}).status_code == 400
    assert client.post("/api/ai/star", json={"role": ["a"]}).status_code == 400
