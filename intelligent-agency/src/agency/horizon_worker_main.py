"""Entry point for the durable Horizon worker.

This is the missing launcher: :class:`agency.worker.DurableHorizonWorker` was
defined but never instantiated anywhere in the repository, so the dashboard's
durable queue (``POST /command``) had no consumer.

Run it on the same machine as the dashboard, with the same database:

    cd intelligent-agency
    python -m agency.horizon_worker_main                 # serve forever
    python -m agency.horizon_worker_main --once          # process at most one item
    python -m agency.horizon_worker_main --publish-github  # enable branch/PR publishing

A live LLM provider is required by default: the worker refuses to start when
``AGENCY_LLM`` would resolve to the mock backend, so an unattended run cannot
emit canned text that looks like reasoning. Pass ``--allow-mock-llm`` to opt
into the mock backend for local development only.

Database path resolution matches ``dashboard.py:11`` exactly, so a command
submitted in the President Console is picked up here:
``HORIZON_DB_PATH`` if set, otherwise ``intelligent-agency/.horizon/horizon.db``.

Policy decisions taken by the worker are appended to
``<queue dir>/policy_audit.jsonl`` (override with ``HORIZON_POLICY_AUDIT_PATH``),
so the audit trail survives the process that produced it.

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
from .policy import AUDIT_PATH_ENV, default_engine
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
    resolved_db = db_path or default_db_path()
    # Make the policy audit trail durable next to the queue DB unless the
    # operator points HORIZON_POLICY_AUDIT_PATH somewhere else. The engine comes
    # from default_engine(), so the worker shares the one process-wide audit
    # sink instead of writing decisions to an object nobody can read.
    os.environ.setdefault(
        AUDIT_PATH_ENV, str(Path(resolved_db).resolve().parent / "policy_audit.jsonl")
    )
    store = StateStore(resolved_db)
    agency = build_agency()
    return DurableHorizonWorker(
        agency.advisor,
        store,
        worker_id=worker_id,
        publisher=publisher,
        policy=default_engine(),
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
        "--allow-mock-llm",
        action="store_true",
        help=(
            "development only: run against the canned mock backend instead of "
            "refusing to start without a live LLM provider"
        ),
    )
    parser.add_argument(
        "--require-live-llm",
        action="store_true",
        help="deprecated no-op: a live LLM backend is now required by default",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if not args.allow_mock_llm:
        try:
            require_live_backend()
        except LLMConfigError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            print(
                "Hint: this worker requires a live LLM provider by default. For a "
                "local development run against the mock backend, pass --allow-mock-llm.",
                file=sys.stderr,
            )
            return 2
    else:
        print(
            "WARNING: --allow-mock-llm is set: this run will emit canned mock text, "
            "not model reasoning. Do not use it for unattended cycles.",
            file=sys.stderr,
        )

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
