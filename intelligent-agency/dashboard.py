"""Polymath HQ local President dashboard. Standard-library only."""
from __future__ import annotations
import html, json, os, sqlite3, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

ROOT=os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT,"src"))
from agency.state import StateStore

DB=os.getenv("HORIZON_DB_PATH", os.path.join(ROOT,".horizon","horizon.db"))
HOST=os.getenv("HQ_DASHBOARD_HOST","127.0.0.1")
PORT=int(os.getenv("HQ_DASHBOARD_PORT","8765"))

STYLE="""body{font-family:Segoe UI,Arial;background:#0b1020;color:#e8edf7;margin:0}header{padding:24px 5%;background:#111a31}main{max-width:1150px;margin:auto;padding:28px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}.card{background:#151e35;border:1px solid #263453;border-radius:14px;padding:18px;margin-bottom:16px}.big{font-size:30px;font-weight:700}.muted{color:#9fb0cf}textarea{width:100%;min-height:110px;background:#0d1427;color:white;border:1px solid #35476d;border-radius:10px;padding:12px;box-sizing:border-box}button{background:#e8edf7;color:#0b1020;border:0;border-radius:9px;padding:11px 18px;font-weight:700;cursor:pointer}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #283653;text-align:left}.ok{color:#8de3a7}.warn{color:#ffd37a}code{color:#a9c7ff}a{color:#a9c7ff}"""

def snapshot():
    s=StateStore(DB); db=s.db
    counts={r['status']:r['n'] for r in db.execute("select status,count(*) n from work_items group by status")}
    hb=[dict(r) for r in db.execute("select * from heartbeat order by seen_at desc limit 10")]
    jobs=[dict(r) for r in db.execute("select id,kind,status,priority,attempts,created_at,updated_at from work_items order by id desc limit 25")]
    mem=[dict(r) for r in db.execute("select key,scope,confidence,status,updated_at from memory order by updated_at desc limit 15")]
    return counts,hb,jobs,mem

def page(message=""):
    counts,hb,jobs,mem=snapshot(); now=time.time()
    heart="No worker heartbeat yet"
    if hb:
        age=int(now-hb[0]['seen_at']); heart=f"{hb[0]['worker_id']} · {age}s ago · {hb[0]['details'] or 'active'}"
    rows=''.join(f"<tr><td>{j['id']}</td><td>{html.escape(j['kind'])}</td><td>{j['status']}</td><td>{j['priority']}</td><td>{j['attempts']}</td></tr>" for j in jobs) or '<tr><td colspan=5>No jobs yet</td></tr>'
    mrows=''.join(f"<tr><td>{html.escape(m['key'])}</td><td>{html.escape(m['scope'])}</td><td>{m['confidence']}</td><td>{m['status']}</td></tr>" for m in mem) or '<tr><td colspan=4>No memory yet</td></tr>'
    note=f'<div class="card ok">{html.escape(message)}</div>' if message else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="refresh" content="20"><title>Polymath HQ</title><style>{STYLE}</style></head><body><header><h1>POLYMATH HQ · PRESIDENT CONSOLE</h1><div class="muted">Local command center · Horizon stops at the merge gate</div></header><main>{note}<div class="grid"><div class="card"><div class="muted">Queued</div><div class="big">{counts.get('queued',0)}</div></div><div class="card"><div class="muted">Running</div><div class="big">{counts.get('running',0)}</div></div><div class="card"><div class="muted">Completed</div><div class="big">{counts.get('done',0)}</div></div><div class="card"><div class="muted">Horizon heartbeat</div><div>{html.escape(heart)}</div></div></div><div class="card"><h2>Command HQ</h2><p class="muted">Your instruction enters Horizon's durable queue. It does not directly modify main or merge code.</p><form method="post" action="/command"><textarea name="command" required placeholder="Example: Inspect M&M and prepare the highest-value production improvement with evidence and tests."></textarea><p><label>Priority <select name="priority"><option value="50">High</option><option value="100" selected>Normal</option><option value="150">Low</option></select></label></p><button type="submit">Send command to Horizon</button></form></div><div class="card"><h2>Recent work</h2><table><tr><th>ID</th><th>Type</th><th>Status</th><th>Priority</th><th>Attempts</th></tr>{rows}</table></div><div class="card"><h2>Recent memory</h2><table><tr><th>Key</th><th>Scope</th><th>Confidence</th><th>Status</th></tr>{mrows}</table></div><div class="card"><h2>Control</h2><p>Database: <code>{html.escape(DB)}</code></p><p class="muted">Dashboard binds to <code>{HOST}</code> by default so it is visible only on this computer. Do not expose it publicly without authentication.</p></div></main></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def send_html(self, body, code=200):
        data=body.encode(); self.send_response(code); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path=='/health':
            data=b'{"status":"ok"}'; self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_html(page())
    def do_POST(self):
        if self.path!='/command': return self.send_html(page('Unknown action'),404)
        length=min(int(self.headers.get('Content-Length','0')),20000); form=parse_qs(self.rfile.read(length).decode())
        command=(form.get('command') or [''])[0].strip()[:8000]
        try: priority=int((form.get('priority') or ['100'])[0])
        except ValueError: priority=100
        if not command: return self.send_html(page('Command cannot be empty.'),400)
        ident=StateStore(DB).enqueue('president_command',{'task':command,'source':'local-dashboard'},priority=max(1,min(priority,999)))
        self.send_response(303); self.send_header('Location',f'/?queued={ident}'); self.end_headers()
    def log_message(self, fmt, *args): pass

if __name__=='__main__':
    print(f"Polymath HQ dashboard: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
