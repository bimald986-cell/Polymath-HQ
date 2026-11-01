import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency import PresidentAdvisor
from agency.llm import MockBackend
from agency.model_router import FallbackBackend
from agency.runtime import HorizonRuntime
from agency.state import StateStore


def test_mock_selected_by_fallback_router_is_simulation_and_not_remembered(tmp_path):
    store = StateStore(str(tmp_path / "horizon.db"))
    router = FallbackBackend([("demo-mock", MockBackend())])
    runtime = HorizonRuntime(
        PresidentAdvisor(backend=router),
        interval_seconds=60,
        state_dir=str(tmp_path / "state"),
        memory=store,
    )

    result = runtime.run_once("scan")

    assert result["status"] == "ok"
    assert result["analysis_mode"] == "simulation"
    assert store.recall(scope="horizon/runtime") == []
    assert runtime.recent_events()[0]["analysis_mode"] == "simulation"
