from pathlib import Path

from agency.agent import Agent


class CaptureBackend:
    def __init__(self):
        self.system_prompt = None

    def complete(self, system_prompt, user_prompt):
        self.system_prompt = system_prompt
        return "Captured successfully"


def test_agent_receives_evidence_policy():
    backend = CaptureBackend()
    agent = Agent(
        name="Evidence Test",
        backend=backend,
    )

    result = agent.handle("What is the verified status of AstroLab?")

    assert result == "Captured successfully"
    assert backend.system_prompt is not None
    assert "HQ EVIDENCE VERIFICATION POLICY" in backend.system_prompt
    assert "Never claim verification is complete" in backend.system_prompt


def test_evidence_policy_file_exists():
    policy_file = (
        Path(__file__).resolve().parents[1]
        / "EVIDENCE_VERIFICATION_POLICY.md"
    )

    assert policy_file.is_file()
    assert "DOCUMENTED:" in policy_file.read_text(encoding="utf-8-sig")
