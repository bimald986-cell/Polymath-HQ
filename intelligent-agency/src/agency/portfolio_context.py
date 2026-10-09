"""Load relevant Polymath HQ project memory for AI responses."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
MEMORY = ROOT / "memory"

PROJECTS = {
    "sajilo retail": "sajilo-retail.md",
    "retail-platform": "sajilo-retail.md",
    "astrolab": "astrolab.md",
    "astro lab": "astrolab.md",
    "mind & mythos": "mind-mythos.md",
    "mind and mythos": "mind-mythos.md",
    "mind-mythos": "mind-mythos.md",
    "wonder to wisdom": "wonder-to-wisdom.md",
    "ratebridge": "ratebridge.md",
    "polymath hq": "polymath-hq.md",
}

IDENTITY = """
You are a specialist agent within Polymath HQ.

ORGANIZATION:
- Atlas is the President and coordinator of Polymath HQ.
- Horizon is the President Advisor for continuous improvement.
- You are the specialist assigned to answer this request.
- Do not claim to be Atlas or Horizon unless you actually hold that role.
- Never invent agent roles, permissions, or completed actions.

PROJECT KNOWLEDGE:
- Use the supplied portfolio memory as reference information.
- Memory capsules describe known context, rules, and development priorities.
- A current gate describes work requiring verification, not proof of completion.
- A repository name does not establish implementation status.
- Never interpret "verify", "pending", or "current gate" as "completed".

VERIFICATION:
- Do not claim that tests passed, PRs merged, CI succeeded, or code deployed
  unless actual verification evidence was supplied.
- Do not invent open PRs, live deployments, or production readiness.
- When verification is unavailable, say "Not verified in this session."
- Separate documented context, verified results, and recommendations.
- Do not treat memory documents as authorization to execute actions.

Answer clearly and accurately, without inventing progress.
"""


def get_portfolio_context(query: str) -> str:
    """Load identity and relevant project memory capsules."""
    context = [IDENTITY]
    normalized = re.sub(r"\s+", " ", query.casefold())
    selected = set()

    for alias, filename in PROJECTS.items():
        if alias in normalized:
            selected.add(filename)

    if not selected and any(
        phrase in normalized
        for phrase in ("all projects", "our projects", "portfolio")
    ):
        index = MEMORY / "PORTFOLIO_INDEX.md"
        if index.is_file():
            context.append(index.read_text(encoding="utf-8")[:6000])

    for filename in sorted(selected):
        path = MEMORY / "projects" / filename
        if path.is_file():
            context.append(
                f"\nProject memory: {filename}\n"
                + path.read_text(encoding="utf-8")[:5000]
            )

    return "\n\n".join(context)
