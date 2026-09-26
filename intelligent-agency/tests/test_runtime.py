import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from agency.runtime import HorizonRuntime


class FakeHorizon:
    def advise(self, task):
        return f"reviewed: {task}"


class BrokenHorizon:
    def advise(self, task):
        raise RuntimeError("temporary failure")


def test_runtime_once_writes_audit(tmp_path):
    runtime = HorizonRuntime(FakeHorizon(), interval_seconds=60, state_dir=str(tmp_path))
    result = runtime.run_once("scan")
    assert result["status"] == "ok"
    events = runtime.recent_events()
    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert "reviewed: scan" in events[0]["message"]


def test_runtime_records_failures(tmp_path):
    runtime = HorizonRuntime(BrokenHorizon(), interval_seconds=60, state_dir=str(tmp_path))
    with pytest.raises(RuntimeError):
        runtime.run_once("scan")
    events = runtime.recent_events()
    assert events[0]["status"] == "error"
    assert "temporary failure" in events[0]["message"]


def test_runtime_rejects_too_fast_loop(tmp_path):
    with pytest.raises(ValueError):
        HorizonRuntime(FakeHorizon(), interval_seconds=10, state_dir=str(tmp_path))
