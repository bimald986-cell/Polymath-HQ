"""Policy-gated agent loop: think → act → observe, always capped.

"Done" is decided by the step function returning a terminal result or by
exhausting max_steps — never by unbounded recursion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .policy import PolicyEngine, default_engine


@dataclass
class LoopStep:
    index: int
    tool: Optional[str]
    observation: Any
    terminal: bool = False
    error: Optional[str] = None


@dataclass
class LoopResult:
    status: str  # completed | max_steps | blocked | error
    steps: List[LoopStep] = field(default_factory=list)
    answer: Any = None
    message: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "answer": self.answer,
            "message": self.message,
            "steps": [
                {
                    "index": s.index,
                    "tool": s.tool,
                    "observation": s.observation,
                    "terminal": s.terminal,
                    "error": s.error,
                }
                for s in self.steps
            ],
        }


StepFn = Callable[[int, List[LoopStep]], Dict[str, Any]]


def run_agent_loop(
    step_fn: StepFn,
    *,
    max_steps: int = 8,
    policy: Optional[PolicyEngine] = None,
    president_authorized: bool = False,
    actor: str = "horizon",
) -> LoopResult:
    """Run a bounded agent loop.

    ``step_fn(step_index, prior_steps)`` must return a dict:
      - tool: optional tool name (checked via PolicyEngine when present)
      - target: optional network target for allowlist
      - observation: result of the action
      - terminal: True to stop successfully
      - answer: optional final answer when terminal
    """
    if max_steps < 1:
        raise ValueError("max_steps must be >= 1")

    eng = policy or default_engine()
    steps: List[LoopStep] = []

    for i in range(1, max_steps + 1):
        try:
            out = step_fn(i, list(steps)) or {}
        except Exception as exc:
            steps.append(
                LoopStep(index=i, tool=None, observation=None, terminal=True, error=repr(exc))
            )
            return LoopResult(
                status="error",
                steps=steps,
                message=f"step_fn raised: {exc!r}",
            )

        tool = out.get("tool")
        if tool:
            decision = eng.check(
                str(tool),
                president_authorized=president_authorized,
                target=out.get("target"),
                actor=actor,
            )
            if not decision.allowed:
                steps.append(
                    LoopStep(
                        index=i,
                        tool=str(tool),
                        observation=decision.as_dict(),
                        terminal=True,
                        error=decision.reason,
                    )
                )
                return LoopResult(
                    status="blocked",
                    steps=steps,
                    message=decision.reason,
                )

        terminal = bool(out.get("terminal"))
        steps.append(
            LoopStep(
                index=i,
                tool=str(tool) if tool else None,
                observation=out.get("observation"),
                terminal=terminal,
            )
        )
        if terminal:
            return LoopResult(
                status="completed",
                steps=steps,
                answer=out.get("answer", out.get("observation")),
                message="terminal step",
            )

    return LoopResult(
        status="max_steps",
        steps=steps,
        message=f"Exceeded max_steps={max_steps} without terminal result",
    )
