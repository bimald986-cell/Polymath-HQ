"""Polymath HQ local President dashboard with Ollama chat + durable commands."""
from __future__ import annotations
import html, json, os, sys, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT=os.path.dirname(__file__)
sys.path.insert(0, os.path.join(ROOT,"src"))
from agency.state import StateStore

DB=os.getenv("HORIZON_DB_PATH", os.path.join(ROOT,".horizon","horizon.db"))
HOST=os.getenv("HQ_DASHBOARD_HOST","127.0.0.1")
PORT=int(os.getenv("HQ_DASHBOARD_PORT","8765"))
OLLAMA=os.getenv("OLLAMA_BASE_URL","http://127.0.0.1:11434")
DEFAULT_MODEL=os.getenv("HQ_OLLAMA_MODEL","")

PERSONAS={
 "hq":"You are Polymath HQ, a calm, practical local AI assistant. Help the President think, plan, learn and coordinate work. Be clear about what you know versus what requires tools or execution. Never claim work was executed when it was only discussed.",
 "atlas":"You are Atlas, President of Polymath HQ. Think across projects, route problems conceptually to the right specialists, surface dependencies, and give concise executive guidance. Preserve the human President's final authority.",
 "horizon":"You are Horizon, President Advisor for Polymath HQ. Focus on evidence-backed improvements, future readiness, risks, learning and system design. You may recommend or prepare work, but never imply you merged or deployed anything unless execution evidence is available."
}
STYLE="""body{font-family:Segoe UI,Arial;background:#0b1020;color:#e8edf7;margin:0}header{padding:22px 5%;background:#111a31;display:flex;justify-content:space-between;gap:16px;align-items:center}main{max-width:1180px;margin:auto;padding:24px}.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.tab{background:#202c49;color:#dbe7ff}.tab.active{background:#e8edf7;color:#0b1020}.panel{display:none}.panel.active{display:block}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.card{background:#151e35;border:1px solid #263453;border-radius:14px;padding:18px;margin-bottom:16px}.big{font-size:30px;font-weight:700}.muted{color:#9fb0cf}textarea,select{background:#0d1427;color:white;border:1px solid #35476d;border-radius:10px;padding:11px;box-sizing:border-box}textarea{width:100%;min-height:105px}button{background:#e8edf7;color:#0b1020;border:0;border-radius:9px;padding:11px 18px;font-weight:700;cursor:pointer}button:disabled{opacity:.55}.chat{height:430px;overflow:auto;background:#0d1427;border:1px solid #263453;border-radius:12px;padding:14px;margin:12px 0}.bubble{max-width:82%;padding:11px 13px;border-radius:12px;margin:8px 0;white-space:pre-wrap;line-height:1.45}.user{background:#27406c;margin-left:auto}.assistant{background:#1d2a45}.meta{font-size:12px;color:#9fb0cf;margin-top:5px}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.grow{flex:1}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #283653;text-align:left}.ok{color:#8de3a7}.warn{color:#ffd37a}.bad{color:#ff9a9a}code{color:#a9c7ff}a{color:#a9c7ff}"""

def ollama_models():
    try:
        with urllib.request.urlopen(OLLAMA+"/api/tags",timeout=3) as r:
            data=json.load(r); return [m.get('name','') for m in data.get('models',[]) if m.get('name')]
    except Exception: return []

def ollama_chat(model,persona,messages):
    system=PERSONAS.get(persona,PERSONAS['hq'])
    clean=[]
    for m in messages[-20:]:
        if m.get('role') in ('user','assistant') and isinstance(m.get('content'),str): clean.append({'role':m['role'],'content':m['content'][:12000]})
    payload=json.dumps({'model':model,'stream':False,'messages':[{'role':'system','content':system}]+clean}).encode()
    req=urllib.request.Request(OLLAMA+"/api/chat",data=payload,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180) as r:
        data=json.load(r); return data.get('message',{}).get('content','')

def snapshot():
    s=StateStore(DB); db=s.db
    counts={r['status']:r['n'] for r in db.execute("select status,count(*) n from work_items group by status")}
    hb=[dict(r) for r in db.execute("select * from heartbeat order by seen_at desc limit 10")]
    jobs=[dict(r) for r in db.execute("select id,kind,status,priority,attempts from work_items order by id desc limit 25")]
    mem=[dict(r) for r in db.execute("select key,scope,confidence,status from memory order by updated_at desc limit 15")]
    return counts,hb,jobs,mem

def page(message=""):
    counts,hb,jobs,mem=snapshot(); models=ollama_models(); now=time.time()
    heart="No worker heartbeat yet"
    if hb: heart=f"{hb[0]['worker_id']} · {int(now-hb[0]['seen_at'])}s ago · {hb[0]['details'] or 'active'}"
    rows=''.join(f"<tr><td>{j['id']}</td><td>{html.escape(j['kind'])}</td><td>{j['status']}</td><td>{j['priority']}</td><td>{j['attempts']}</td></tr>" for j in jobs) or '<tr><td colspan=5>No jobs yet</td></tr>'
    mrows=''.join(f"<tr><td>{html.escape(m['key'])}</td><td>{html.escape(m['scope'])}</td><td>{m['confidence']}</td><td>{m['status']}</td></tr>" for m in mem) or '<tr><td colspan=4>No memory yet</td></tr>'
    opts=''.join(f'<option value="{html.escape(m)}" {"selected" if m==DEFAULT_MODEL else ""}>{html.escape(m)}</option>' for m in models)
    ollama_state=f'<span class="ok">Ollama online · {len(models)} model(s)</span>' if models else '<span class="bad">Ollama offline or no models found</span>'
    note=f'<div class="card ok">{html.escape(message)}</div>' if message else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Polymath HQ</title><style>{STYLE}</style></head><body><header><div><h1>POLYMATH HQ · PRESIDENT CONTROL ROOM</h1><div class="muted">Local AI + durable autonomous work</div></div><div>{ollama_state}</div></header><main>{note}
