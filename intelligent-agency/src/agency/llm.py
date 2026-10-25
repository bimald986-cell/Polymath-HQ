"""Pluggable LLM backend.

Out of the box the agency uses :class:`MockBackend`, so the whole repo runs
with zero configuration and zero API keys -- perfect for demos and tests.
Set the environment variables below to switch to any OpenAI-compatible
endpoint, including a LOCAL gateway such as OmniRoute:

    AGENCY_LLM=openai
    AGENCY_LLM_BASE_URL=http://127.0.0.1:20128/v1   # e.g. OmniRoute
    AGENCY_LLM_API_KEY=sk-...
    AGENCY_LLM_MODEL=gpt-4o-mini                     # or any routed model

Mock is the *development* default and stays available, but it is never reached by
accident: ``AGENCY_LLM=openai`` without a key, an unknown ``AGENCY_LLM`` value, and
``AGENCY_LLM=router`` with no complete real provider all raise ``LLMConfigError``.
A router adds local Ollama only when ``AGENCY_ALLOW_LOCAL_OLLAMA=1`` opts into it.
Unattended callers (``horizon_worker_main``) additionally require a live backend by
default; see ``docs/POLICY_ENGINE.md``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Protocol


def unknown_usage(note: str = "provider response carried no usage envelope") -> Dict[str, Any]:
    """An explicit "we do not know" usage record.

    Token counts are ``None``, never ``0``: a zero would read as a free run and
    silently understate cost, which is the failure mode this is meant to end.
    """
    return {
        "status": "unknown",
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "note": note,
    }


def _token(usage: Dict[str, Any], *names: str):
    for name in names:
        value = usage.get(name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


def extract_usage(data: Any) -> Dict[str, Any]:
    """Read the token counts out of a provider response.

    OpenAI-compatible endpoints report ``usage.prompt_tokens`` /
    ``usage.completion_tokens`` / ``usage.total_tokens``; some compatible
    gateways use the ``input_tokens`` / ``output_tokens`` aliases. Both are
    accepted. A response with no ``usage`` object yields :func:`unknown_usage`
    instead of raising or inventing zeros.
    """
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return unknown_usage()
    prompt_tokens = _token(usage, "prompt_tokens", "input_tokens")
    completion_tokens = _token(usage, "completion_tokens", "output_tokens")
    if prompt_tokens is None and completion_tokens is None:
        return unknown_usage("provider usage envelope had no recognisable token counts")
    total_tokens = _token(usage, "total_tokens")
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "status": "known",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "note": "",
    }


class LLMBackend(Protocol):
    #: Usage of the most recent ``complete()`` call, as :func:`extract_usage`
    #: returns it. Backends that cannot report it must say "unknown".
    last_usage: Dict[str, Any]

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class MockBackend:
    """Deterministic, offline backend. Explains what the agent *would* do."""

    def __init__(self):
        self.last_usage = unknown_usage("mock backend performs no metered work")

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.last_usage = unknown_usage("mock backend performs no metered work")
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
        self.last_usage: Dict[str, Any] = unknown_usage("no call made yet")

    def _request(self, payload: bytes) -> Dict[str, Any]:
        """POST the payload and return the decoded response body.

        Split out so tests can exercise the response handling -- including the
        ``usage`` envelope -- without a network call or a real provider.
        """
        import json
        import urllib.request

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
            return json.loads(resp.read().decode())

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        import json

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }).encode()
        data = self._request(payload)
        self.last_usage = extract_usage(data)
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

        if os.getenv("AGENCY_ALLOW_LOCAL_OLLAMA", "").strip().lower() in ("1", "true", "yes"):
            providers.append((
                "ollama",
                OpenAICompatibleBackend(
                    "http://127.0.0.1:11434/v1",
                    "ollama",
                    os.getenv("AGENCY_OLLAMA_MODEL", "qwen2.5:3b"),
                ),
            ))

        if not providers:
            raise LLMConfigError(
                "AGENCY_LLM=router is configured but no real provider is set up "
                "(AGENCY_PRIMARY_BASE_URL / AGENCY_PRIMARY_API_KEY / "
                "AGENCY_PRIMARY_MODEL, or the AGENCY_SECONDARY_* equivalents). "
                "Local Ollama is used only when AGENCY_ALLOW_LOCAL_OLLAMA opts into "
                "it, so refusing to run what would look live but is not."
            )

        return FallbackBackend(providers)

    raise LLMConfigError(
        f"Unknown AGENCY_LLM={choice!r}. Expected 'mock', 'openai' or 'router'. "
        "Refusing to guess a backend."
    )
