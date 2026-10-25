import unittest
from unittest.mock import patch

from src.agency.llm import LLMConfigError, get_backend
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
                "AGENCY_PRIMARY_BASE_URL": "https://provider.test/v1",
                "AGENCY_PRIMARY_API_KEY": "k",
                "AGENCY_PRIMARY_MODEL": "m",
                # Local Ollama is opt-in only now; without this the router is
                # refused rather than silently dialling 127.0.0.1.
                "AGENCY_ALLOW_LOCAL_OLLAMA": "1",
                "AGENCY_OLLAMA_MODEL": "qwen2.5:3b",
            },
        ):
            backend = get_backend()
            self.assertIsInstance(backend, FallbackBackend)
            self.assertEqual([name for name, _ in backend.backends], ["primary", "ollama"])

    def test_router_without_a_real_provider_is_refused(self):
        # No cloud provider configured and no opt-in: a router that would have
        # run on local Ollama (or nothing) must fail loudly, not look live.
        env = {"AGENCY_LLM": "router", "AGENCY_ALLOW_LOCAL_OLLAMA": ""}
        for prefix in ("AGENCY_PRIMARY", "AGENCY_SECONDARY"):
            for suffix in ("BASE_URL", "API_KEY", "MODEL"):
                env[f"{prefix}_{suffix}"] = ""
        with patch.dict("os.environ", env):
            with self.assertRaises(LLMConfigError) as excinfo:
                get_backend()
            self.assertIn("no real provider", str(excinfo.exception))


if __name__ == "__main__":
    unittest.main()
