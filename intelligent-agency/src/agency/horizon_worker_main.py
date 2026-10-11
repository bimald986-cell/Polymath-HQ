"""Entry point for the durable Horizon worker.

This is the missing launcher: :class:`agency.worker.DurableHorizonWorker` was
defined but never instantiated anywhere in the repository, so the dashboard's
durable queue (``POST /command``) had no consumer.

Run it on the same machine as the dashboard, with the same database:

    cd intelligent-agency
    python -m agency.horizon_worker_main                 # serve forever
    python -m agency.horizon_worker_main --once          # process at most one item
    python -m agency.horizon_worker_main --publish-github  # enable branch/PR publishing

Database path resolution matches ``dashboard.py:11`` exactly, so a command
submitted in the President Console is picked up here:
``HORIZON_DB_PATH`` if set, otherwise ``intelligent-agency/.horizon/horizon.db``.

Authority boundary: this worker may write to review branches and open pull
requests. It cannot merge, and it refuses to run a GitHub cycle at all without
``GITHUB_TOKEN``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from .github_client import GitHubAuthError, GitHubClient
from .github_worker import GitHubPublisher
from .llm import LLMConfigError, require_live_backend
from .loader import build_agency
from .state import StateStore
from .worker import DurableHorizonWorker

# intelligent-agency/ (parents: agency -> src -> intelligent-agency)
PKG_ROOT = Path(__file__).resolve().parents[2]


def default_db_path() -> str:
    """The shared queue DB: ``HORIZON_DB_PATH`` or ``.horizon/horizon.db``."""
    configured = os.getenv("HORIZON_DB_PATH", "").strip()
    if configured:
        return configured
    return str(PKG_ROOT / ".horizon" / "horizon.db")


def build_publisher(repo: Optional[str] = None) -> GitHubPublisher:
    """Build a publisher from the environment. Raises loudly without a token."""
    client = GitHubClient.from_env(repo=repo)
    return GitHubPublisher(client)


def build_worker(
    db_path: Optional[str] = None,
    *,
    worker_id: Optional[str] = None,
    publisher=None,
) -> DurableHorizonWorker:
    """Wire the existing pieces into one runnable worker."""
    store = StateStore(db_path or default_db_path())
    agency = build_agency()
    return DurableHorizonWorker(
        agency.advisor,
        store,
        worker_id=worker_id,
        publisher=publisher,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="horizon-worker",
        description="Consume the durable Horizon queue (shared with the dashboard).",
    )
    parser.add_argument("--db", default=None, help="queue DB path (default: HORIZON_DB_PATH)")
    parser.add_argument("--worker-id", default=None, help="stable worker identifier for the heartbeat")
    parser.add_argument("--once", action="store_true", help="process at most one work item, then exit")
    parser.add_argument("--cycles", type=int, default=None, help="stop after N poll cycles")
    parser.add_argument(
        "--publish-github",
        action="store_true",
        help="enable GitHub branch/PR publishing for github_review_changeset items",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="target repository 'owner/name' for publishing (default: GITHUB_REPO)",
    )
    parser.add_argument(
        "--require-live-llm",
        action="store_true",
        help="refuse to start when only the mock LLM backend is configured",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.require_live_llm:
        try:
            require_live_backend()
        except LLMConfigError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    publisher = None
    if args.publish_github:
        try:
            publisher = build_publisher(args.repo)
        except GitHubAuthError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(
            f"GitHub publishing enabled for {publisher.client.repo} "
            f"(branch prefix {publisher.client.branch_prefix}, merge unavailable)",
            flush=True,
        )

    db_path = args.db or default_db_path()
    worker = build_worker(db_path, worker_id=args.worker_id, publisher=publisher)
    print(
        f"Horizon worker {worker.worker_id} watching {db_path} "
        f"(poll {worker.poll_seconds}s, daily budget {worker.daily_budget} units)",
        flush=True,
    )

    if args.once:
        worker.seed_if_empty()
        processed = worker.run_one()
        print(
            json.dumps(
                {"worker_id": worker.worker_id, "db": db_path, "processed": processed},
                sort_keys=True,
            ),
            flush=True,
        )
        return 0

    worker.serve_forever(max_cycles=args.cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
