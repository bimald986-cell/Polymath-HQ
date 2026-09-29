"""Tests for policy-gated agent loop."""
from agency.agent_loop import run_agent_loop
from agency.policy import default_engine


def test_loop_completes_when_terminal():
    def step(i, prior):
        if i < 3:
            return {"tool": "local_file_read", "observation": f"chunk-{i}"}
        return {"tool": "local_file_read", "observation": "done", "terminal": True, "answer": "ok"}

    result = run_agent_loop(step, max_steps=5)
    assert result.status == "completed"
    assert result.answer == "ok"
    assert len(result.steps) == 3


def test_loop_stops_at_max_steps():
    def step(i, prior):
        return {"tool": "memory_recall", "observation": i}

    result = run_agent_loop(step, max_steps=3)
    assert result.status == "max_steps"
    assert len(result.steps) == 3


def test_loop_blocks_irreversible_without_president():
    eng = default_engine()

    def step(i, prior):
        return {"tool": "merge_pull_request", "observation": "nope"}

    result = run_agent_loop(step, max_steps=5, policy=eng, president_authorized=False)
    assert result.status == "blocked"
    assert "President" in result.message


def test_loop_allows_irreversible_with_president():
    eng = default_engine()

    def step(i, prior):
        return {
            "tool": "merge_pull_request",
            "observation": "merged",
            "terminal": True,
            "answer": "merged",
        }

    result = run_agent_loop(step, max_steps=3, policy=eng, president_authorized=True)
    assert result.status == "completed"
    assert result.answer == "merged"
