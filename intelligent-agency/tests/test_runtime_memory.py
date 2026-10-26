"""The runtime records its own cycle, so the *next* cycle starts from it.

Before this, only ``Worker`` ever called ``StateStore.remember`` -- the runtime
read memory (``runtime.py`` ``augment_prompt``) and never wrote it, so a
store-backed ``HorizonRuntime`` recalled nothing it had done itself.

These tests assert the fact in the prompt the model actually receives, so
deleting the recording write (``HorizonRuntime._remember_cycle``) turns them
red. Verified by mutation: commenting out that call fails
``test_second_cycle_prompt_contains_first_cycles_answer`` and
``test_cycle_records_are_bounded_in_their_own_scope``.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.memory_context import HEADER
from agency.model_router import FallbackBackend
from agency.runtime import MEMORY_SCOPE, MEMORY_WINDOW, HorizonRuntime
from agency.state import StateStore


class RecordingProvider:
    """Offline provider stub used to exercise the runtime's live-response path."""

    def __init__(self):
        self.prompts = []
        self.last_usage = {"status": "known", "prompt_tokens": 123,
                           "completion_tokens": 45, "total_tokens": 168}

    def complete(self, system_prompt, user_prompt):
        self.prompts.append(user_prompt)
        return f"FINDING-{len(self.prompts)}: the queue is empty"


class RecordingHorizon:
    """Records prompts and routes them through a deterministic provider stub."""

    def __init__(self):
        self.prompts = []
        self.provider = RecordingProvider()
        self.backend = FallbackBackend([("test-provider", self.provider)])
        self.last_usage = self.provider.last_usage

    def advise(self, task):
        self.prompts.append(task)
        return self.backend.complete("test system", task)


class BrokenStore:
    """A store whose write fails, to prove a failed record is not reported ok."""

    def recall(self, *args, **kwargs):
        return []

    def remember(self, *args, **kwargs):
        raise RuntimeError("disk full")


def test_second_cycle_prompt_contains_first_cycles_answer(tmp_path):
    horizon = RecordingHorizon()
    store = StateStore(str(tmp_path / "horizon.db"))
    runtime = HorizonRuntime(horizon, interval_seconds=60,
                             state_dir=str(tmp_path), memory=store)

    first = runtime.run_once("scan HQ")
    second = runtime.run_once("scan HQ")

    # Cycle 1 started cold: the prompt is the bare task, no recall block.
    assert first["cycle"] == "1"
    assert HEADER not in horizon.prompts[0]
    # Cycle 2's outgoing prompt carries what cycle 1 recorded.
    assert HEADER in horizon.prompts[1]
    assert "FINDING-1: the queue is empty" in horizon.prompts[1]
    assert second["cycle"] == "2"


def test_recalled_prompt_is_byte_identical_without_a_store(tmp_path):
    """The read side is unchanged: no store, no memory, no extra text."""
    horizon = RecordingHorizon()
    runtime = HorizonRuntime(horizon, interval_seconds=60, state_dir=str(tmp_path))

    runtime.run_once("scan HQ")
    runtime.run_once("scan HQ")

    assert horizon.prompts == ["scan HQ", "scan HQ"]


def test_cycle_records_are_bounded_in_their_own_scope(tmp_path):
    """Recording never grows past MEMORY_WINDOW rows, and stays out of work-results."""
    horizon = RecordingHorizon()
    store = StateStore(str(tmp_path / "horizon.db"))
    store.remember("work:1", "horizon/work-results", {"task": "t", "answer": "a"})
    runtime = HorizonRuntime(horizon, interval_seconds=60,
                             state_dir=str(tmp_path), memory=store)

    for _ in range(MEMORY_WINDOW + 2):
        runtime.run_once("scan HQ")

    rows = store.recall(scope=MEMORY_SCOPE, limit=100)
    assert len(rows) == MEMORY_WINDOW
    # The newest cycle is still the one that was just written.
    assert max(row["value"]["cycle"] for row in rows) == MEMORY_WINDOW + 2
    # The worker's own memory is untouched by the runtime's writes.
    work = store.recall(scope="horizon/work-results", limit=100)
    assert len(work) == 1 and work[0]["key"] == "work:1"


def test_recorded_cycle_carries_usage_and_task(tmp_path):
    horizon = RecordingHorizon()
    store = StateStore(str(tmp_path / "horizon.db"))
    runtime = HorizonRuntime(horizon, interval_seconds=60,
                             state_dir=str(tmp_path), memory=store)

    runtime.run_once("scan HQ")

    (row,) = store.recall(scope=MEMORY_SCOPE)
    assert row["value"]["task"] == "scan HQ"
    assert row["value"]["cycle"] == 1
    assert row["value"]["usage"]["total_tokens"] == 168
    assert row["value"]["finished_at"]


def test_cycle_number_survives_a_new_process(tmp_path):
    """A scheduled run is one process per cycle.

    The storage has to be the source of the cycle number: if the runtime used
    its own per-process counter, every CI run would record ``cycle: 1`` and
    overwrite the same row forever instead of rotating through the window.
    """
    db = str(tmp_path / "horizon.db")
    HorizonRuntime(RecordingHorizon(), interval_seconds=60, state_dir=str(tmp_path),
                   memory=StateStore(db)).run_once("scan HQ")
    # A second runtime and a second store handle, as the next scheduled run has.
    HorizonRuntime(RecordingHorizon(), interval_seconds=60, state_dir=str(tmp_path),
                   memory=StateStore(db)).run_once("scan HQ")

    rows = StateStore(db).recall(scope=MEMORY_SCOPE, limit=10)
    assert sorted(row["value"]["cycle"] for row in rows) == [1, 2]


def test_failed_memory_write_fails_the_cycle(tmp_path):
    """A cycle that cannot record itself is reported as an error, not as ok."""
    runtime = HorizonRuntime(RecordingHorizon(), interval_seconds=60,
                             state_dir=str(tmp_path), memory=BrokenStore())

    with pytest.raises(RuntimeError, match="disk full"):
        runtime.run_once("scan HQ")

    events = runtime.recent_events()
    assert events[-1]["status"] == "error"
    assert "disk full" in events[-1]["message"]
