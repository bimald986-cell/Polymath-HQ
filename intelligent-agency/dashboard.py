"""Polymath HQ local President dashboard: governed chat + durable commands.

The chat surface used to post straight to ``http://127.0.0.1:11434/api/chat``.
That call consulted no provider configuration, no mode classification and no
durable record, so a user could not tell a model answer from a placeholder and
the audit trail never saw the turn. ``POST /api/chat`` now answers through
:func:`agency.chat.answer_turn` -- the same path ``cli.py ask`` takes: the
President routes to a director and agent, that agent's backend (built by
``agency.llm.get_backend``) answers, durable memory is recalled into the task,
and the turn is classified ``simulation`` / ``live`` / ``unknown`` and written to
the ``runs`` table with its cost.

Local Ollama still works, but only as a *configured provider*::

    AGENCY_LLM=router
    AGENCY_ALLOW_LOCAL_OLLAMA=1
    AGENCY_OLLAMA_MODEL=qwen2.5:3b

or directly, through Ollama's OpenAI-compatible endpoint::

    AGENCY_LLM=openai
    AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
    AGENCY_LLM_API_KEY=ollama
    AGENCY_LLM_MODEL=qwen2.5:3b

There is no second transport in this file: no ``/api/chat`` call, no model
endpoint constant, no ``urllib``. ``tests/test_dashboard_chat_governance.py``
fails if either comes back.
"""
from __future__ import annotations
import html, json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT=os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT,"src"))
from agency import chat
from agency.chat import (  # re-exported: the one definition lives in agency.chat
    PERSONAS,
    PROJECT_CONTEXT_FOOTER,
    PROJECT_CONTEXT_HEADER,
    project_context,
    provider_status,
    system_prompt,
)
from agency.state import StateStore

DB=os.getenv("HORIZON_DB_PATH", os.path.join(ROOT,".horizon","horizon.db"))
HOST=os.getenv("HQ_DASHBOARD_HOST","127.0.0.1")
PORT=int(os.getenv("HQ_DASHBOARD_PORT","8765"))


def state_path():
    """Where a chat turn is recorded, resolved at call time (env can change)."""
    return os.getenv("HORIZON_DB_PATH", os.path.join(ROOT,".horizon","horizon.db"))


def provider_badge():
    """``(css_class, text)`` for the header: what would answer right now."""
    status = provider_status()
    mode = status["analysis_mode"]
    if mode == "live":
        return "ok", f"Live provider · {status['model'] or 'configured model'}"
    if mode == "simulation":
        return "warn", "No provider configured · answers are SIMULATED"
    return "bad", "Provider unclassified · see System tab"


STYLE="""body{font-family:Segoe UI,Arial;background:#0b1020;color:#e8edf7;margin:0}header{padding:22px 5%;background:#111a31;display:flex;justify-content:space-between;gap:16px;align-items:center}main{max-width:1180px;margin:auto;padding:24px}.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.tab{background:#202c49;color:#dbe7ff}.tab.active{background:#e8edf7;color:#0b1020}.panel{display:none}.panel.active{display:block}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.card{background:#151e35;border:1px solid #263453;border-radius:14px;padding:18px;margin-bottom:16px}.big{font-size:30px;font-weight:700}.muted{color:#9fb0cf}textarea,select{background:#0d1427;color:white;border:1px solid #35476d;border-radius:10px;padding:11px;box-sizing:border-box}textarea{width:100%;min-height:105px}button{background:#e8edf7;color:#0b1020;border:0;border-radius:9px;padding:11px 18px;font-weight:700;cursor:pointer}button:disabled{opacity:.55}.chat{height:430px;overflow:auto;background:#0d1427;border:1px solid #263453;border-radius:12px;padding:14px;margin:12px 0}.bubble{max-width:82%;padding:11px 13px;border-radius:12px;margin:8px 0;white-space:pre-wrap;line-height:1.45}.user{background:#27406c;margin-left:auto}.assistant{background:#1d2a45}.assistant.sim{border:1px dashed #ffd37a}.assistant.unknown{border:1px dashed #ff9a9a}.meta{font-size:12px;color:#9fb0cf;margin-top:5px}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.grow{flex:1}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #283653;text-align:left}.ok{color:#8de3a7}.warn{color:#ffd37a}.bad{color:#ff9a9a}code{color:#a9c7ff}a{color:#a9c7ff}"""

