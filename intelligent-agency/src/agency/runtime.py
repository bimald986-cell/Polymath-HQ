"""Persistent runtime for Horizon's continuous improvement cycle.

The runtime intentionally separates autonomous *work* from human-controlled
promotion. Horizon may inspect, plan, test and prepare review artifacts, but a
runtime cycle never grants merge authority.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
import time
from typing import Callable, Dict, List, Optional


@dataclass
class RuntimeEvent:
    started_at: str
    finished_at: str
    status: str
    cycle: int
    message: str


class HorizonRuntime:
    """Run Horizon repeatedly with durable, append-only JSONL audit events."""

    def __init__(
        self,
        horizon,
        interval_seconds: int = 3600,
        state_dir: Optional[str] = None,
        max_backoff_seconds: int = 21600,
    ):
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60 seconds")
        self.horizon = horizon
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

    def run_once(self, task: str = "Run the continuous improvement cycle") -> Dict[str, str]:
        self._cycle += 1
        started = self._now()
        try:
            answer = self.horizon.advise(task)
            event = RuntimeEvent(started, self._now(), "ok", self._cycle, str(answer))
            self._append(event)
            return {"status": "ok", "answer": str(answer), "cycle": str(self._cycle)}
        except Exception as exc:
            event = RuntimeEvent(started, self._now(), "error", self._cycle, repr(exc))
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
