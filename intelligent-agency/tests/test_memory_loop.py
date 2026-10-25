"""The learning loop is closed: memory written by one cycle reaches the next prompt.

Before this, ``StateStore.recall()`` was called only from tests, so every cycle
started from exactly the same static text. These tests assert the fact a cycle
stored is in the *user prompt the model actually receives* on a later cycle --
remove the recall call and they fail.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import PresidentAdvisor
from agency.memory_context import (
    HEADER,
    MAX_CHARS,
    MAX_ENTRIES,
    MAX_ENTRY_CHARS,
    augment_prompt,
    build_recalled_context,
)
from agency.runtime import HorizonRuntime
from agency.state import StateStore
from agency.worker import DurableHorizonWorker


class RecordingBackend:
    """A backend that records exactly what prompt it was handed."""

    def __init__(self, reply="advice"):
        self.reply = reply
        self.calls = []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.reply


def make_worker(tmp_path, backend=None):
    store = StateStore(str(tmp_path / "horizon.db"))
    advisor = PresidentAdvisor(backend=backend or RecordingBackend())
    return DurableHorizonWorker(advisor, store, worker_id="test-worker"), store, advisor


# ------------------------------------------------------- the loop, end to end
def test_a_later_cycle_sees_what_an_earlier_cycle_learned(tmp_path):
    backend = RecordingBackend(reply="FIRST-CYCLE-FINDING-7Q")
    worker, store, _ = make_worker(tmp_path, backend)

    store.enqueue("president_command", {"task": "first task"})
    assert worker.run_one() is True
    first_prompt = backend.calls[-1][1]

    store.enqueue("president_command", {"task": "second task"})
    assert worker.run_one() is True
    second_prompt = backend.calls[-1][1]

    # The first cycle's own prompt had nothing to recall ...
    assert first_prompt == "first task"
    # ... the second cycle's prompt carries what the first one stored.
    assert "FIRST-CYCLE-FINDING-7Q" in second_prompt
    assert "first task" in second_prompt
    assert HEADER in second_prompt
    # The instructions are kept, not replaced.
    assert second_prompt.startswith("second task\n\n")


def test_recalled_memory_is_recorded_as_observable_on_the_run(tmp_path):
    worker, store, _ = make_worker(tmp_path)
    store.enqueue("president_command", {"task": "a"})
    worker.run_one()
    store.enqueue("president_command", {"task": "b"})
    worker.run_one()

    runs = store.recall(scope="horizon/work-results")
    by_task = {r["value"]["task"]: r["value"] for r in runs}
    assert by_task["a"]["recalled_context"] is False
    assert by_task["b"]["recalled_context"] is True


def test_project_scoped_memory_is_selected_for_that_project_only(tmp_path):
    backend = RecordingBackend()
    worker, store, _ = make_worker(tmp_path, backend)
    store.remember(
        "project/sajilo-retail",
        "project/sajilo-retail",
        {"fact": "SAJILO-STOCKOUT-FACT"},
    )
    store.remember(
        "project/astrolab",
        "project/astrolab",
        {"fact": "ASTROLAB-FACT"},
    )

    store.enqueue("president_command", {"task": "scan", "project": "sajilo-retail"})
    worker.run_one()

    prompt = backend.calls[-1][1]
    assert "SAJILO-STOCKOUT-FACT" in prompt
    assert "ASTROLAB-FACT" not in prompt


def test_tagged_memory_is_selected_by_tag(tmp_path):
    backend = RecordingBackend()
    worker, store, _ = make_worker(tmp_path, backend)
    store.remember("lesson/ci", "horizon/lessons", {"fact": "CI-RED-ON-MERGE-REF"})
    store.remember("lesson/video", "horizon/lessons", {"fact": "CAPCUT-SEAM"})

    store.enqueue("president_command", {"task": "look", "tags": ["merge-ref"]})
    worker.run_one()

    prompt = backend.calls[-1][1]
    assert "CI-RED-ON-MERGE-REF" in prompt
    assert "CAPCUT-SEAM" not in prompt


# --------------------------------------------------- no drift when it is empty
def test_prompt_is_byte_identical_when_nothing_was_recalled(tmp_path):
    backend = RecordingBackend()
    worker, store, _ = make_worker(tmp_path, backend)
    store.enqueue("president_command", {"task": "only task"})
    worker.run_one()
    assert backend.calls[-1][1] == "only task"
    assert store.recall(scope="horizon/work-results")[0]["value"]["recalled_context"] is False


def test_augment_prompt_without_a_store_is_a_no_op():
    assert augment_prompt("do the thing", None) == "do the thing"
    assert augment_prompt("do the thing", None, project="x", tags=["y"]) == "do the thing"


def test_empty_store_yields_no_header(tmp_path):
    store = StateStore(str(tmp_path / "h.db"))
    assert build_recalled_context(store) == ""


# ------------------------------------------------------------------- the caps
def test_recalled_context_is_bounded_in_entries_and_characters(tmp_path):
    store = StateStore(str(tmp_path / "h.db"))
    for i in range(40):
        store.remember(f"fact:{i}", "horizon/lessons", {"fact": "F" * 4000})

    context = build_recalled_context(store)

    bullets = [line for line in context.splitlines() if line.startswith("- ")]
    assert len(bullets) <= MAX_ENTRIES
    assert len(context) <= MAX_CHARS
    assert max(len(b) for b in bullets) <= MAX_ENTRY_CHARS + 100  # rendered prefix + ellipsis


# --------------------------------------------------- the runtime path also recalls
def test_horizon_runtime_feeds_memory_into_the_cycle(tmp_path):
    store = StateStore(str(tmp_path / "h.db"))
    store.remember("project/mind-mythos", "project/mind-mythos", {"fact": "PARKED-EPISODE-010"})
    seen = []

    class FakeHorizon:
        def advise(self, task):
            seen.append(task)
            return "ok"

    runtime = HorizonRuntime(
        FakeHorizon(), interval_seconds=60, state_dir=str(tmp_path / "state"), memory=store
    )
    runtime.run_once("scan", project="mind-mythos")
    assert "PARKED-EPISODE-010" in seen[-1]

    # Without memory the runtime behaves exactly as before.
    plain = HorizonRuntime(FakeHorizon(), interval_seconds=60, state_dir=str(tmp_path / "s2"))
    plain.run_once("scan")
    assert seen[-1] == "scan"
