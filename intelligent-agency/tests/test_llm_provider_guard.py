"""Tests for the LLM provider guard and the scheduled workflow's provider config.

Intent, unchanged: an unattended cycle must not silently fabricate reasoning --
canned mock text in a CI log looks like autonomous operation while doing none.

Background: the 4-hourly workflow pinned ``AGENCY_LLM: mock``, so the only
unattended cycle emitted canned text while looking like autonomous operation.
The hard pin was removed and the provider now comes from configuration.

OWNER DECISION (commit 20d65ed, authored by bimald986-cell, on ``main``): the
scheduled cycle is deliberately allowed to fall back to ``mock`` when no
provider is configured, rather than failing the run red. That fallback is the
owner's explicit choice, recorded here so a future reader knows it was decided
and not eroded, and it stays bounded by the tests below: the scheduled workflow
must never pin a real provider and never carry an API key literal, and the
*unattended worker* path (``horizon_worker_main``) must still refuse mock and
exit loudly.
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
WORKER = REPO_ROOT / "intelligent-agency" / "src" / "agency" / "horizon_worker_main.py"
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


def test_scheduled_workflow_falls_back_to_mock_only_when_nothing_is_configured():
    """OWNER DECISION (commit 20d65ed): the scheduled cycle keeps running on the
    mock backend when no provider is configured, instead of failing red.

    This is not a licence to fabricate reasoning silently -- it is bounded. The
    workflow must not pin a *real* provider and must not carry a key literal; the
    producer still selects the provider, and the unattended worker still refuses
    mock (see the two tests below).
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    # The provider is chosen by repository config; 'mock' is only the fallback.
    assert "AGENCY_LLM: ${{ vars.AGENCY_LLM || 'mock' }}" in text
    # ...and it is a fallback, never a hard pin of the mock backend again.
    assert "AGENCY_LLM: mock" not in text
    # A live provider must never be named or keyed in the file itself.
    assert "AGENCY_LLM_API_KEY: ${{ secrets.AGENCY_LLM_API_KEY }}" in text
    assert "sk-" not in text


def test_scheduled_workflow_no_longer_exits_two_on_an_unconfigured_cycle():
    """The loud-exit block was removed by the owner in 20d65ed. Services that
    depended on it must not be assumed to be here -- use the worker guard."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "SystemExit(2)" not in text
    assert "require_live_backend" not in text


def test_unattended_worker_still_refuses_mock():
    """The scheduled workflow's mock fallback does not reach the unattended
    worker. ``horizon_worker_main`` still imports and calls the guard, so a real
    unattended cycle cannot silently fabricate reasoning."""
    text = WORKER.read_text(encoding="utf-8")
    assert "require_live_backend" in text  # imported from agency.llm
    assert "require_live_backend()" in text  # and actually invoked
    assert "return 2" in text  # and the refusal is a non-zero exit, not a warning


def test_unattended_worker_entry_point_exits_two_on_mock(clean_env):
    """Behavioural companion to the text assertions above: the real entry point
    refuses a mock backend and exits non-zero before reaching the cycle."""
    from agency import horizon_worker_main
    clean_env.setenv("AGENCY_LLM", "mock")
    assert horizon_worker_main.main([]) == 2


def test_require_live_backend_still_refuses_an_explicit_mock_pin(clean_env):
    """The guard itself is unchanged: even an explicit ``mock`` is refused."""
    clean_env.setenv("AGENCY_LLM", "mock")
    with pytest.raises(LLMConfigError) as excinfo:
        require_live_backend()
    assert "AGENCY_LLM" in str(excinfo.value)


def test_workflow_reads_the_api_key_from_secrets_not_literals():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets.AGENCY_LLM_API_KEY" in text
    assert "sk-" not in text
