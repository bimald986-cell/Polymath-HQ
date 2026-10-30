"""A cycle's tokens become a cost: priced once, exactly, and never invented.

Before this, a run was costed as a flat 1 budget unit -- a ration, not a cost.
``llm.py`` captured the provider's ``usage`` envelope and ``state.py`` stored
it, but nothing turned tokens into money.

The assertions here are written so that deleting the mechanism turns them red.
Mutation checks (run by hand against this branch, recorded in the PR body):

* divide by ``1e5`` instead of ``1e6`` in ``pricing.cost_for_run`` ->
  ``test_known_usage_and_known_rate_gives_the_exact_amount`` and
  ``test_the_rate_in_force_on_the_run_date_is_the_one_used`` fail;
* make ``_unknown_cost`` return ``amount_pico: 0`` ->
  ``test_a_mock_backed_run_is_costed_unknown_not_zero``,
  ``test_a_model_missing_from_the_table_is_unknown_not_zero`` and
  ``test_usage_reported_as_unknown_costs_unknown`` fail;
* have ``StateStore.record_run`` ignore the ``cost`` it is given (store
  ``UNCALCULATED_COST`` instead) ->
  ``test_a_recorded_run_keeps_its_cost_after_the_rate_changes`` fails.
"""
import json
import os
import sqlite3
import sys
from datetime import date
from decimal import Decimal

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import PresidentAdvisor
from agency.llm import MockBackend, OpenAICompatibleBackend
from agency.model_router import FallbackBackend
from agency.pricing import (
    PRICE_TABLE_ENV,
    PriceTableError,
    cost_for_run,
    default_price_table_path,
    load_price_table,
    load_price_table_safely,
)
from agency.runtime import MEMORY_SCOPE, HorizonRuntime
from agency.state import StateStore
from agency.worker import DurableHorizonWorker


