"""Tests for the LLM provider guard and the scheduled workflow's provider config.

Background: the 4-hourly workflow pinned ``AGENCY_LLM: mock``, so the only
unattended cycle emitted canned text while looking like autonomous operation.
Now the provider comes from configuration and an unconfigured run fails loudly.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.llm import (  # noqa: E402
    LLMConfigError,
    MockBackend,
    OpenAICompatibleBackend,
    require_live_backend,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "horizon-scheduled.yml"
PROVIDER_VARS = (
    "AGENCY_LLM",
    "AGENCY_LLM_API_KEY",
    "AGENCY_LLM_BASE_URL",
    "AGENCY_LLM_MODEL",
    "AGENCY_PRIMARY_API_KEY",
    "AGENCY_PRIMARY_BASE_URL",
    "AGENCY_PRIMARY_MODEL",
    "AGENCY_SECONDARY_API_KEY",
    "AGENCY_SECONDARY_BASE_URL",
    "AGENCY_SECONDARY_MODEL",
    "AGENCY_ALLOW_LOCAL_OLLAMA",
)


@pytest.fixture()
def clean_env(monkeypatch):
    for var in PROVIDER_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_unconfigured_provider_fails_loudly(clean_env):
    with pytest.raises(LLMConfigError) as excinfo:
        require_live_backend()
    message = str(excinfo.value)
    assert "AGENCY_LLM" in message
    assert "canned text" in message


def test_mock_pin_still_yields_mock_backend_from_get_backend(clean_env):
    # The default path is unchanged; only *unattended* callers must opt in to the guard.
    from agency.llm import get_backend

    assert isinstance(get_backend(), MockBackend)


def test_configured_openai_provider_is_accepted(clean_env):
    clean_env.setenv("AGENCY_LLM", "openai")
    clean_env.setenv("AGENCY_LLM_API_KEY", "sk-test")
    backend = require_live_backend()
    assert isinstance(backend, OpenAICompatibleBackend)
    assert backend.model  # resolved from env/defaults


def test_openai_without_key_fails_loudly(clean_env):
    clean_env.setenv("AGENCY_LLM", "openai")
    with pytest.raises(LLMConfigError):
        require_live_backend()


def test_router_provider_is_accepted(clean_env):
    clean_env.setenv("AGENCY_LLM", "router")
    clean_env.setenv("AGENCY_PRIMARY_BASE_URL", "https://provider.test/v1")
    clean_env.setenv("AGENCY_PRIMARY_API_KEY", "k")
    clean_env.setenv("AGENCY_PRIMARY_MODEL", "m")
    backend = require_live_backend()
    assert not isinstance(backend, MockBackend)
    # Local Ollama is opt-in only, so a router with a real provider does not
    # silently acquire a second, unverified backend.
    assert [name for name, _ in backend.backends] == ["primary"]


def test_router_with_no_real_provider_fails_loudly(clean_env):
    """A router whose only candidate was local Ollama used to 'count as live'
    while in fact running on a local guess. It now refuses."""
    clean_env.setenv("AGENCY_LLM", "router")
    with pytest.raises(LLMConfigError) as excinfo:
        require_live_backend()
    assert "no real provider" in str(excinfo.value)
    assert "AGENCY_ALLOW_LOCAL_OLLAMA" in str(excinfo.value)


def test_router_with_local_ollama_is_refused_unless_opted_in(clean_env):
    from agency.llm import get_backend

    clean_env.setenv("AGENCY_LLM", "router")
    with pytest.raises(LLMConfigError):
        get_backend()
    clean_env.setenv("AGENCY_ALLOW_LOCAL_OLLAMA", "1")
    backend = get_backend()
    assert not isinstance(backend, MockBackend)
    assert [name for name, _ in backend.backends] == ["ollama"]


def test_router_with_a_half_configured_provider_is_refused(clean_env):
    clean_env.setenv("AGENCY_LLM", "router")
    clean_env.setenv("AGENCY_PRIMARY_BASE_URL", "https://provider.test/v1")
    # API key and model missing: do not treat this as configured.
    with pytest.raises(LLMConfigError) as excinfo:
        require_live_backend()
    assert "partially" in str(excinfo.value)


def test_get_backend_raises_when_a_real_provider_is_requested_without_credentials(clean_env):
    from agency.llm import get_backend

    clean_env.setenv("AGENCY_LLM", "openai")
    with pytest.raises(LLMConfigError) as excinfo:
        get_backend()
    assert "AGENCY_LLM_API_KEY" in str(excinfo.value)
    # ...and it did not quietly answer with canned mock text instead.
    clean_env.setenv("AGENCY_LLM_API_KEY", "sk-test")
    assert isinstance(get_backend(), OpenAICompatibleBackend)


def test_get_backend_refuses_an_unknown_provider(clean_env):
    from agency.llm import get_backend

    clean_env.setenv("AGENCY_LLM", "opemai")  # a typo must not become mock
    with pytest.raises(LLMConfigError) as excinfo:
        get_backend()
    assert "Unknown AGENCY_LLM" in str(excinfo.value)


def test_get_backend_still_returns_mock_when_mock_is_asked_for(clean_env):
    from agency.llm import get_backend

    clean_env.setenv("AGENCY_LLM", "mock")
    assert isinstance(get_backend(), MockBackend)


# ------------------------------------------------------- the scheduled workflow
def test_workflow_no_longer_pins_the_mock_backend():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "AGENCY_LLM: mock" not in text
    assert "AGENCY_LLM: ${{ vars.AGENCY_LLM" in text


def test_workflow_guards_with_a_loud_non_zero_exit():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "require_live_backend" in text
    assert "LLMConfigError" in text
    assert "SystemExit(2)" in text


def test_workflow_reads_the_api_key_from_secrets_not_literals():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets.AGENCY_LLM_API_KEY" in text
    assert "sk-" not in text
