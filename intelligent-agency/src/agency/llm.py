"""Pluggable LLM backend.

Out of the box the agency uses :class:`MockBackend`, so the whole repo runs
with zero configuration and zero API keys -- perfect for demos and tests.
Set the environment variables below to switch to any OpenAI-compatible
endpoint, including a LOCAL gateway such as OmniRoute:

    AGENCY_LLM=openai
    AGENCY_LLM_BASE_URL=http://127.0.0.1:20128/v1   # e.g. OmniRoute
    AGENCY_LLM_API_KEY=sk-...
    AGENCY_LLM_MODEL=gpt-4o-mini                     # or any routed model
"""
from __future__ import annotations

import os
from typing import Protocol


class LLMBackend(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class MockBackend:
    """Deterministic, offline backend. Explains what the agent *would* do."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        persona = system_prompt.strip().splitlines()[0] if system_prompt else "Agent"
        return (
            f"[mock reply] {persona}\n"
            f"I received your request: {user_prompt!r}.\n"
            "Set AGENCY_LLM=openai (see llm.py) to get real model answers."
        )


class OpenAICompatibleBackend:
    """Calls any OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import json
        import urllib.request

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"]


class LLMConfigError(RuntimeError):
    """Raised when an unattended cycle is started with no real model configured."""


def require_live_backend() -> LLMBackend:
    """Return a non-mock backend, or fail loudly.

    Unattended cycles must not silently run against :class:`MockBackend`: canned
    text looks like autonomous operation in a CI log while doing no reasoning.
    """
    backend = get_backend()
    if isinstance(backend, MockBackend):
        raise LLMConfigError(
            "No live LLM provider configured (AGENCY_LLM unset or 'mock'), so this cycle "
            "would emit canned text. Configure AGENCY_LLM=openai with AGENCY_LLM_API_KEY, "
            "AGENCY_LLM_BASE_URL and AGENCY_LLM_MODEL, or AGENCY_LLM=router with "
            "AGENCY_PRIMARY_* / AGENCY_SECONDARY_* providers. Refusing to run."
        )
    return backend


def get_backend() -> LLMBackend:
    """Build a backend from environment variables.

    ``AGENCY_LLM`` selects the provider:

    - unset or ``mock`` -- :class:`MockBackend` (the development default);
    - ``openai`` -- an OpenAI-compatible endpoint; raises :class:`LLMConfigError`
      when no API key is configured rather than answering with canned mock text;
    - ``router`` -- :class:`~agency.model_router.FallbackBackend` over the
      configured ``AGENCY_PRIMARY_*`` / ``AGENCY_SECONDARY_*`` providers; raises
      when none of them is fully configured. Local Ollama is added only when
      ``AGENCY_ALLOW_LOCAL_OLLAMA`` opts into it, so a router with no real
      provider no longer looks live.

    An unrecognised value raises too: a typo must not silently become mock.
    """
    choice = os.getenv("AGENCY_LLM", "mock").strip().lower()

    if choice in ("", "mock"):
        return MockBackend()

    if choice == "openai":
        base = os.getenv("AGENCY_LLM_BASE_URL", "https://api.openai.com/v1")
        key = os.getenv("AGENCY_LLM_API_KEY", "").strip()
        model = os.getenv("AGENCY_LLM_MODEL", "gpt-4o-mini")
        if not key:
            raise LLMConfigError(
                "AGENCY_LLM=openai is configured but AGENCY_LLM_API_KEY is empty. "
                "Set AGENCY_LLM_API_KEY (plus AGENCY_LLM_BASE_URL / AGENCY_LLM_MODEL "
                "if you are not using the OpenAI defaults), or set AGENCY_LLM=mock to "
                "ask for canned development text explicitly. Refusing to silently fall "
                "back to the mock backend."
            )
        return OpenAICompatibleBackend(base, key, model)

    if choice == "router":
        from .model_router import FallbackBackend

        providers = []

        for prefix, name in (
            ("AGENCY_PRIMARY", "primary"),
            ("AGENCY_SECONDARY", "secondary"),
        ):
            base = os.getenv(f"{prefix}_BASE_URL", "").strip()
            key = os.getenv(f"{prefix}_API_KEY", "").strip()
            model = os.getenv(f"{prefix}_MODEL", "").strip()

            if not (base or key or model):
                continue
            if not (base and key and model):
                raise LLMConfigError(
                    f"AGENCY_LLM=router: the {name} provider is only partially "
                    f"configured. Set {prefix}_BASE_URL, {prefix}_API_KEY and "
                    f"{prefix}_MODEL together, or none of them."
                )
            if not base.startswith("https://"):
                raise ValueError(
                    f"{name} provider requires an HTTPS endpoint"
                )
            providers.append((
                name,
                OpenAICompatibleBackend(base, key, model),
            ))

        if not providers:
            raise LLMConfigError(
                "AGENCY_LLM=router is configured but no real provider is set up "
                "(AGENCY_PRIMARY_BASE_URL / AGENCY_PRIMARY_API_KEY / "
                "AGENCY_PRIMARY_MODEL, or the AGENCY_SECONDARY_* equivalents). "
                "Local Ollama is used only when AGENCY_ALLOW_LOCAL_OLLAMA opts into "
                "it, so refusing to run what would look live but is not."
            )

        if os.getenv("AGENCY_ALLOW_LOCAL_OLLAMA", "").strip().lower() in ("1", "true", "yes"):
            providers.append((
                "ollama",
                OpenAICompatibleBackend(
                    "http://127.0.0.1:11434/v1",
                    "ollama",
                    os.getenv("AGENCY_OLLAMA_MODEL", "qwen2.5:3b"),
                ),
            ))

        return FallbackBackend(providers)

    raise LLMConfigError(
        f"Unknown AGENCY_LLM={choice!r}. Expected 'mock', 'openai' or 'router'. "
        "Refusing to guess a backend."
    )
