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


def get_backend() -> LLMBackend:
    """Build a backend from environment variables (MockBackend by default)."""
    if os.getenv("AGENCY_LLM", "").lower() == "router":
        from .model_router import FallbackBackend

        providers = []

        for prefix, name in (
            ("AGENCY_PRIMARY", "primary"),
            ("AGENCY_SECONDARY", "secondary"),
        ):
            base = os.getenv(f"{prefix}_BASE_URL", "").strip()
            key = os.getenv(f"{prefix}_API_KEY", "").strip()
            model = os.getenv(f"{prefix}_MODEL", "").strip()

            if base and key and model:
                if not base.startswith("https://"):
                    raise ValueError(
                        f"{name} provider requires an HTTPS endpoint"
                    )
                providers.append((
                    name,
                    OpenAICompatibleBackend(base, key, model),
                ))

        providers.append((
            "ollama",
            OpenAICompatibleBackend(
                "http://127.0.0.1:11434/v1",
                "ollama",
                os.getenv("AGENCY_OLLAMA_MODEL", "qwen2.5:3b"),
            ),
        ))

        return FallbackBackend(providers)

    if os.getenv("AGENCY_LLM", "mock").lower() == "openai":
        base = os.getenv("AGENCY_LLM_BASE_URL", "https://api.openai.com/v1")
        key = os.getenv("AGENCY_LLM_API_KEY", "")
        model = os.getenv("AGENCY_LLM_MODEL", "gpt-4o-mini")
        if key:
            return OpenAICompatibleBackend(base, key, model)
    return MockBackend()