<div class="tabs"><button class="tab active" data-tab="chat">Chat</button><button class="tab" data-tab="command">Command HQ</button><button class="tab" data-tab="activity">Activity & Memory</button></div>
<section id="chat" class="panel active"><div class="card"><div class="row"><div><label>Talk to </label><select id="persona"><option value="hq">HQ Assistant</option><option value="atlas">Atlas · President</option><option value="horizon">Horizon · Advisor</option></select></div><div><label>Ollama model </label><select id="model">{opts}</select></div><button id="clear">New chat</button></div><div id="chatbox" class="chat"><div class="bubble assistant">Welcome to Polymath HQ. Choose HQ, Atlas, or Horizon and talk normally. This chat uses Ollama on this computer.</div></div><textarea id="chatinput" placeholder="Talk to HQ... (Ctrl+Enter to send)"></textarea><div class="row"><button id="send">Send</button><span id="chatstatus" class="muted"></span></div></div></section>
<section id="command" class="panel"><div class="grid"><div class="card"><div class="muted">Queued</div><div class="big">{counts.get('queued',0)}</div></div><div class="card"><div class="muted">Running</div><div class="big">{counts.get('running',0)}</div></div><div class="card"><div class="muted">Completed</div><div class="big">{counts.get('done',0)}</div></div><div class="card"><div class="muted">Horizon heartbeat</div><div>{html.escape(heart)}</div></div></div><div class="card"><h2>Give HQ a job</h2><p class="muted">Unlike Chat, this enters the durable work queue for Horizon to process.</p><form method="post" action="/command"><textarea name="command" required placeholder="Example: Inspect M&M and prepare the highest-value production improvement."></textarea><p><label>Priority <select name="priority"><option value="50">High</option><option value="100" selected>Normal</option><option value="150">Low</option></select></label></p><button type="submit">Send command to Horizon</button></form></div></section>
<section id="activity" class="panel"><div class="card"><h2>Recent work</h2><table><tr><th>ID</th><th>Type</th><th>Status</th><th>Priority</th><th>Attempts</th></tr>{rows}</table></div><div class="card"><h2>Recent memory</h2><table><tr><th>Key</th><th>Scope</th><th>Confidence</th><th>Status</th></tr>{mrows}</table></div><div class="card"><h2>System</h2><p>Database: <code>{html.escape(DB)}</code></p><p>Ollama: <code>{html.escape(OLLAMA)}</code></p><p class="muted">Local-only at <code>http://{HOST}:{PORT}</code>. Keep it private until authentication is added.</p></div></section>
<script>
const hist=[]; const box=document.getElementById('chatbox'), input=document.getElementById('chatinput'), send=document.getElementById('send'), status=document.getElementById('chatstatus');
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')}});
function bubble(role,text){{const d=document.createElement('div');d.className='bubble '+(role==='user'?'user':'assistant');d.textContent=text;box.appendChild(d);box.scrollTop=box.scrollHeight}}
send.onclick=async()=>{{const text=input.value.trim();if(!text)return;if(!document.getElementById('model').value){{status.textContent='Start Ollama and make sure a model is installed.';return}};bubble('user',text);hist.push({{role:'user',content:text}});input.value='';send.disabled=true;status.textContent='Thinking locally...';try{{const r=await fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{persona:document.getElementById('persona').value,model:document.getElementById('model').value,messages:hist}})}});const j=await r.json();if(!r.ok)throw new Error(j.error||'Chat failed');bubble('assistant',j.answer);hist.push({{role:'assistant',content:j.answer}});status.textContent='Local Ollama';}}catch(e){{bubble('assistant','Error: '+e.message);status.textContent='Check Ollama';}}finally{{send.disabled=false}}}};
input.onkeydown=e=>{{if(e.key==='Enter'&&e.ctrlKey)send.click()}};document.getElementById('clear').onclick=()=>{{hist.length=0;box.innerHTML='<div class="bubble assistant">New local HQ chat started.</div>';status.textContent=''}};
</script></main></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def send_json(self,obj,code=200):
        data=json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def send_html(self,body,code=200):
        data=body.encode(); self.send_response(code); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if urlparse(self.path).path=='/health': return self.send_json({'status':'ok','ollama_models':ollama_models()})
        self.send_html(page())
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/chat':
            try:
                length=min(int(self.headers.get('Content-Length','0')),250000); data=json.loads(self.rfile.read(length) or b'{}')
                model=str(data.get('model',''))[:200]; persona=str(data.get('persona','hq'))[:30]; messages=data.get('messages',[])
                if not model or not isinstance(messages,list): return self.send_json({'error':'model and messages are required'},400)
                answer=ollama_chat(model,persona,messages); return self.send_json({'answer':answer,'model':model,'persona':persona})
            except urllib.error.URLError as e: return self.send_json({'error':'Cannot reach Ollama. Make sure Ollama is running. '+str(e)},503)
            except Exception as e: return self.send_json({'error':str(e)},500)
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
    print(f"Ollama: {OLLAMA}")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
