"""Runs are costed: the provider's usage envelope is captured and persisted.

Nothing read ``usage`` before this, so a run's cost was discarded with the
response. And the budget was enforced check-then-write, so two workers could
both pass the check and both spend the last unit.
"""

import math
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import PresidentAdvisor
from agency.llm import (
    OpenAICompatibleBackend,
    extract_usage,
    unknown_usage,
)
from agency.state import StateStore
from agency.worker import DurableHorizonWorker


class CannedBackend(OpenAICompatibleBackend):
    """OpenAI-compatible backend whose HTTP layer is a fixture, not a network."""

    def __init__(self, response):
        super().__init__("https://example.invalid/v1", "test-key", "test-model")
        self.response = response

    def _request(self, payload):
        return self.response


OPENAI_SHAPED = {
    "choices": [{"message": {"content": "a real answer"}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
}
NO_USAGE = {"choices": [{"message": {"content": "a real answer"}}]}


# ------------------------------------------------------------------- capture
def test_usage_is_read_from_the_openai_response_shape():
    usage = extract_usage(OPENAI_SHAPED)
    assert usage["status"] == "known"
    assert usage["prompt_tokens"] == 120
    assert usage["completion_tokens"] == 30
    assert usage["total_tokens"] == 150


def test_usage_accepts_input_output_token_aliases():
    usage = extract_usage({"usage": {"input_tokens": 7, "output_tokens": 3}})
    assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]) == (7, 3, 10)


def test_a_response_without_usage_is_unknown_not_zero():
    usage = extract_usage(NO_USAGE)
    assert usage["status"] == "unknown"
    assert usage["prompt_tokens"] is None
    assert usage["completion_tokens"] is None
    assert usage["total_tokens"] is None
    assert usage["note"]


def test_malformed_token_counts_are_unknown_not_truncated_or_negative():
    for invalid in (-1, True, 1.5, "7"):
        usage = extract_usage({
            "usage": {
                "prompt_tokens": invalid,
                "completion_tokens": 3,
                "total_tokens": 4,
            }
        })
        assert usage["status"] == "unknown"
        assert usage["prompt_tokens"] is None
        assert usage["completion_tokens"] is None
        assert usage["total_tokens"] is None


def test_zero_token_counts_are_valid_integers():
    usage = extract_usage({
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    })
    assert usage["status"] == "known"
    assert usage["prompt_tokens"] == 0
    assert usage["completion_tokens"] == 0
    assert usage["total_tokens"] == 0


def test_backend_records_usage_and_still_returns_the_content():
    backend = CannedBackend(OPENAI_SHAPED)
    assert backend.complete("system", "user") == "a real answer"
    assert backend.last_usage["total_tokens"] == 150


def test_backend_without_usage_does_not_crash():
    backend = CannedBackend(NO_USAGE)
    assert backend.complete("system", "user") == "a real answer"
    assert backend.last_usage["status"] == "unknown"


def test_mock_backend_reports_unknown_rather_than_zero():
    from agency.llm import MockBackend

    backend = MockBackend()
    backend.complete("system", "user")
    assert backend.last_usage["status"] == "unknown"
    assert backend.last_usage["total_tokens"] is None


def test_advisor_surfaces_the_backend_usage():
    advisor = PresidentAdvisor(backend=CannedBackend(OPENAI_SHAPED))
    advisor.advise("topic")
    assert advisor.last_usage["total_tokens"] == 150


# ---------------------------------------------------------------- persistence
def make_worker(tmp_path, backend):
    store = StateStore(str(tmp_path / "horizon.db"))
    return DurableHorizonWorker(PresidentAdvisor(backend=backend), store, worker_id="w"), store


def test_a_run_persists_its_usage(tmp_path):
    worker, store = make_worker(tmp_path, CannedBackend(OPENAI_SHAPED))
    store.enqueue("president_command", {"task": "costed"})
    assert worker.run_one() is True

    stored = store.recall(scope="horizon/work-results")[0]["value"]["usage"]
    assert stored["total_tokens"] == 150
    runs = store.recent_runs()
    assert len(runs) == 1
    assert runs[0]["usage"]["prompt_tokens"] == 120
    assert runs[0]["usage"]["completion_tokens"] == 30
    assert runs[0]["status"] == "ok"


def test_a_run_without_usage_persists_unknown(tmp_path):
    worker, store = make_worker(tmp_path, CannedBackend(NO_USAGE))
    store.enqueue("president_command", {"task": "costed"})
    assert worker.run_one() is True

    runs = store.recent_runs()
    assert runs[0]["usage"]["status"] == "unknown"
    assert runs[0]["usage"]["total_tokens"] is None


def test_a_horizon_that_reports_nothing_still_persists_unknown(tmp_path):
    class Bare:
        def advise(self, task):
            return "ok"

    store = StateStore(str(tmp_path / "horizon.db"))
    worker = DurableHorizonWorker(Bare(), store, worker_id="w")
    store.enqueue("president_command", {"task": "x"})
    assert worker.run_one() is True
    assert store.recent_runs()[0]["usage"]["status"] == "unknown"


# --------------------------------------------------------------------- budget
def test_budget_cannot_be_double_spent_by_two_workers(tmp_path):
    """Two connections race for the last unit; exactly one may take it."""
    path = str(tmp_path / "horizon.db")
    StateStore(path)  # create the schema once, up front
    results = []
    barrier = threading.Barrier(2)

    def spend():
        # A connection per thread, as two separate workers would have.
        store = StateStore(path)
        barrier.wait()
        results.append(store.charge("2026-10-18", 1.0, 1.0))

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == [False, True]
    used = StateStore(path).db.execute(
        "SELECT units FROM budget WHERE period='2026-10-18'"
    ).fetchone()["units"]
    assert used == 1.0


def test_budget_still_refuses_once_the_limit_is_reached(tmp_path):
    store = StateStore(str(tmp_path / "horizon.db"))
    assert store.charge("p", 1.0, 2.0) is True
    assert store.charge("p", 1.0, 2.0) is True
    assert store.charge("p", 1.0, 2.0) is False


def test_budget_refuses_a_charge_larger_than_the_whole_limit(tmp_path):
    store = StateStore(str(tmp_path / "horizon.db"))
    assert store.charge("p", 5.0, 1.0) is False
    assert store.db.execute("SELECT COUNT(*) n FROM budget").fetchone()["n"] == 0


@pytest.mark.parametrize("bad_units", [math.nan, math.inf, -math.inf])
def test_budget_rejects_non_finite_units(tmp_path, bad_units):
    store = StateStore(str(tmp_path / "horizon.db"))
    with pytest.raises(ValueError, match="finite"):
        store.charge("p", bad_units, 10.0)


@pytest.mark.parametrize("bad_limit", [math.nan, math.inf, -math.inf, -1.0])
def test_budget_rejects_invalid_limits(tmp_path, bad_limit):
    store = StateStore(str(tmp_path / "horizon.db"))
    with pytest.raises(ValueError, match="limit"):
        store.charge("p", 0.0, bad_limit)


def test_budget_rejects_boolean_units_and_limits(tmp_path):
    store = StateStore(str(tmp_path / "horizon.db"))
    with pytest.raises(ValueError, match="boolean"):
        store.charge("p", True, 1.0)
    with pytest.raises(ValueError, match="boolean"):
        store.charge("p", 1.0, False)


def test_unknown_usage_helper_is_not_zeros():
    usage = unknown_usage()
    assert usage["status"] == "unknown"
    assert usage["total_tokens"] is None
