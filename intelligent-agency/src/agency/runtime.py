"""Persistent runtime for Horizon's continuous improvement cycle.

The runtime intentionally separates autonomous work from human-controlled
promotion. Horizon may inspect, plan, test and prepare review artifacts, but a
runtime cycle never grants merge authority.

Memory policy coverage, stated plainly: this path writes its cycle record with
no policy engine. Worker asks policy.require("memory_remember", ...) before
writing because it holds a PolicyEngine; HorizonRuntime holds none, so a cycle's
own memory write is unchecked and unaudited by policy. It is a local, bounded,
non-consequential write (a sqlite row in the state directory), and adding a real
gate here would mean giving the runtime a policy engine -- not pretending one
exists.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
import time
from typing import Callable, Dict, List, Optional

from .llm import MockBackend
from .memory_context import augment_prompt
from .state import StateStore

# Where this class keeps its own cycle records. The worker writes its results
# to horizon/work-results; keeping the runtime's cycles in their own scope
# keeps the two readable (and lets StateStore.recall(scope=...) read either).
MEMORY_SCOPE = "horizon/runtime"
# Keys are a fixed-size ring, so the runtime can never accumulate more than
# this many memory rows however long it runs. Without a bound, a cycle every
# four hours would push the worker's work-results out of the newest-50 window
# that memory_context.select_entries reads.
MEMORY_WINDOW = 5
MAX_TASK_CHARS = 200
MAX_ANSWER_CHARS = 600


@dataclass
class RuntimeEvent:
    started_at: str
    finished_at: str
    status: str
    cycle: int
    message: str
    usage: Optional[Dict] = None
    analysis_mode: str = "unknown"


class HorizonRuntime:
    """Run Horizon repeatedly with durable, append-only JSONL audit events."""

    def __init__(
        self,
        horizon,
        interval_seconds: int = 3600,
        state_dir: Optional[str] = None,
        max_backoff_seconds: int = 21600,
        memory=None,
    ):
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60 seconds")
        self.horizon = horizon
        # Optional StateStore: when present, a cycle starts from what earlier
        # cycles remembered instead of from the same static text every time.
        self.memory = memory
        self.interval_seconds = interval_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.state_dir = state_dir or os.getenv("HORIZON_STATE_DIR", ".horizon")
        os.makedirs(self.state_dir, exist_ok=True)
        self.audit_path = os.path.join(self.state_dir, "runtime.jsonl")
        self._cycle = 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append(self, event: RuntimeEvent) -> None:
        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), sort_keys=True) + "\n")

    def _recorded_cycles(self) -> int:
        """Highest cycle number already recorded in the store, or 0."""
        if self.memory is None:
            return 0
        rows = self.memory.recall(scope=MEMORY_SCOPE, limit=MEMORY_WINDOW) or []
        numbers = []
        for row in rows:
            value = row.get("value")
            number = value.get("cycle") if isinstance(value, dict) else None
            if isinstance(number, int) and not isinstance(number, bool):
                numbers.append(number)
        return max(numbers, default=0)

    def _remember_cycle(self, task: str, answer, usage: Optional[Dict]) -> None:
        """Record a non-mock cycle so a later one can recall it.

        The write is bounded (MEMORY_WINDOW rows at most, and both fields
        truncated) and idempotent per cycle: the key is derived from the cycle
        number, so re-running a cycle updates one row through the UPSERT in
        StateStore.remember instead of appending a duplicate.

        Mock replies are simulation output, not learning evidence. run_once
        detects the mock backend and does not call this method for simulations.
        """
        if self.memory is None:
            return
        cycle = self._recorded_cycles() + 1
        self.memory.remember(
            f"horizon/runtime/cycle-{cycle % MEMORY_WINDOW}",
            MEMORY_SCOPE,
            {
                "task": task[:MAX_TASK_CHARS],
                "answer": str(answer)[:MAX_ANSWER_CHARS],
                "usage": usage,
                "cycle": cycle,
                "finished_at": self._now(),
            },
            provenance="Horizon runtime cycle",
            confidence="medium",
            status="candidate",
        )

    def run_once(
        self,
        task: str = "Run the continuous improvement cycle",
        *,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        self._cycle += 1
        started = self._now()
        analysis_mode = "unknown"
        try:
            prompt = augment_prompt(task, self.memory, project=project, tags=tags or ())
            answer = self.horizon.advise(prompt)
            usage = getattr(self.horizon, "last_usage", None)
            backend = getattr(self.horizon, "backend", None)
            if isinstance(backend, MockBackend):
                analysis_mode = "simulation"
            elif backend is not None:
                analysis_mode = "live"

            # Preserve workflow success as status=ok, but never treat canned
            # mock output as durable learning or feed it into later prompts.
            if analysis_mode != "simulation":
                self._remember_cycle(task, answer, usage if isinstance(usage, dict) else None)

            event = RuntimeEvent(
                started, self._now(), "ok", self._cycle, str(answer),
                usage if isinstance(usage, dict) else None, analysis_mode,
            )
            self._append(event)
            return {
                "status": "ok",
                "analysis_mode": analysis_mode,
                "answer": str(answer),
                "cycle": str(self._cycle),
            }
        except Exception as exc:
            event = RuntimeEvent(
                started, self._now(), "error", self._cycle, repr(exc),
                analysis_mode=analysis_mode,
            )
            self._append(event)
            raise

    def serve_forever(
        self,
        task: str = "Run the continuous improvement cycle",
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Run forever, surviving transient failures with bounded backoff."""
        failures = 0
        while True:
            try:
                self.run_once(task)
                failures = 0
                sleep(self.interval_seconds)
            except KeyboardInterrupt:
                raise
            except Exception:
                failures += 1
                backoff = min(self.interval_seconds * (2 ** min(failures, 6)), self.max_backoff_seconds)
                sleep(backoff)

    def recent_events(self, limit: int = 20) -> List[dict]:
        if not os.path.exists(self.audit_path):
            return []
        with open(self.audit_path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]
