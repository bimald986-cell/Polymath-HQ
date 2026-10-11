"""Runtime v2 durable worker.

Uses PolicyEngine before memory writes and work enqueue so local side-effects
are classified and audited.

Work-item kinds handled here:

* ``github_review_changeset`` — published as a review branch + pull request by
  the injected :class:`agency.github_worker.GitHubPublisher` (never merged).
* anything else — an advisory Horizon cycle, stored as candidate memory.

Run it with ``python -m agency.horizon_worker_main`` (see that module) against
the same ``HORIZON_DB_PATH`` the dashboard writes to.
"""
from __future__ import annotations
from datetime import datetime, timezone
import os, socket, time
from typing import Optional

from .state import StateStore
from .policy import PolicyEngine, default_engine

GITHUB_CHANGESET_KIND = "github_review_changeset"


class DurableHorizonWorker:
    def __init__(
        self,
        horizon,
        store: StateStore,
        worker_id: str | None = None,
        policy: Optional[PolicyEngine] = None,
        publisher=None,
    ):
        self.horizon = horizon
        self.store = store
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.poll_seconds = max(30, int(os.getenv("HORIZON_POLL_SECONDS", "60")))
        self.daily_budget = float(os.getenv("HORIZON_DAILY_BUDGET_UNITS", "24"))
        self.policy = policy or default_engine()
        self.publisher = publisher

    def seed_if_empty(self):
        row = self.store.db.execute(
            "SELECT COUNT(*) n FROM work_items WHERE status IN ('queued','running')"
        ).fetchone()
        if row["n"] == 0:
            self.policy.require("enqueue_work", actor=self.worker_id)
            self.store.enqueue(
                "improvement_scan",
                {
                    "task": (
                        "Inspect HQ for the highest-value evidence-backed improvement "
                        "and prepare a President-Brief proposal."
                    )
                },
            )

    def run_one(self) -> bool:
        self.store.beat(self.worker_id, "claiming")
        item = self.store.claim(self.worker_id)
        if not item:
            self.store.beat(self.worker_id, "idle")
            return False
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not self.store.charge(period, 1.0, self.daily_budget):
            self.store.fail(item["id"], retry_seconds=3600, max_attempts=999)
            self.store.beat(self.worker_id, "budget-paused")
            return False
        try:
            if item["kind"] == GITHUB_CHANGESET_KIND:
                return self._publish_changeset(item)
            task = item["payload"].get("task", "Run continuous improvement cycle")
            answer = self.horizon.advise(task)
            self.policy.require("memory_remember", actor=self.worker_id)
            self.store.remember(
                f"work:{item['id']}",
                "horizon/work-results",
                {"task": task, "answer": str(answer)},
                provenance="Horizon runtime v2",
                confidence="medium",
                status="candidate",
            )
            self.store.complete(item["id"])
            self.store.beat(self.worker_id, "ok")
            return True
        except Exception:
            self.store.fail(item["id"])
            self.store.beat(self.worker_id, "error")
            raise

    def _publish_changeset(self, item: dict) -> bool:
        """Publish a queued change-set as a review branch + PR. Never merges."""
        if self.publisher is None:
            raise RuntimeError(
                "queued github_review_changeset but no GitHubPublisher is configured: "
                "set GITHUB_TOKEN and GITHUB_REPO (see horizon_worker_main / "
                "docs/MIND_MYTHOS_INTEGRATION.md)"
            )
        from .github_worker import changeset_from_payload

        payload = dict(item["payload"])
        payload.setdefault("id", item["id"])
        branch = payload.pop("branch", None) or f"horizon/proposal-{item['id']}"
        change = changeset_from_payload(payload, branch=branch)
        result = self.publisher.publish(change)
        self.policy.require("memory_remember", actor=self.worker_id)
        self.store.remember(
            f"work:{item['id']}",
            "horizon/work-results",
            {
                "kind": GITHUB_CHANGESET_KIND,
                "branch": result.branch,
                "pull_request": result.pr_url,
                "files": result.files,
                "merged": False,
            },
            provenance="Horizon GitHub adapter",
            confidence="high",
            status="candidate",
        )
        self.store.complete(item["id"])
        self.store.beat(self.worker_id, f"pr-opened:{result.pr_url or result.branch}")
        return True

    def serve_forever(self, max_cycles: Optional[int] = None):
        """Poll the queue forever, or for ``max_cycles`` iterations when given."""
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            self.seed_if_empty()
            try:
                self.run_one()
            except Exception:
                pass
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(self.poll_seconds)
