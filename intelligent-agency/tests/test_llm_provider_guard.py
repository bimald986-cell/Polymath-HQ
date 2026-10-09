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


def test_router_with_only_local_ollama_still_counts_as_live(clean_env):
    # The router falls back to local Ollama; that is a real provider, not mock text.
    clean_env.setenv("AGENCY_LLM", "router")
    assert not isinstance(require_live_backend(), MockBackend)


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