# --------------------------------------------------------------------- helpers
def usage_known(prompt=123, completion=45):
    return {"status": "known", "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion, "note": ""}


OPENAI_SHAPED = {
    "choices": [{"message": {"content": "a real answer"}}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
}


class CannedBackend(OpenAICompatibleBackend):
    """OpenAI-compatible backend whose HTTP layer is a fixture, not a network."""

    def __init__(self, response=OPENAI_SHAPED, model="test-model"):
        super().__init__("https://example.invalid/v1", "test-key", model)
        self.response = response

    def _request(self, payload):
        return self.response


class PricedHorizon:
    """A horizon that reports the same usage and model a live provider would."""

    def __init__(self, model="test-model", prompt=123, completion=45):
        self.model = model
        self.last_usage = usage_known(prompt, completion)

    def advise(self, task):
        return "a priced answer"


def entry(model="test-model", inp="3.00", out="15.50", currency="USD",
          effective="2026-01-01", provider="test-provider"):
    return {
        "model": model,
        "provider": provider,
        "input_per_mtok": inp,
        "output_per_mtok": out,
        "currency": currency,
        "effective_from": effective,
        "source": "test fixture -- not a real rate",
    }


def write_table(path, entries):
    """Write a price table and return the loaded table (as production does)."""
    path.write_text(yaml.safe_dump({"version": 1, "models": entries},
                                   sort_keys=False), encoding="utf-8")
    return load_price_table(path)


def make_worker(tmp_path, backend, price_table=None):
    store = StateStore(str(tmp_path / "horizon.db"))
    worker = DurableHorizonWorker(PresidentAdvisor(backend=backend), store,
                                  worker_id="w", price_table=price_table)
    return worker, store


# ----------------------------------------------------------------- arithmetic
def test_known_usage_and_known_rate_gives_the_exact_amount(tmp_path):
    """123 prompt + 45 completion at 3.00 / 15.50 per million.

    123 * 3.00 = 369.0 and 45 * 15.50 = 697.5 micro-units, so the cycle cost
    1066.5 micro-units = 0.0010665 currency = 1066500000 pico-units.
    """
    table = write_table(tmp_path / "prices.yaml", [entry()])
    cost = cost_for_run(usage_known(123, 45), model="test-model", table=table,
                        at=date(2026, 6, 1))

    assert cost["status"] == "known"
    assert cost["amount_pico"] == 1_066_500_000
    assert Decimal(cost["amount"]) == Decimal("0.0010665")
    assert cost["currency"] == "USD"
    assert cost["provider"] == "test-provider"
    assert (cost["input_per_mtok"], cost["output_per_mtok"]) == ("3.00", "15.50")
    assert cost["source"] == "test fixture -- not a real rate"
    assert cost["effective_from"] == "2026-01-01"
    assert cost["model"] == "test-model"


def test_large_operands_remain_exact_beyond_decimal_context(tmp_path):
    """A 33-digit pico amount must not lose its final unit to Decimal context."""
    table = write_table(tmp_path / "prices.yaml", [
        entry(inp="999999999.999999", out="0")
    ])
    cost = cost_for_run(
        usage_known(999_999_999_999_999_999, 0),
        model="test-model",
        table=table,
        at=date(2026, 6, 1),
    )

    assert cost["status"] == "known"
    assert cost["amount_pico"] == 999999999999998999000000000000001
    assert cost["amount"] == "999999999999998999000.000000000001"


def test_two_cycles_sum_exactly_without_drift(tmp_path):
    """Amounts are integers in pico units, so addition cannot accumulate error."""
    table = write_table(tmp_path / "prices.yaml",
                        [entry(inp="0.000001", out="0.000002")])
    one = cost_for_run(usage_known(999_999, 3), model="test-model", table=table,
                       at=date(2026, 6, 1))
    two = cost_for_run(usage_known(999_999, 3), model="test-model", table=table,
                       at=date(2026, 6, 1))

    assert isinstance(one["amount_pico"], int)
    assert one["amount_pico"] == 1_000_005
    assert one["amount_pico"] + two["amount_pico"] == 2_000_010

    # The same sum, computed independently with Decimals from the rates.
    expected = (Decimal(2 * 999_999) * Decimal("0.000001")
                + Decimal(6) * Decimal("0.000002")) / Decimal(10 ** 6)
    total = Decimal(one["amount_pico"] + two["amount_pico"]).scaleb(-12)
    assert total == expected
    # And the two-run total equals pricing the same tokens as a single run:
    # exactly, with no residue to lose.
    both = cost_for_run(usage_known(2 * 999_999, 6), model="test-model",
                        table=table, at=date(2026, 6, 1))
    assert both["amount_pico"] == one["amount_pico"] + two["amount_pico"]


def test_the_rate_kept_is_the_one_recorded_for_the_run(tmp_path):
    """The block carries the rates, source and date it was priced with."""
    table = write_table(tmp_path / "prices.yaml", [entry(currency="EUR")])
    cost = cost_for_run(usage_known(1, 1), model="test-model", table=table,
                        at=date(2026, 3, 4))
    assert cost["currency"] == "EUR"          # never converted, only recorded
    assert cost["priced_at"] == "2026-03-04"


# ------------------------------------------------------------------ stability
def test_a_recorded_run_keeps_its_cost_after_the_rate_changes(tmp_path):
    """Cost is computed at record time. A new rate must not rewrite history."""
    path = tmp_path / "prices.yaml"
    old_table = write_table(path, [entry(inp="3.00", out="15.50")])
    worker, store = make_worker(tmp_path, CannedBackend(), price_table=old_table)
    store.enqueue("president_command", {"task": "costed"})
    assert worker.run_one() is True

    recorded = store.recent_runs()[0]["cost"]
    # 120 * 3.00 + 30 * 15.50 = 825 micro-units
    assert recorded["status"] == "known"
    assert recorded["amount_pico"] == 825_000_000

    # Rewrite the table with doubled rates and read the run again.
    new_table = write_table(path, [entry(inp="6.00", out="31.00")])
    assert store.recent_runs()[0]["cost"] == recorded

    # And this is not a tautology: the new table would price a new cycle
    # differently, so the equality above is being earned by the stored block.
    repriced = cost_for_run(usage_known(120, 30), model="test-model",
                            table=new_table, at=date(2026, 6, 1))
    assert repriced["amount_pico"] == 1_650_000_000
    assert repriced["amount_pico"] != recorded["amount_pico"]


def test_the_audit_line_is_never_rewritten_by_a_later_rate_change(tmp_path, monkeypatch):
    path = tmp_path / "prices.yaml"
    write_table(path, [entry()])
    monkeypatch.setenv(PRICE_TABLE_ENV, str(path))
    state = tmp_path / "state"

    HorizonRuntime(PricedHorizon(), interval_seconds=60, state_dir=str(state)).run_once("scan")
    first_line = (state / "runtime.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert json.loads(first_line)["cost"]["amount_pico"] == 1_066_500_000

    write_table(path, [entry(inp="9.00", out="45.00")])
    after = (state / "runtime.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert after == first_line


# -------------------------------------------------------- unknown is not zero
def test_a_mock_backed_run_is_costed_unknown_not_zero(tmp_path):
    table = write_table(tmp_path / "prices.yaml", [entry(model="any-model")])
    worker, store = make_worker(tmp_path, MockBackend(), price_table=table)
    store.enqueue("president_command", {"task": "unpriced"})
    assert worker.run_one() is True

    (run,) = store.recent_runs()
    cost = run["cost"]
    assert cost["status"] == "unknown"
    assert cost["amount"] is None
    assert cost["amount_pico"] is None
    assert cost["currency"] is None
    assert "unknown" in cost["note"]          # the usage envelope's status
    # The token counts are left exactly as the backend reported them.
    assert run["usage"]["prompt_tokens"] is None
    assert run["usage"]["total_tokens"] is None
    assert run["usage"]["status"] == "unknown"


def test_a_model_missing_from_the_table_is_unknown_not_zero(tmp_path):
    table = write_table(tmp_path / "prices.yaml", [entry(model="some-other-model")])
    cost = cost_for_run(usage_known(120, 30), model="test-model", table=table,
                        at=date(2026, 6, 1))
    assert cost["status"] == "unknown"
    assert cost["amount_pico"] is None and cost["amount"] is None
    assert "no entry" in cost["note"]
    assert "test-model" in cost["note"]


def test_usage_reported_as_unknown_costs_unknown(tmp_path):
    table = write_table(tmp_path / "prices.yaml", [entry()])
    usage = {"status": "unknown", "prompt_tokens": None, "completion_tokens": None,
             "total_tokens": None, "note": "provider response carried no usage envelope"}
    cost = cost_for_run(usage, model="test-model", table=table, at=date(2026, 6, 1))
    assert cost["status"] == "unknown"
    assert cost["amount_pico"] is None
    assert "not 'known'" in cost["note"]
    assert "no usage envelope" in cost["note"]


def test_a_missing_token_count_is_unknown(tmp_path):
    """Half a token count is not priced: the total would be understated."""
    table = write_table(tmp_path / "prices.yaml", [entry()])
    usage = {"status": "known", "prompt_tokens": 120, "completion_tokens": None,
             "total_tokens": None, "note": ""}
    cost = cost_for_run(usage, model="test-model", table=table, at=date(2026, 6, 1))
    assert cost["status"] == "unknown"
    assert cost["amount_pico"] is None
    assert "completion_tokens" in cost["note"]


def test_a_boolean_token_count_is_not_treated_as_one_token(tmp_path):
    table = write_table(tmp_path / "prices.yaml", [entry()])
    cost = cost_for_run({"status": "known", "prompt_tokens": True,
                         "completion_tokens": 3, "total_tokens": 4}, model="test-model",
                        table=table, at=date(2026, 6, 1))
    assert cost["status"] == "unknown"


def test_a_zero_rate_in_the_table_is_a_legitimate_zero(tmp_path):
    """Zero is only ever reported because the table itself says zero."""
    table = write_table(tmp_path / "prices.yaml", [entry(inp="0", out="0")])
    cost = cost_for_run(usage_known(1_000, 500), model="test-model", table=table,
                        at=date(2026, 6, 1))
    assert cost["status"] == "known"
    assert cost["amount_pico"] == 0
    assert Decimal(cost["amount"]) == 0


def test_no_table_configured_is_unknown(tmp_path):
    cost = cost_for_run(usage_known(), model="test-model", table=None,
                        at=date(2026, 6, 1))
    assert cost["status"] == "unknown"
    assert cost["amount_pico"] is None
    assert PRICE_TABLE_ENV in cost["note"]


# ------------------------------------------------------------------ versioning
def test_the_rate_in_force_on_the_run_date_is_the_one_used(tmp_path):
    table = write_table(tmp_path / "prices.yaml", [
        entry(inp="1.00", out="2.00", effective="2026-01-01"),
        entry(inp="4.00", out="8.00", effective="2026-07-01"),
    ])
    before = cost_for_run(usage_known(1_000_000, 0), model="test-model",
                          table=table, at=date(2026, 6, 30))
    after = cost_for_run(usage_known(1_000_000, 0), model="test-model",
                         table=table, at=date(2026, 7, 1))
    assert Decimal(before["amount"]) == Decimal("1.00")
    assert Decimal(after["amount"]) == Decimal("4.00")
    assert before["effective_from"] == "2026-01-01"
    assert after["effective_from"] == "2026-07-01"


def test_a_rate_not_yet_in_force_is_unknown_not_the_next_one(tmp_path):
    table = write_table(tmp_path / "prices.yaml",
                        [entry(inp="4.00", out="8.00", effective="2026-12-01")])
    cost = cost_for_run(usage_known(1_000_000, 0), model="test-model",
                        table=table, at=date(2026, 10, 26))
    assert cost["status"] == "unknown"
    assert cost["amount_pico"] is None
    assert "2026-12-01" in cost["note"]


def test_a_near_miss_model_name_is_not_priced_with_another_models_rate(tmp_path):
    table = write_table(tmp_path / "prices.yaml", [entry(model="test-model-mini")])
    missing = cost_for_run(usage_known(), model="test-model", table=table,
                           at=date(2026, 6, 1))
    assert missing["status"] == "unknown"

    table2 = write_table(tmp_path / "prices2.yaml", [entry(model="test-model")])
    near = cost_for_run(usage_known(), model="test-model-mini", table=table2,
                        at=date(2026, 6, 1))
    assert near["status"] == "unknown"


# --------------------------------------------------------------- table itself
def test_the_committed_table_ships_with_no_rates():
    """We will not invent a rate. The shipped table prices nothing."""
    path = default_price_table_path()
    assert load_price_table(path).entries == []
    for line in path.read_text(encoding="utf-8").splitlines():
        assert not line.strip().startswith("- model:"), (
            f"{path} contains an active entry: a rate must be added only by the "
            f"owner, with its source: {line!r}"
        )


@pytest.mark.parametrize("bad_rate", ["1.2345678", "-1", "lots", True, "1000000000000000000"])
def test_a_malformed_rate_is_refused_not_rounded(tmp_path, bad_rate):
    path = tmp_path / "prices.yaml"
    path.write_text(yaml.safe_dump({"version": 1,
                                    "models": [entry(inp=bad_rate)]}),
                    encoding="utf-8")
    with pytest.raises(PriceTableError):
        load_price_table(path)


def test_an_entry_missing_a_field_is_refused(tmp_path):
    raw = entry()
    raw.pop("source")
    path = tmp_path / "prices.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [raw]}), encoding="utf-8")
    with pytest.raises(PriceTableError, match="source"):
        load_price_table(path)


def test_two_rates_for_one_model_and_date_are_refused(tmp_path):
    path = tmp_path / "prices.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "models": [entry(), entry(inp="4.00")]}),
                    encoding="utf-8")
    with pytest.raises(PriceTableError, match="effective_from"):
        load_price_table(path)


def test_a_missing_table_file_is_reported_not_fatal(tmp_path):
    table, error = load_price_table_safely(tmp_path / "nope.yaml")
    assert table is None
    assert "cannot read price table" in error


def test_a_broken_table_does_not_stop_the_cycle_and_is_recorded_unknown(tmp_path, monkeypatch):
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: 1\nmodels:\n  - model: 'x'\n", encoding="utf-8")
    monkeypatch.setenv(PRICE_TABLE_ENV, str(broken))
    state = tmp_path / "state"

    result = HorizonRuntime(PricedHorizon(), interval_seconds=60,
                            state_dir=str(state)).run_once("scan")

    assert result["status"] == "ok"          # the cycle still ran
    event = json.loads(
        (state / "runtime.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert event["cost"]["status"] == "unknown"
    assert event["cost"]["amount_pico"] is None
    assert "price table could not be used" in event["cost"]["note"]


# --------------------------------------------------------------- surfacing it
def test_the_runtime_audit_event_carries_the_cost(tmp_path, monkeypatch):
    """The four-hourly artifact's runtime.jsonl says what the cycle cost."""
    path = tmp_path / "prices.yaml"
    write_table(path, [entry()])
    monkeypatch.setenv(PRICE_TABLE_ENV, str(path))
    state = tmp_path / "state"

    HorizonRuntime(PricedHorizon(), interval_seconds=60,
                   state_dir=str(state)).run_once("scan")

    event = json.loads(
        (state / "runtime.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    )
    assert event["status"] == "ok"
    assert event["usage"]["total_tokens"] == 168
    assert event["cost"]["status"] == "known"
    assert event["cost"]["amount_pico"] == 1_066_500_000
    assert event["cost"]["source"] == "test fixture -- not a real rate"


def test_the_runtime_records_the_cost_with_the_cycle(tmp_path):
    """A store-backed cycle lands in ``runs`` with its price, for recent_runs()."""
    table = write_table(tmp_path / "prices.yaml", [entry()])
    store = StateStore(str(tmp_path / "horizon.db"))
    runtime = HorizonRuntime(PricedHorizon(), interval_seconds=60,
                             state_dir=str(tmp_path), memory=store, price_table=table)
    runtime.run_once("scan")

    (run,) = store.recent_runs()
    assert run["kind"] == "horizon_runtime_cycle"
    assert run["usage"]["total_tokens"] == 168
    assert run["cost"]["amount_pico"] == 1_066_500_000
    # The memory row stays what the next cycle learns from -- cost is not in it,
    # because the recall block truncates every entry at 240 characters.
    (row,) = store.recall(scope=MEMORY_SCOPE)
    assert "cost" not in row["value"]


def test_the_workers_memory_value_is_not_bloated_by_cost(tmp_path):
    """Cost goes on the run row, not into the prompt-rendered memory value.

    ``memory_context`` truncates each rendered entry at ``MAX_ENTRY_CHARS`` (240),
    so a cost block inside the memory value silently evicts the finding the next
    cycle is meant to learn from. This is the regression guard for that.
    """
    table = write_table(tmp_path / "prices.yaml", [entry()])
    worker, store = make_worker(tmp_path, CannedBackend(), price_table=table)
    store.enqueue("president_command", {"task": "costed"})
    assert worker.run_one() is True

    (row,) = store.recall(scope="horizon/work-results")
    assert "cost" not in row["value"]
    assert store.recent_runs()[0]["cost"]["status"] == "known"


def test_a_run_recorded_without_a_cost_is_unknown_not_zero(tmp_path):
    store = StateStore(str(tmp_path / "horizon.db"))
    store.record_run(worker_id="w", kind="k", usage=usage_known())
    cost = store.recent_runs()[0]["cost"]
    assert cost["status"] == "unknown"
    assert cost["amount_pico"] is None
    assert cost["note"]


def test_an_older_database_gains_the_cost_column(tmp_path):
    """The scheduled cycle restores a database created before costing existed."""
    path = str(tmp_path / "horizon.db")
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE runs(id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id TEXT,"
        " work_item_id INTEGER, kind TEXT, status TEXT NOT NULL, usage TEXT NOT NULL,"
        " started_at REAL NOT NULL, finished_at REAL NOT NULL, error TEXT);"
    )
    db.execute("INSERT INTO runs(worker_id,kind,status,usage,started_at,finished_at)"
               " VALUES('w','k','ok','{}',1.0,2.0)")
    db.commit()
    db.close()

    store = StateStore(path)                      # migrates in __init__
    assert store.recent_runs()[0]["cost"] is None  # an old run is not invented
    store.record_run(worker_id="w", kind="k", usage=usage_known(),
                     cost={"status": "unknown", "amount_pico": None, "note": "test"})
    assert store.recent_runs()[0]["cost"]["status"] == "unknown"


def test_the_router_names_the_model_that_answered():
    router = FallbackBackend([("primary", CannedBackend(model="served-model"))])
    assert router.model is None
    router.complete("system", "user")
    assert router.model == "served-model"
    assert PresidentAdvisor(backend=router).model == "served-model"


def test_the_advisor_reports_no_model_for_the_mock_backend():
    assert PresidentAdvisor(backend=MockBackend()).model is None
