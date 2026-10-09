"""Priority-ordered LLM backends with automatic fallback."""

from __future__ import annotations

import logging
from typing import Sequence

logger = logging.getLogger(__name__)


class FallbackBackend:
    """Try configured backends in order until one succeeds."""

    def __init__(self, backends: Sequence[tuple[str, object]]):
        if not backends:
            raise ValueError("At least one backend is required")
        self.backends = list(backends)
        self.last_provider: str | None = None

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        failures = []

        for name, backend in self.backends:
            try:
                result = backend.complete(system_prompt, user_prompt)
                if not isinstance(result, str) or not result.strip():
                    raise ValueError("Provider returned an empty response")
                self.last_provider = name
                logger.info("LLM provider succeeded: %s", name)
                return result
            except Exception as exc:
                logger.warning(
                    "LLM provider %s failed: %s",
                    name,
                    type(exc).__name__,
                )
                failures.append(name)

        raise RuntimeError(
            "All configured LLM providers failed: "
            + ", ".join(failures)
        )
