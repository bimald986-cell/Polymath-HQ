"""``cli.py doctor``: one command that says what is ready and what is not.

The defect these tests guard
----------------------------
Nothing told a first-time user whether the HQ could do anything. A missing
provider, an unusable registry, an absent GitHub token and a broken state store
all failed in different places, most of them silently, and the only way to find
out was to read the source or start a cycle and watch it do nothing.

What is asserted here
---------------------
1. A configured and an unconfigured environment report differently, in the
   ``READY`` / ``NOT READY`` / ``UNKNOWN`` vocabulary, with the environment
   variable named in the reason.
2. A malformed registry is *reported* with the offending entry and field, not
   raised out of the command.
3. A missing GitHub token is reported -- and the token value never appears in
   the report, not even a prefix of it.
4. Doctor makes no network call and creates nothing: a state store that does not
   exist stays non-existent, and an existing one is only read.
5. The exit code is non-zero only when something essential is missing, unless
   ``--require-live`` asks for a real provider.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cli  # noqa: E402
from agency import doctor  # noqa: E402
from agency.state import StateStore  # noqa: E402

PROVIDER_ENV = (
    "AGENCY_LLM", "AGENCY_LLM_BASE_URL", "AGENCY_LLM_API_KEY", "AGENCY_LLM_MODEL",
    "AGENCY_PRIMARY_BASE_URL", "AGENCY_PRIMARY_API_KEY", "AGENCY_PRIMARY_MODEL",
    "AGENCY_SECONDARY_BASE_URL", "AGENCY_SECONDARY_API_KEY", "AGENCY_SECONDARY_MODEL",
    "AGENCY_ALLOW_LOCAL_OLLAMA", "AGENCY_OLLAMA_MODEL",
)
TOKEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN")
REGISTRY_ENV = "HORIZON_PROJECTS_REGISTRY"
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_env(monkeypatch):
    for name in PROVIDER_ENV + TOKEN_ENV + (REGISTRY_ENV, "HORIZON_DB_PATH"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _diagnose(monkeypatch, **kwargs):
    """Diagnose with no network call possible and no accidental repo writes."""
    def refuse(*args, **kwargs):
        raise AssertionError("doctor must not make a network call")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    kwargs.setdefault("repo_root", str(REPO_ROOT))
    return doctor.diagnose(**kwargs)


def _status(report, name):
    check = report.by_name(name)
    assert check is not None, [c.name for c in report.checks]
    return check.status, check.detail


# --------------------------------------------------------------------------
# 1. Configured vs unconfigured.
# --------------------------------------------------------------------------


def test_unconfigured_environment_reports_a_simulation_and_names_the_variable(clean_env, tmp_path):
    report = _diagnose(clean_env, state_path=str(tmp_path / "state" / "horizon.db"))

    status, detail = _status(report, "Provider")
    assert status == doctor.NOT_READY
    assert "AGENCY_LLM" in detail
    assert "SIMULATION" in detail

    model_status, model_detail = _status(report, "Model")
    assert model_status == doctor.NOT_READY
    assert "unknown" in model_detail

    # A cycle still runs on the mock (owner-sanctioned), so this is not a failure.
    assert report.exit_code == 0
    assert report.verdict.startswith("READY TO RUN, IN SIMULATION")
    assert "AGENCY_LLM" in report.verdict


def test_configured_environment_reports_live_and_the_model_name(clean_env, tmp_path):
    clean_env.setenv("AGENCY_LLM", "openai")
    clean_env.setenv("AGENCY_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    clean_env.setenv("AGENCY_LLM_API_KEY", "stub-key")
    clean_env.setenv("AGENCY_LLM_MODEL", "stub-model")

    report = _diagnose(clean_env, state_path=str(tmp_path / "horizon.db"))

    status, detail = _status(report, "Provider")
    assert status == doctor.READY
    assert "live" in detail
    assert _status(report, "Model") == (doctor.READY, "stub-model")
    assert report.exit_code == 0
    assert report.verdict.startswith("READY -")
    assert "stub-model" in report.verdict


def test_require_live_fails_when_no_provider_is_configured(clean_env, tmp_path):
    report = _diagnose(
        clean_env, state_path=str(tmp_path / "horizon.db"), require_live=True
    )
    assert report.exit_code == 1
    assert "--require-live" in report.verdict
    assert "AGENCY_LLM" in report.verdict


# --------------------------------------------------------------------------
# 2. A malformed registry is reported, not raised.
# --------------------------------------------------------------------------


def test_registry_missing_a_required_field_is_reported_with_the_entry(clean_env, tmp_path):
    registry = tmp_path / "projects.yaml"
    registry.write_text(
        "projects:\n"
        "  zebra-labs:\n"
        "    name: Zebra Labs\n"
        "    default_branch: main\n",
        encoding="utf-8",
    )
    report = _diagnose(
        clean_env, registry_path=registry, state_path=str(tmp_path / "horizon.db")
    )
    status, detail = _status(report, "Project registry")
    assert status == doctor.NOT_READY
    assert "zebra-labs" in detail
    assert "github" in detail
    # A broken registry does not stop a cycle, so it does not set the exit code.
    assert report.exit_code == 0
    assert "Project registry" in report.verdict


def test_registry_that_is_not_yaml_is_reported(clean_env, tmp_path):
    registry = tmp_path / "projects.yaml"
    registry.write_text("projects: [this is: not, a mapping\n", encoding="utf-8")
    report = _diagnose(
        clean_env, registry_path=registry, state_path=str(tmp_path / "horizon.db")
    )
    status, detail = _status(report, "Project registry")
    assert status == doctor.NOT_READY
    assert "not valid YAML" in detail


def test_a_healthy_registry_reports_its_project_count(clean_env, tmp_path):
    registry = tmp_path / "projects.yaml"
    registry.write_text(
        "projects:\n"
        "  zebra-labs:\n"
        "    name: Zebra Labs\n"
        "    github: someone/zebra-labs\n"
        "    default_branch: main\n"
        "  yonder:\n"
        "    name: Yonder\n"
        "    github: someone/yonder\n"
        "    default_branch: trunk\n",
        encoding="utf-8",
    )
    report = _diagnose(
        clean_env, registry_path=registry, state_path=str(tmp_path / "horizon.db")
    )
    status, detail = _status(report, "Project registry")
    assert status == doctor.READY
    assert "2 project(s)" in detail
    assert "zebra-labs" in detail and "yonder" in detail


# --------------------------------------------------------------------------
# 3. The GitHub token: presence only, never a value or a prefix.
# --------------------------------------------------------------------------


def test_the_github_token_is_reported_present_and_never_printed(clean_env, tmp_path, capsys):
    secret = "ghp_THISmustNeverAppear1234567890"
    clean_env.setenv("GITHUB_TOKEN", secret)

    report = _diagnose(clean_env, state_path=str(tmp_path / "horizon.db"))
    status, detail = _status(report, "GitHub token")
    assert status == doctor.READY
    assert "GITHUB_TOKEN is set" in detail
    assert "value not shown" in detail

    # Neither the rendered report nor the JSON may carry the value, or a prefix.
    rendered = report.render()
    as_json = json.dumps(report.as_dict())
    for text in (rendered, as_json, detail):
        assert secret not in text
        assert secret[:4] not in text
        assert secret[:8] not in text

    # And the same through the real command.
    assert cli.main(["doctor", "--state-path", str(tmp_path / "h2.db")]) == 0
    captured = capsys.readouterr()
    for text in (captured.out, captured.err):
        assert secret not in text
        assert secret[:8] not in text
    assert "GITHUB_TOKEN is set" in captured.out


def test_a_missing_token_is_reported_as_not_ready(clean_env, tmp_path):
    report = _diagnose(clean_env, state_path=str(tmp_path / "horizon.db"))
    status, detail = _status(report, "GitHub token")
    assert status == doctor.NOT_READY
    assert "GITHUB_TOKEN" in detail
    assert "GH_TOKEN" in detail
    assert report.exit_code == 0  # chat and inspection still work


# --------------------------------------------------------------------------
# 4. No network calls, no writes.
# --------------------------------------------------------------------------


def test_doctor_creates_no_state_store_and_makes_no_network_call(clean_env, tmp_path):
    target = tmp_path / "never" / "horizon.db"
    report = _diagnose(clean_env, state_path=str(target))
    assert not target.exists(), "doctor must not create the state database"
    assert not target.parent.exists(), "doctor must not create the directory either"
    status, detail = _status(report, "State store")
    # Creatable is READY, and it says so without having created anything.
    assert status == doctor.READY
    assert "not created yet" in detail


def test_an_uncreatable_state_store_path_is_fatal(clean_env, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory", encoding="utf-8")
    report = _diagnose(clean_env, state_path=str(blocker / "horizon.db"))
    status, detail = _status(report, "State store")
    assert status == doctor.NOT_READY
    assert "cannot be created" in detail
    assert report.exit_code == 1, "an unusable state store blocks a cycle"


def test_doctor_reads_an_existing_state_store_without_touching_it(clean_env, tmp_path):
    path = tmp_path / "horizon.db"
    store = StateStore(str(path))
    store.record_run(worker_id="test", kind="chat_turn", usage={"status": "unknown"},
                     analysis_mode="simulation")
    before = sorted(p.name for p in tmp_path.iterdir())

    report = _diagnose(clean_env, state_path=str(path))
    status, detail = _status(report, "State store")
    assert status == doctor.READY
    assert "1 run record(s)" in detail
    assert sorted(p.name for p in tmp_path.iterdir()) == before, "doctor wrote something"


def test_a_corrupt_state_store_is_reported_not_raised(clean_env, tmp_path):
    path = tmp_path / "horizon.db"
    path.write_bytes(b"this is not a database")
    report = _diagnose(clean_env, state_path=str(path))
    status, detail = _status(report, "State store")
    assert status == doctor.NOT_READY
    assert report.exit_code == 1


# --------------------------------------------------------------------------
# 5. The rest of the report, and the one verdict line.
# --------------------------------------------------------------------------


def test_report_covers_every_item_a_first_time_user_needs(clean_env, tmp_path):
    report = _diagnose(clean_env, state_path=str(tmp_path / "horizon.db"))
    names = [check.name for check in report.checks]
    assert names == [
        "Agency config", "Provider", "Model", "Project registry",
        "Price table", "State store", "Tools", "GitHub token",
    ]
    for check in report.checks:
        assert check.status in (doctor.READY, doctor.NOT_READY, doctor.UNKNOWN)
        assert check.detail, f"{check.name} has no reason"

    tools_status, tools_detail = _status(report, "Tools")
    assert tools_status == doctor.READY
    for tool in ("read_file", "run_tests", "http_get_allowlisted"):
        assert tool in tools_detail

    price_status, price_detail = _status(report, "Price table")
    assert price_status == doctor.READY
    assert "empty on purpose" in price_detail

    rendered = report.render()
    assert rendered.rstrip().splitlines()[-1].startswith("Verdict: ")
    assert "no network calls, no writes" in rendered


def test_a_broken_agency_config_is_fatal_and_reported(clean_env, tmp_path):
    broken = tmp_path / "agency.yaml"
    broken.write_text("directors: [not a mapping\n", encoding="utf-8")
    report = _diagnose(
        clean_env, config_path=str(broken), state_path=str(tmp_path / "horizon.db")
    )
    status, detail = _status(report, "Agency config")
    assert status == doctor.NOT_READY
    assert report.exit_code == 1
    assert report.verdict.startswith("NOT READY")


def test_cli_doctor_returns_the_report_exit_code(clean_env, tmp_path, capsys):
    assert cli.main(["doctor", "--state-path", str(tmp_path / "horizon.db")]) == 0
    out = capsys.readouterr().out
    assert "Polymath HQ doctor" in out
    assert "Verdict: READY TO RUN, IN SIMULATION" in out

    assert cli.main([
        "doctor", "--state-path", str(tmp_path / "h.db"), "--require-live",
    ]) == 1


def test_cli_doctor_json_is_machine_readable(clean_env, tmp_path, capsys):
    assert cli.main(["doctor", "--json", "--state-path", str(tmp_path / "h.db")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 0
    assert {check["name"] for check in payload["checks"]} >= {"Provider", "State store"}
    assert payload["verdict"]
