import unittest
from unittest.mock import patch

from src.agency.llm import get_backend
from src.agency.model_router import FallbackBackend


class FailedProvider:
    def complete(self, system_prompt, user_prompt):
        raise TimeoutError("Simulated provider timeout")


class WorkingProvider:
    def complete(self, system_prompt, user_prompt):
        return "Successful fallback"


class EmptyProvider:
    def complete(self, system_prompt, user_prompt):
        return ""


class RouterTests(unittest.TestCase):

    def test_fallback_after_timeout(self):
        router = FallbackBackend([
            ("cloud", FailedProvider()),
            ("ollama", WorkingProvider()),
        ])
        self.assertEqual(
            router.complete("system", "user"),
            "Successful fallback",
        )
        self.assertEqual(router.last_provider, "ollama")

    def test_fallback_after_empty_response(self):
        router = FallbackBackend([
            ("cloud", EmptyProvider()),
            ("ollama", WorkingProvider()),
        ])
        self.assertEqual(
            router.complete("system", "user"),
            "Successful fallback",
        )

    def test_all_providers_fail(self):
        router = FallbackBackend([
            ("cloud", FailedProvider()),
        ])
        with self.assertRaises(RuntimeError):
            router.complete("system", "user")

    def test_router_configuration(self):
        with patch.dict(
            "os.environ",
            {
                "AGENCY_LLM": "router",
                "AGENCY_OLLAMA_MODEL": "qwen2.5:3b",
            },
        ):
            backend = get_backend()
            self.assertIsInstance(backend, FallbackBackend)
            self.assertEqual(backend.backends[-1][0], "ollama")


if __name__ == "__main__":
    unittest.main()
