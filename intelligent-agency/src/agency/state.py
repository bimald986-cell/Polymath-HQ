"""Durable local state for unattended Horizon workers."""
from __future__ import annotations
import json, sqlite3, time
from pathlib import Path
from typing import Any, Dict, List, Optional


class StateStore:
    def __init__(self, path: str = ".horizon/horizon.db"):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS work_items(
          id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued', priority INTEGER NOT NULL DEFAULT 100,
          attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
          lease_until REAL, worker_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_work_ready ON work_items(status, available_at, priority, id);
        CREATE TABLE IF NOT EXISTS memory(
          key TEXT PRIMARY KEY, scope TEXT NOT NULL, value TEXT NOT NULL, provenance TEXT,
          confidence TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'candidate',
          updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS heartbeat(
          worker_id TEXT PRIMARY KEY, seen_at REAL NOT NULL, details TEXT);
        CREATE TABLE IF NOT EXISTS budget(
          period TEXT PRIMARY KEY, units REAL NOT NULL DEFAULT 0, updated_at REAL NOT NULL);
        """)
        self.db.commit()

    def enqueue(self, kind: str, payload: Dict[str, Any], priority: int = 100, delay_seconds: int = 0) -> int:
        now = time.time()
        cur = self.db.execute("INSERT INTO work_items(kind,payload,priority,available_at,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                              (kind, json.dumps(payload), priority, now + delay_seconds, now, now))
        self.db.commit(); return int(cur.lastrowid)

    def claim(self, worker_id: str, lease_seconds: int = 900) -> Optional[Dict[str, Any]]:
        now = time.time(); self.requeue_expired(now)
        self.db.execute("BEGIN IMMEDIATE")
        row = self.db.execute("SELECT * FROM work_items WHERE status='queued' AND available_at<=? ORDER BY priority,id LIMIT 1", (now,)).fetchone()
        if not row: self.db.commit(); return None
        self.db.execute("UPDATE work_items SET status='running',worker_id=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=?",
                        (worker_id, now + lease_seconds, now, row['id']))
        self.db.commit()
        item = dict(row); item['payload'] = json.loads(item['payload']); item['worker_id'] = worker_id
        return item

    def complete(self, item_id: int) -> None:
        self.db.execute("UPDATE work_items SET status='done',lease_until=NULL,updated_at=? WHERE id=?", (time.time(), item_id)); self.db.commit()

    def fail(self, item_id: int, retry_seconds: int = 300, max_attempts: int = 5) -> None:
        row = self.db.execute("SELECT attempts FROM work_items WHERE id=?", (item_id,)).fetchone()
        status = 'failed' if not row or row['attempts'] >= max_attempts else 'queued'
        self.db.execute("UPDATE work_items SET status=?,available_at=?,lease_until=NULL,worker_id=NULL,updated_at=? WHERE id=?",
                        (status, time.time()+retry_seconds, time.time(), item_id)); self.db.commit()

    def requeue_expired(self, now: Optional[float] = None) -> None:
        now = now or time.time()
        self.db.execute("UPDATE work_items SET status='queued',worker_id=NULL,lease_until=NULL,updated_at=? WHERE status='running' AND lease_until<?", (now, now)); self.db.commit()

    def remember(self, key: str, scope: str, value: Dict[str, Any], provenance: str = '', confidence: str = 'medium', status: str = 'candidate') -> None:
        self.db.execute("INSERT INTO memory(key,scope,value,provenance,confidence,status,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET scope=excluded.scope,value=excluded.value,provenance=excluded.provenance,confidence=excluded.confidence,status=excluded.status,updated_at=excluded.updated_at",
                        (key, scope, json.dumps(value), provenance, confidence, status, time.time())); self.db.commit()

    def recall(self, scope: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[dict]:
        q="SELECT * FROM memory WHERE 1=1"; args=[]
        if scope: q += " AND scope=?"; args.append(scope)
        if status: q += " AND status=?"; args.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"; args.append(limit)
        rows=self.db.execute(q,args).fetchall(); out=[]
        for r in rows:
            x=dict(r); x['value']=json.loads(x['value']); out.append(x)
        return out

    def beat(self, worker_id: str, details: str = '') -> None:
        self.db.execute("INSERT INTO heartbeat(worker_id,seen_at,details) VALUES(?,?,?) ON CONFLICT(worker_id) DO UPDATE SET seen_at=excluded.seen_at,details=excluded.details", (worker_id,time.time(),details)); self.db.commit()

    def charge(self, period: str, units: float, limit: float) -> bool:
        row=self.db.execute("SELECT units FROM budget WHERE period=?",(period,)).fetchone(); used=float(row['units']) if row else 0.0
        if used + units > limit: return False
        now=time.time(); self.db.execute("INSERT INTO budget(period,units,updated_at) VALUES(?,?,?) ON CONFLICT(period) DO UPDATE SET units=units+excluded.units,updated_at=excluded.updated_at",(period,units,now)); self.db.commit(); return True