SCRIPT="""const hist=[]; const box=document.getElementById('chatbox'), input=document.getElementById('chatinput'), send=document.getElementById('send'), status=document.getElementById('chatstatus');
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')});
function bubble(role,text,mode){const d=document.createElement('div');d.className='bubble '+(role==='user'?'user':'assistant')+(mode==='simulation'?' sim':(mode==='unknown'?' unknown':''));d.textContent=text;box.appendChild(d);box.scrollTop=box.scrollHeight}
send.onclick=async()=>{const text=input.value.trim();if(!text)return;bubble('user',text);hist.push({role:'user',content:text});input.value='';send.disabled=true;status.textContent='Waiting for the HQ...';try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona:document.getElementById('persona').value,messages:hist})});const j=await r.json();if(!r.ok&&!j.answer)throw new Error(j.error||'Chat failed');const mode=j.analysis_mode||'unknown';const label=mode==='simulation'?'[SIMULATION - placeholder text, not a model answer]':(mode==='live'?'':'[UNKNOWN - unverified]');const tail=j.notice?('\\n\\n'+j.notice):'';bubble('assistant',(label?label+'\\n':'')+j.answer+tail,mode);hist.push({role:'assistant',content:j.answer});status.textContent=mode+(j.model?' · '+j.model:'')+(j.run_id?' · run '+j.run_id:'')+(j.record_error?' · NOT RECORDED':'');}catch(e){bubble('assistant','Error: '+e.message,'unknown');status.textContent='Request failed';}finally{send.disabled=false}};
input.onkeydown=e=>{if(e.key==='Enter'&&e.ctrlKey)send.click()};document.getElementById('clear').onclick=()=>{hist.length=0;box.innerHTML='';status.textContent=''};
"""


def snapshot():
    s=StateStore(DB); db=s.db
    counts={r['status']:r['n'] for r in db.execute("select status,count(*) n from work_items group by status")}
    hb=[dict(r) for r in db.execute("select * from heartbeat order by seen_at desc limit 10")]
    jobs=[dict(r) for r in db.execute("select id,kind,status,priority,attempts from work_items order by id desc limit 25")]
    mem=[dict(r) for r in db.execute("select key,scope,confidence,status from memory order by updated_at desc limit 15")]
    return counts,hb,jobs,mem


