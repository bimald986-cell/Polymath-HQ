"""Regression checks for public-facing Horizon workflow safety.

The scheduled workflow must not persist mock-only state or publish raw memory,
model responses, or the SQLite database as a public Actions artifact.
"""
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "horizon-scheduled.yml"


def test_mock_mode_does_not_restore_persistent_state_cache():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    restore_step = workflow.split("      - name: Restore Horizon state", 1)[1].split(
        "      - name: Run Horizon cycle", 1
    )[0]

    assert "if: vars.AGENCY_LLM != '' && vars.AGENCY_LLM != 'mock'" in restore_step


def test_public_artifact_and_console_output_are_sanitized():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "print(result)" not in workflow
    assert "path: intelligent-agency/.horizon/" not in workflow
    assert "path: intelligent-agency/horizon-audit-summary.json" in workflow
    assert "safe_result = {key: result.get(key) for key in ('status', 'analysis_mode', 'cycle')}" in workflow
    assert "json.dump(summary, fh, sort_keys=True)" in workflow
