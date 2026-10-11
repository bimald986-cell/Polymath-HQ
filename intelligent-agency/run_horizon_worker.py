"""Launcher for the durable Horizon worker (thin wrapper).

Kept at the repository root next to ``start_hq_dashboard.bat`` so both halves of
the documented path are startable the same way:

    python run_horizon_worker.py                 # serve forever
    python run_horizon_worker.py --once          # one item, then exit

See ``src/agency/horizon_worker_main.py`` for options and the authority boundary.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from agency.horizon_worker_main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