def page(message=""):
    counts,hb,jobs,mem=snapshot(); now=time.time(); status=provider_status()
    badge_class,badge_text=provider_badge()
    heart="No worker heartbeat yet"
    if hb: heart=f"{hb[0]['worker_id']} · {int(now-hb[0]['seen_at'])}s ago · {hb[0]['details'] or 'active'}"
    rows=''.join(f"<tr><td>{j['id']}</td><td>{html.escape(j['kind'])}</td><td>{j['status']}</td><td>{j['priority']}</td><td>{j['attempts']}</td></tr>" for j in jobs) or '<tr><td colspan=5>No jobs yet</td></tr>'
    mrows=''.join(f"<tr><td>{html.escape(m['key'])}</td><td>{html.escape(m['scope'])}</td><td>{m['confidence']}</td><td>{m['status']}</td></tr>" for m in mem) or '<tr><td colspan=4>No memory yet</td></tr>'
    note=f'<div class="card ok">{html.escape(message)}</div>' if message else ''
    if status["analysis_mode"] == "simulation":
        chat_banner=('<div class="card warn"><strong>No model provider is configured.</strong> '
                     'Answers below are <strong>simulated</strong> by the built-in mock backend: canned '
                     'placeholder text, not reasoning, and not evidence. To get real answers set '
                     '<code>AGENCY_LLM=openai</code> with <code>AGENCY_LLM_API_KEY</code>, '
                     '<code>AGENCY_LLM_BASE_URL</code> and <code>AGENCY_LLM_MODEL</code>, or '
                     '<code>AGENCY_LLM=router</code> with <code>AGENCY_PRIMARY_*</code>. '
                     'Local Ollama: <code>AGENCY_LLM=openai</code>, '
                     '<code>AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1</code>, '
                     '<code>AGENCY_LLM_API_KEY=ollama</code>, <code>AGENCY_LLM_MODEL=&lt;model&gt;</code>.</div>')
    elif status["analysis_mode"] == "live":
        chat_banner=(f'<div class="card ok">Live provider: <code>{html.escape(status["model"] or "configured model")}</code>. '
                     'Every turn is written to the run record with its token usage and cost.</div>')
    else:
        chat_banner=f'<div class="card bad">{html.escape(status["detail"])}</div>'
    welcome=("Welcome to Polymath HQ. Choose HQ, Atlas, or Horizon and talk normally. "
             + ("This chat is simulated - no model is configured." if status["analysis_mode"]=="simulation"
                else "Answers come from the configured provider."))
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Polymath HQ</title><style>{STYLE}</style></head><body><header><div><h1>POLYMATH HQ · PRESIDENT CONTROL ROOM</h1><div class="muted">Local AI + durable autonomous work</div></div><div class="{badge_class}">{html.escape(badge_text)}</div></header><main>{note}
<div class="tabs"><button class="tab active" data-tab="chat">Chat</button><button class="tab" data-tab="command">Command HQ</button><button class="tab" data-tab="activity">Activity &amp; Memory</button></div>
<section id="chat" class="panel active"><div class="card">{chat_banner}<div class="row"><div><label>Talk to </label><select id="persona"><option value="hq">HQ Assistant</option><option value="atlas">Atlas · President</option><option value="horizon">Horizon · Advisor</option></select></div><button id="clear">New chat</button></div><div id="chatbox" class="chat"><div class="bubble assistant">{html.escape(welcome)}</div></div><textarea id="chatinput" placeholder="Talk to HQ... (Ctrl+Enter to send)"></textarea><div class="row"><button id="send">Send</button><span id="chatstatus" class="muted"></span></div></div></section>
<section id="command" class="panel"><div class="grid"><div class="card"><div class="muted">Queued</div><div class="big">{counts.get('queued',0)}</div></div><div class="card"><div class="muted">Running</div><div class="big">{counts.get('running',0)}</div></div><div class="card"><div class="muted">Completed</div><div class="big">{counts.get('done',0)}</div></div><div class="card"><div class="muted">Horizon heartbeat</div><div>{html.escape(heart)}</div></div></div><div class="card"><h2>Give HQ a job</h2><p class="muted">Unlike Chat, this enters the durable work queue for Horizon to process.</p><form method="post" action="/command"><textarea name="command" required placeholder="Example: Inspect M&amp;M and prepare the highest-value production improvement."></textarea><p><label>Priority <select name="priority"><option value="50">High</option><option value="100" selected>Normal</option><option value="150">Low</option></select></label></p><button type="submit">Send command to Horizon</button></form></div></section>
<section id="activity" class="panel"><div class="card"><h2>Recent work</h2><table><tr><th>ID</th><th>Type</th><th>Status</th><th>Priority</th><th>Attempts</th></tr>{rows}</table></div><div class="card"><h2>Recent memory</h2><table><tr><th>Key</th><th>Scope</th><th>Confidence</th><th>Status</th></tr>{mrows}</table></div><div class="card"><h2>System</h2><p>Database: <code>{html.escape(DB)}</code></p><p>Provider: <span class="{badge_class}">{html.escape(badge_text)}</span></p><p class="muted">{html.escape(status["detail"])}</p><p class="muted">Local-only at <code>http://{HOST}:{PORT}</code>. Keep it private until authentication is added.</p></div></section>
<script>{SCRIPT}</script></main></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,code=200):
        data=json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def send_html(self,body,code=200):
        data=body.encode(); self.send_response(code); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if urlparse(self.path).path=='/health': return self.send_json({'status':'ok','provider':provider_status()})
        self.send_html(page())
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/chat':
            try:
                length=min(int(self.headers.get('Content-Length','0')),250000); data=json.loads(self.rfile.read(length) or b'{}')
                persona=str(data.get('persona','hq'))[:30]; messages=data.get('messages',[])
                if not isinstance(messages,list) or not messages: return self.send_json({'error':'messages are required'},400)
                last=[m for m in messages if isinstance(m,dict) and m.get('role')=='user']
                if not last or not str(last[-1].get('content') or '').strip():
                    return self.send_json({'error':'the last message must be a non-empty user message'},400)
                # One path, shared with `cli.py ask`: routing, the configured
                # provider, memory recall, mode classification and the run record.
                turn=chat.answer_turn(
                    str(last[-1]['content'])[:12000],
                    persona=persona,
                    history=messages[:-1][-20:],
                    state_path_override=state_path(),
                )
                code=200 if turn.status=='ok' else 502
                return self.send_json(turn.as_dict(),code)
            except Exception as e:
                return self.send_json({'error':str(e)},500)
        if path!='/command': return self.send_html(page('Unknown action'),404)
        length=min(int(self.headers.get('Content-Length','0')),20000); form=parse_qs(self.rfile.read(length).decode()); command=(form.get('command') or [''])[0].strip()[:8000]
        try: priority=int((form.get('priority') or ['100'])[0])
        except ValueError: priority=100
        if not command: return self.send_html(page('Command cannot be empty.'),400)
        ident=StateStore(DB).enqueue('president_command',{'task':command,'source':'local-dashboard'},priority=max(1,min(priority,999)))
        self.send_response(303); self.send_header('Location',f'/?queued={ident}'); self.end_headers()
    def log_message(self,fmt,*args): pass

if __name__=='__main__':
    print(f"Polymath HQ Control Room: http://{HOST}:{PORT}")
    status=provider_status()
    print(f"Provider: {status['analysis_mode']} · {status['detail']}")
    if status['analysis_mode']=='simulation':
        print("Chat answers will be SIMULATED placeholder text until AGENCY_LLM is configured.")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
