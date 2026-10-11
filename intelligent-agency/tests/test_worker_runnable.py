"""Tests that DurableHorizonWorker is actually runnable, and that the launcher
consumes the same queue the dashboard writes to.

No network: the GitHub side uses ``FakeTransport``; the advisory side uses a
stub horizon object instead of an LLM.
"""
import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.github_client import GitHubClient  # noqa: E402
from agency.github_worker import GitHubPublisher  # noqa: E402
from agency.horizon_worker_main import build_worker, default_db_path, main  # noqa: E402
from agency.state import StateStore  # noqa: E402
from agency.worker import DurableHorizonWorker  # noqa: E402
from fake_github import FakeTransport  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a test attempted a real HTTP call")

    monkeypatch.setattr(urllib.request, "urlopen", boom)


class StubHorizon:
    """Stands in for PresidentAdvisor: records tasks, returns deterministic text."""

    def __init__(self):
        self.tasks = []

    def advise(self, task):
        self.tasks.append(task)
        return f"[stub] {task}"


@pytest.fixture()
def store(tmp_path):
    return StateStore(str(tmp_path / "horizon.db"))


def make_worker(store, horizon=None, publisher=None):
    return DurableHorizonWorker(
        horizon or StubHorizon(), store, worker_id="test-worker", publisher=publisher
    )


# ----------------------------------------------------------------- the queue
def test_dashboard_command_is_consumed_and_stored(store):
    item_id = store.enqueue("president_command", {"task": "Improve the docs"}, priority=5)
    worker = make_worker(store)

    assert worker.run_one() is True

    row = store.db.execute("SELECT status FROM work_items WHERE id=?", (item_id,)).fetchone()
    assert row["status"] == "done"
    memory = store.recall(scope="horizon/work-results")
    assert len(memory) == 1
    assert memory[0]["value"]["task"] == "Improve the docs"
    assert memory[0]["status"] == "candidate"
    beats = store.db.execute("SELECT details FROM heartbeat WHERE worker_id='test-worker'").fetchall()
    assert beats  # heartbeat rows are written, so the dashboard can see liveness


def test_idle_worker_returns_false(store):
    assert make_worker(store).run_one() is False


def test_seed_if_empty_enqueues_a_scan(store):
    worker = make_worker(store)
    worker.seed_if_empty()
    row = store.db.execute("SELECT kind, status FROM work_items").fetchone()
    assert row["kind"] == "improvement_scan"
    assert row["status"] == "queued"


def test_budget_exhaustion_pauses_without_losing_the_item(store, monkeypatch):
    store.enqueue("president_command", {"task": "work"})
    monkeypatch.setenv("HORIZON_DAILY_BUDGET_UNITS", "1")
    worker = make_worker(store)
    assert worker.run_one() is True  # first unit
    store.enqueue("president_command", {"task": "work again"})
    assert worker.run_one() is False  # budget exhausted
    assert store.db.execute("SELECT COUNT(*) n FROM work_items WHERE status='queued'").fetchone()["n"] == 1


def test_failed_item_is_requeued_not_lost(store):
    class Exploding:
        def advise(self, task):
            raise RuntimeError("model exploded")

    store.enqueue("president_command", {"task": "x"})
    with pytest.raises(RuntimeError):
        make_worker(store, horizon=Exploding()).run_one()
    row = store.db.execute("SELECT status, attempts FROM work_items").fetchone()
    assert row["status"] == "queued" and row["attempts"] == 1


# --------------------------------------------------- queue item -> branch + PR
def test_changeset_work_item_publishes_a_pull_request(store):
    transport = FakeTransport()
    client = GitHubClient(repo="owner/repo", token="t", transport=transport)
    worker = make_worker(store, publisher=GitHubPublisher(client))

    item_id = store.enqueue("github_review_changeset", {"task": "Tighten docs"})
    assert worker.run_one() is True

    assert transport.branches["horizon/proposal-%d" % item_id]
    assert transport.pull_requests[0]["head"] == f"horizon/proposal-{item_id}"
    assert transport.merge_attempts == 0
    memory = store.recall(scope="horizon/work-results")[0]["value"]
    assert memory["merged"] is False
    assert memory["pull_request"].endswith("/pull/7")


def test_changeset_work_item_without_publisher_fails_loudly(store):
    store.enqueue("github_review_changeset", {"task": "x"})
    with pytest.raises(RuntimeError) as excinfo:
        make_worker(store).run_one()
    assert "GITHUB_TOKEN" in str(excinfo.value)


def test_advisory_items_do_not_touch_github(store):
    transport = FakeTransport()
    client = GitHubClient(repo="owner/repo", token="t", transport=transport)
    store.enqueue("president_command", {"task": "advise"})
    assert make_worker(store, publisher=GitHubPublisher(client)).run_one() is True
    assert transport.calls == []


# ---------------------------------------------------------------- the launcher
def test_default_db_path_matches_the_documented_location(monkeypatch):
    monkeypatch.delenv("HORIZON_DB_PATH", raising=False)
    assert default_db_path().endswith(os.path.join("intelligent-agency", ".horizon", "horizon.db"))
    monkeypatch.setenv("HORIZON_DB_PATH", "/tmp/custom-horizon.db")
    assert default_db_path() == "/tmp/custom-horizon.db"


def test_build_worker_wires_store_and_advisor(tmp_path):
    db = str(tmp_path / "q.db")
    worker = build_worker(db, worker_id="w1")
    assert worker.worker_id == "w1"
    assert os.path.exists(db)
    assert hasattr(worker.horizon, "advise")


def test_main_once_processes_a_queued_item(tmp_path, capsys):
    db = str(tmp_path / "queue.db")
    StateStore(db).enqueue("president_command", {"task": "hello from the dashboard"})
    rc = main(["--once", "--db", db, "--worker-id", "cli"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out.strip().splitlines()[-1])
    assert payload == {"db": db, "processed": True, "worker_id": "cli"}
    row = StateStore(db).db.execute("SELECT status FROM work_items").fetchone()
    assert row["status"] == "done"


def test_main_once_is_idle_safe(tmp_path):
    assert main(["--once", "--db", str(tmp_path / "empty.db")]) == 0


def test_main_publish_github_without_token_exits_non_zero(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    rc = main(["--once", "--db", str(tmp_path / "q.db"), "--publish-github"])
    assert rc == 2
    assert "GITHUB_TOKEN" in capsys.readouterr().err


def test_main_require_live_llm_exits_non_zero_when_mock(tmp_path, capsys, monkeypatch):
    for var in ("AGENCY_LLM", "AGENCY_LLM_API_KEY", "AGENCY_PRIMARY_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    rc = main(["--once", "--db", str(tmp_path / "q.db"), "--require-live-llm"])
    assert rc == 2
    assert "No live LLM provider" in capsys.readouterr().err


def test_root_launcher_script_exists():
    launcher = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run_horizon_worker.py"
    )
    assert os.path.exists(launcher)
    with open(launcher, encoding="utf-8") as fh:
        assert "horizon_worker_main" in fh.read()
