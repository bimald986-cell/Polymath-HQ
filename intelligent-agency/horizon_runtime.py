#!/usr/bin/env python3
"""Long-running Horizon worker.

Environment:
  HORIZON_INTERVAL_SECONDS  cycle interval, default 3600
  HORIZON_STATE_DIR         durable runtime state directory, default .horizon
  HORIZON_TASK              standing instruction for each cycle
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agency import build_agency
from agency.runtime import HorizonRuntime


def main() -> int:
    president = build_agency()
    horizon = president.advisor
    if horizon is None:
        raise RuntimeError("Horizon President Advisor is not configured")

    interval = int(os.getenv("HORIZON_INTERVAL_SECONDS", "3600"))
    task = os.getenv(
        "HORIZON_TASK",
        "Inspect HQ and approved evidence for useful improvements. Verify findings, prepare reversible changes on review branches when justified, run available QA, and prepare a President Brief. Never merge your own work.",
    )
    runtime = HorizonRuntime(horizon, interval_seconds=interval)
    runtime.serve_forever(task)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
