"""Runtime v2 durable worker."""
from __future__ import annotations
from datetime import datetime, timezone
import os, socket, time
from .state import StateStore

class DurableHorizonWorker:
    def __init__(self, horizon, store: StateStore, worker_id: str | None = None):
        self.horizon=horizon; self.store=store
        self.worker_id=worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.poll_seconds=max(30,int(os.getenv('HORIZON_POLL_SECONDS','60')))
        self.daily_budget=float(os.getenv('HORIZON_DAILY_BUDGET_UNITS','24'))

    def seed_if_empty(self):
        row=self.store.db.execute("SELECT COUNT(*) n FROM work_items WHERE status IN ('queued','running')").fetchone()
        if row['n']==0:
            self.store.enqueue('improvement_scan', {'task':'Inspect HQ for the highest-value evidence-backed improvement and prepare a President-Brief proposal.'})

    def run_one(self) -> bool:
        self.store.beat(self.worker_id, 'claiming')
        item=self.store.claim(self.worker_id)
        if not item: self.store.beat(self.worker_id,'idle'); return False
        period=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if not self.store.charge(period,1.0,self.daily_budget):
            self.store.fail(item['id'], retry_seconds=3600, max_attempts=999)
            self.store.beat(self.worker_id,'budget-paused'); return False
        try:
            task=item['payload'].get('task','Run continuous improvement cycle')
            answer=self.horizon.advise(task)
            self.store.remember(f"work:{item['id']}", 'horizon/work-results', {'task':task,'answer':str(answer)}, provenance='Horizon runtime v2', confidence='medium', status='candidate')
            self.store.complete(item['id']); self.store.beat(self.worker_id,'ok'); return True
        except Exception:
            self.store.fail(item['id']); self.store.beat(self.worker_id,'error'); raise

    def serve_forever(self):
        while True:
            self.seed_if_empty()
            try: self.run_one()
            except Exception: pass
            time.sleep(self.poll_seconds)
