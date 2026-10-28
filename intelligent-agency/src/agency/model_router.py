"""Priority-ordered LLM backends with automatic fallback."""

from __future__ import annotations

import logging
from typing import Any, Dict, Sequence

from .llm import unknown_usage

logger = logging.getLogger(__name__)


class FallbackBackend:
    """Try configured backends in order until one succeeds."""

    def __init__(self, backends: Sequence[tuple[str, object]]):
        if not backends:
            raise ValueError("At least one backend is required")
        self.backends = list(backends)
        self.last_provider: str | None = None
        # Usage of the provider that actually answered; "unknown" until one does.
        self.last_usage: Dict[str, Any] = unknown_usage("no provider has answered yet")
        # The model string of that provider, so a run can be priced by the
        # exact name that served it rather than the first configured one.
        self.last_model: str | None = None

    @property
    def model(self) -> str | None:
        """The model that answered most recently, if the provider names one."""
        return self.last_model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        failures = []

        for name, backend in self.backends:
            try:
                result = backend.complete(system_prompt, user_prompt)
                if not isinstance(result, str) or not result.strip():
                    raise ValueError("Provider returned an empty response")
                self.last_provider = name
                self.last_usage = getattr(backend, "last_usage", None) or unknown_usage()
                model = getattr(backend, "model", None)
                self.last_model = model if isinstance(model, str) and model.strip() else None
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
