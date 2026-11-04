"""The dashboard must not assert a project state that no artifact supports.

The defect this guards
----------------------
``dashboard.py`` used to hardcode a project glossary that was injected into the
system prompt of *every* dashboard chat call, and that string ended with "For
production 015 scene prompts, ask for its script or scene plan if absent". The
memory capsule this repository ships says the opposite: production stopped at
"Production 010 completed" and the project is parked
(``memory/projects/mind-mythos.md``). Nothing in the repository supports 015, so
the HQ would confidently discuss an episode that does not exist, against a memory
that says production stopped five episodes earlier.

What is asserted here
---------------------
1. The system message the chat call actually builds states **no production number
   that the quoted capsule does not state**. Re-adding "production 015" to the
   prompt chain turns this red.
2. That guard is measured on the real outgoing request payload, not only on a
   helper, so a future edit to ``ollama_chat`` cannot quietly bypass it.
3. The project list and capsule text are derived from ``core/projects.yaml`` and
   ``memory/projects/``. A project that exists only in those files reaches the
   prompt; a hardcoded glossary would fail this.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import dashboard

REPO_ROOT = Path(dashboard.ROOT).resolve().parent
CAPSULE_DIR = REPO_ROOT / "memory" / "projects"
REGISTRY = REPO_ROOT / "core" / "projects.yaml"
MIND_MYTHOS_CAPSULE = CAPSULE_DIR / "mind-mythos.md"

PRODUCTION_NUMBER = re.compile(r"production\s+0*(\d+)", re.IGNORECASE)


def _production_numbers(text: str) -> set:
    """Every ``production N`` / ``Production 0N`` number in ``text``, as ints."""
    return {int(match.group(1)) for match in PRODUCTION_NUMBER.finditer(text or "")}


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        return self._payload


def test_the_capsule_is_the_only_source_of_a_production_number():
    """The guard below is only meaningful if the capsule actually states a number."""
    capsule = MIND_MYTHOS_CAPSULE.read_text(encoding="utf-8")
    assert _production_numbers(capsule) == {10}, capsule


def test_system_prompt_states_no_production_number_the_capsule_does_not():
    capsule = MIND_MYTHOS_CAPSULE.read_text(encoding="utf-8")
    messages = [
        {
            "role": "user",
            "content": "For production 015 scene prompts for Mind & Mythos, what should we do next?",
        }
    ]
    prompt = dashboard.system_prompt("hq", messages)
    # The capsule really was quoted, so this is not passing by quoting nothing.
    assert "mind-mythos.md" in prompt
    assert "Production 010 completed" in prompt
    assert _production_numbers(prompt) <= _production_numbers(capsule), (
        "the injected project context states a production number the memory capsule "
        "does not state; the capsule is the only source of production state"
    )


def test_outgoing_chat_payload_carries_the_same_guarded_system_message(monkeypatch):
    """Measured on the request body, so editing ``ollama_chat`` cannot skip the guard."""
    capsule = MIND_MYTHOS_CAPSULE.read_text(encoding="utf-8")
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps({"message": {"content": "ok"}}).encode("utf-8"))

    monkeypatch.setattr(dashboard.urllib.request, "urlopen", fake_urlopen)
    answer = dashboard.ollama_chat(
        "test-model", "hq", [{"role": "user", "content": "Mind & Mythos production 015?"}]
    )
    assert answer == "ok"
    system = captured["body"]["messages"][0]
    assert system["role"] == "system"
    assert _production_numbers(system["content"]) <= _production_numbers(capsule)


def test_project_context_is_derived_from_the_registry_and_capsule_directory(tmp_path):
    """A project that exists only in the data files must reach the prompt."""
    registry = tmp_path / "projects.yaml"
    registry.write_text(
        "projects:\n"
        "  zebra-labs:\n"
        "    name: Zebra Labs\n"
        "    aliases: [zebra]\n",
        encoding="utf-8",
    )
    capsules = tmp_path / "capsules"
    capsules.mkdir()
    (capsules / "zebra-labs.md").write_text(
        "# Zebra Labs\nCurrent checkpoint: nothing has started.\n", encoding="utf-8"
    )

    mentioned = dashboard.project_context(
        [{"role": "user", "content": "what is happening with zebra this week?"}],
        registry_path=registry,
        capsules_dir=capsules,
    )
    assert "Zebra Labs" in mentioned
    assert "nothing has started" in mentioned

    unmentioned = dashboard.project_context(
        [{"role": "user", "content": "hello, just saying good morning"}],
        registry_path=registry,
        capsules_dir=capsules,
    )
    assert "nothing has started" not in unmentioned
    assert "No project capsule is quoted" in unmentioned


def test_real_registry_and_capsules_are_the_sources_used_by_default():
    """No third hardcoded map: the shipped files themselves drive the prompt."""
    prompt = dashboard.project_context(
        [{"role": "user", "content": "tell me about the portfolio of projects"}]
    )
    assert "mind-mythos.md" not in prompt  # nothing is quoted without a mention
    assert "Mind & Mythos" in prompt  # but the registry's name is in the glossary
    assert REGISTRY.name == "projects.yaml" and REGISTRY.parent.name == "core"
    assert CAPSULE_DIR.is_dir()


@pytest.mark.parametrize("persona", ["hq", "atlas", "horizon"])
def test_every_persona_gets_the_same_project_block(persona):
    prompt = dashboard.system_prompt(persona, [{"role": "user", "content": "Mind & Mythos"}])
    assert dashboard.PROJECT_CONTEXT_HEADER in prompt
    assert dashboard.PROJECT_CONTEXT_FOOTER in prompt
    assert "mind-mythos.md" in prompt
