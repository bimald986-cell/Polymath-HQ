#!/usr/bin/env python3
"""Elevate Edge — local career service web app (MVP).

    cd elevate-edge
    pip install -r requirements.txt
    set AGENCY_LLM=openai
    set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
    set AGENCY_LLM_API_KEY=ollama
    set AGENCY_LLM_MODEL=gemma2:2b
    python app.py

Open http://127.0.0.1:8088
(Do not use port 5060 — Chrome blocks it as ERR_UNSAFE_PORT.)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

ROOT = Path(__file__).resolve().parent
ROLES_PATH = ROOT / "data" / "roles.json"

# Reuse Intelligent Agency LLM backend when available
_AGENCY_SRC = ROOT.parent / "intelligent-agency" / "src"
if _AGENCY_SRC.is_dir():
    sys.path.insert(0, str(_AGENCY_SRC))

try:
    from agency.llm import get_backend  # type: ignore
except Exception:  # pragma: no cover
    def get_backend():
        class _Mock:
            def complete(self, system_prompt: str, user_prompt: str) -> str:
                return (
                    "[offline mock] Connect Ollama or set AGENCY_LLM=openai to get AI suggestions.\n"
                    f"Request was: {user_prompt[:200]}"
                )

        return _Mock()

app = Flask(__name__)

with open(ROLES_PATH, encoding="utf-8") as f:
    ROLES = json.load(f)


def llm_complete(system: str, user: str) -> str:
    backend = get_backend()
    return backend.complete(system, user)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Elevate Edge — Career Service</title>
<style>
:root{
  --bg:#0c1220;--panel:#141c2b;--card:#1a2436;--line:#2a364a;
  --text:#eef2ff;--muted:#93a0b8;--accent:#3b82f6;--accent2:#14b8a6;--warn:#f59e0b;
  --radius:14px;--font:Segoe UI,system-ui,sans-serif;
}
*{box-sizing:border-box} body{margin:0;font-family:var(--font);background:var(--bg);color:var(--text)}
a{color:var(--accent2);text-decoration:none}
header{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:1rem 1.25rem;border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(12,18,32,.92);backdrop-filter:blur(8px);z-index:10;flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.02em}.brand span{color:var(--accent2)}
nav{display:flex;gap:.4rem;flex-wrap:wrap}
nav button{background:transparent;border:1px solid transparent;color:var(--muted);padding:.45rem .75rem;border-radius:999px;cursor:pointer;font:inherit}
nav button.active,nav button:hover{color:var(--text);border-color:var(--line);background:var(--panel)}
main{max-width:1100px;margin:0 auto;padding:1.25rem}
.hero{display:grid;gap:1.25rem;grid-template-columns:1.3fr 1fr;align-items:stretch}
@media(max-width:800px){.hero{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:1.1rem}
h1{margin:.2rem 0 .6rem;font-size:1.8rem;line-height:1.2}
h2{margin:0 0 .75rem;font-size:1.2rem}
p.lead{color:var(--muted);line-height:1.55;margin:0 0 1rem}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;border:none;border-radius:10px;padding:.65rem 1rem;font:inherit;font-weight:600;cursor:pointer}
.btn-primary{background:linear-gradient(135deg,var(--accent),#2563eb);color:#fff}
.btn-secondary{background:var(--card);color:var(--text);border:1px solid var(--line)}
.btn:disabled{opacity:.55;cursor:wait}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem}
@media(max-width:800px){.grid3{grid-template-columns:1fr}}
.price{font-size:1.4rem;font-weight:700;color:var(--accent2);margin:.3rem 0}
.muted{color:var(--muted);font-size:.9rem}
ul.clean{margin:.4rem 0 0;padding-left:1.1rem;color:var(--muted)}
.view{display:none}.view.active{display:block}
label{display:block;font-size:.78rem;color:var(--muted);margin:0.55rem 0 0.25rem;text-transform:uppercase;letter-spacing:.04em}
input,textarea,select{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:.65rem .75rem;font:inherit}
textarea{min-height:88px;resize:vertical}
.row{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:.75rem}
.split{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:900px){.split{grid-template-columns:1fr}}
.cv-preview{background:#f8fafc;color:#0f172a;border-radius:12px;padding:1.25rem;min-height:420px;font-size:13px;line-height:1.4}
.cv-preview.modern{border-top:6px solid #0f766e}
.cv-preview.classic{border-top:6px solid #1e3a8a}
.cv-preview h3{margin:0 0 .2rem;font-size:1.35rem;color:#0f172a}
.cv-preview .sub{color:#475569;margin-bottom:.8rem}
.cv-preview h4{margin:.85rem 0 .35rem;font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:#334155;border-bottom:1px solid #e2e8f0;padding-bottom:.2rem}
.cv-preview ul{margin:.2rem 0 .4rem;padding-left:1.1rem}
.role-card{cursor:pointer;transition:.15s}.role-card:hover{border-color:var(--accent)}
.role-card.active{border-color:var(--accent2);box-shadow:0 0 0 1px var(--accent2) inset}
.tag{display:inline-block;background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:.15rem .5rem;font-size:.75rem;margin:.15rem .15rem 0 0;color:var(--muted)}
.out{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:.8rem;min-height:100px;line-height:1.5}
.banner{font-size:.8rem;color:var(--muted);margin-top:1rem}
footer{text-align:center;color:var(--muted);font-size:.75rem;padding:1.5rem}
</style>
</head>
<body>
<header>
  <div class="brand">Elevate <span>Edge</span></div>
  <nav>
    <button data-view="home" class="active">Home</button>
    <button data-view="packages">Packages</button>
    <button data-view="cv">CV Builder</button>
    <button data-view="roles">Role Guide</button>
    <button data-view="interview">Interview</button>
  </nav>
</header>
<main>
  <section id="home" class="view active">
    <div class="hero">
      <div class="panel">
        <p class="muted">Career Service · HR-informed</p>
        <h1>Present your best self—clearly.</h1>
        <p class="lead">Elevate Edge helps job seekers with CVs, LinkedIn, interview prep, and role clarity. Start with the free tools below; upgrade to done-for-you packages when you want expert hands-on help.</p>
        <div class="row">
          <button class="btn btn-primary" data-go="cv">Open CV Builder</button>
          <button class="btn btn-secondary" data-go="packages">View packages</button>
        </div>
        <p class="banner">Not a job guarantee. AI suggestions are drafts—you must verify facts. Local app · optional Ollama for AI.</p>
      </div>
      <div class="panel">
        <h2>What you can do here</h2>
        <ul class="clean">
          <li>Build a structured CV and print/save as PDF</li>
          <li>Pull role-based bullet ideas from the Role Guide</li>
          <li>Practice STAR interview answers</li>
          <li>Ask AI (if Ollama is connected) to draft bullets</li>
        </ul>
        <p class="muted" style="margin-top:1rem" id="healthLine">Checking AI backend…</p>
      </div>
    </div>
  </section>

  <section id="packages" class="view">
    <h2>Service packages</h2>
    <p class="lead">Manual Elevate Edge services (delivered by you as the HR professional). Prices are guides—adjust anytime.</p>
    <div class="grid3">
      <div class="panel">
        <h2>Edge Start</h2>
        <div class="price">$49–89</div>
        <p class="muted">CV rewrite or strong edit · 1 revision · 5–7 days</p>
        <ul class="clean"><li>1-page focused CV</li><li>HR-style bullets</li><li>One revision round</li></ul>
      </div>
      <div class="panel">
        <h2>Edge Pro</h2>
        <div class="price">$99–179</div>
        <p class="muted">CV + LinkedIn · 7–10 days</p>
        <ul class="clean"><li>Full CV rewrite</li><li>LinkedIn headline + About + experience</li><li>One revision each</li></ul>
      </div>
      <div class="panel">
        <h2>Edge Career</h2>
        <div class="price">$179–299</div>
        <p class="muted">CV + LinkedIn + interview prep</p>
        <ul class="clean"><li>Everything in Pro</li><li>60-min coaching call</li><li>7-day email support</li></ul>
      </div>
    </div>
    <div class="panel" style="margin-top:1rem">
      <h2>Client intake (copy into Google Form)</h2>
      <ul class="clean">
        <li>Full name · email · WhatsApp</li>
        <li>Target role / industry · years of experience</li>
        <li>Current CV upload</li>
        <li>Top 3 achievements</li>
        <li>Package selected · deadline</li>
      </ul>
    </div>
  </section>

  <section id="cv" class="view">
    <h2>CV Builder</h2>
    <p class="lead">Fill the form · pick a template · print to PDF from your browser (Ctrl+P).</p>
    <div class="split">
      <div class="panel">
        <label>Template</label>
        <select id="tpl"><option value="modern">Modern</option><option value="classic">Classic</option></select>
        <label>Full name</label><input id="name" placeholder="Your name"/>
        <label>Headline</label><input id="headline" placeholder="HR Generalist | Employee Relations"/>
        <label>Contact line</label><input id="contact" placeholder="City · email · phone · LinkedIn"/>
        <label>Professional summary</label><textarea id="summary" placeholder="3–4 lines on your value"></textarea>
        <label>Experience (one role per block; use blank lines between roles)</label>
        <textarea id="experience" style="min-height:140px" placeholder="Job Title — Company (Dates)
- Achievement bullet
- Achievement bullet"></textarea>
        <label>Education</label><textarea id="education" placeholder="Degree — School (Year)"></textarea>
        <label>Skills (comma-separated)</label><input id="skills" placeholder="Recruitment, Onboarding, HRIS"/>
        <div class="row">
          <button class="btn btn-primary" id="btnSave">Save locally</button>
          <button class="btn btn-secondary" id="btnPrint">Print / PDF</button>
          <button class="btn btn-secondary" id="btnAiBullets">AI: suggest bullets</button>
        </div>
        <div class="out" id="aiOut" style="margin-top:.75rem;display:none"></div>
      </div>
      <div>
        <div class="cv-preview modern" id="preview"></div>
      </div>
    </div>
  </section>

  <section id="roles" class="view">
    <h2>Role Guide</h2>
    <p class="lead">Understand common roles and copy editable bullet ideas into your CV.</p>
    <div class="grid3" id="roleGrid"></div>
    <div class="panel" style="margin-top:1rem" id="roleDetail">
      <p class="muted">Select a role card.</p>
    </div>
  </section>

  <section id="interview" class="view">
    <h2>Interview Coach</h2>
    <p class="lead">Draft a STAR answer. Use AI if connected, or write it yourself.</p>
    <div class="panel">
      <label>Target role</label><input id="ivRole" placeholder="e.g. HR Generalist"/>
      <label>Question</label><input id="ivQ" placeholder="Tell me about a time you handled conflict"/>
      <label>Your raw notes (situation, what you did, result)</label>
      <textarea id="ivNotes" placeholder="What happened, your actions, measurable result"></textarea>
      <div class="row">
        <button class="btn btn-primary" id="btnStar">Build STAR answer</button>
      </div>
      <div class="out" id="ivOut" style="margin-top:.75rem"></div>
    </div>
  </section>
</main>
<footer>Elevate Edge · Polymath-HQ · Local MVP · Suggestions are not legal or employment advice</footer>
<script>
const $ = (id) => document.getElementById(id);
const views = [...document.querySelectorAll('.view')];
const navBtns = [...document.querySelectorAll('nav button')];

function show(id){
  views.forEach(v => v.classList.toggle('active', v.id === id));
  navBtns.forEach(b => b.classList.toggle('active', b.dataset.view === id));
}
navBtns.forEach(b => b.onclick = () => show(b.dataset.view));
document.querySelectorAll('[data-go]').forEach(b => b.onclick = () => show(b.dataset.go));

fetch('/api/health').then(r=>r.json()).then(j=>{
  $('healthLine').textContent = `AI mode: ${j.llm_mode} · model: ${j.model} · roles loaded: ${j.roles}`;
}).catch(()=>{$('healthLine').textContent='API offline';});

function renderCv(){
  const tpl = $('tpl').value;
  const prev = $('preview');
  prev.className = 'cv-preview ' + tpl;
  const skills = ($('skills').value||'').split(',').map(s=>s.trim()).filter(Boolean);
  const exp = ($('experience').value||'').trim().split(/\n\s*\n/).filter(Boolean);
  let expHtml = exp.map(block=>{
    const lines = block.split('\n').filter(Boolean);
    const title = lines.shift() || '';
    return `<div><strong>${esc(title)}</strong><ul>${lines.map(l=>`<li>${esc(l.replace(/^[-•*]\s*/,''))}</li>`).join('')}</ul></div>`;
  }).join('');
  prev.innerHTML = `
    <h3>${esc($('name').value||'Your Name')}</h3>
    <div class="sub"><strong>${esc($('headline').value||'Professional headline')}</strong><br/>${esc($('contact').value||'Contact details')}</div>
    <h4>Summary</h4><div>${esc($('summary').value||'Add a short professional summary.')}</div>
    <h4>Experience</h4>${expHtml || '<div class="sub">Add experience blocks.</div>'}
    <h4>Education</h4><div>${esc($('education').value||'').replace(/\n/g,'<br/>')}</div>
    <h4>Skills</h4><div>${skills.map(s=>esc(s)).join(' · ')||'—'}</div>`;
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
['name','headline','contact','summary','experience','education','skills','tpl'].forEach(id=>$(id).addEventListener('input', renderCv));
$('tpl').addEventListener('change', renderCv);

$('btnSave').onclick = ()=>{
  const data = {name:$('name').value,headline:$('headline').value,contact:$('contact').value,summary:$('summary').value,experience:$('experience').value,education:$('education').value,skills:$('skills').value,tpl:$('tpl').value};
  localStorage.setItem('elevate_edge_cv', JSON.stringify(data));
  alert('Saved in this browser.');
};
(function load(){
  try{
    const d = JSON.parse(localStorage.getItem('elevate_edge_cv')||'null');
    if(!d) return;
    Object.keys(d).forEach(k=>{if($(k)) $(k).value=d[k];});
  }catch(e){}
  renderCv();
})();
$('btnPrint').onclick = ()=>{
  const w = window.open('','_blank');
  w.document.write(`<html><head><title>CV</title><style>body{font-family:Segoe UI,sans-serif;padding:24px;color:#0f172a}</style></head><body>${$('preview').innerHTML}</body></html>`);
  w.document.close(); w.focus(); w.print();
};
$('btnAiBullets').onclick = async ()=>{
  const role = $('headline').value || 'professional';
  const notes = $('experience').value || $('summary').value;
  $('aiOut').style.display='block'; $('aiOut').textContent='Generating…';
  $('btnAiBullets').disabled=true;
  try{
    const r = await fetch('/api/ai/bullets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,notes})});
    const j = await r.json();
    if(!r.ok) throw new Error(j.error||'failed');
    $('aiOut').textContent = j.text;
  }catch(e){$('aiOut').textContent=String(e.message||e);}
  finally{$('btnAiBullets').disabled=false;}
};

let ROLES=[];
fetch('/api/roles').then(r=>r.json()).then(list=>{
  ROLES=list;
  const grid=$('roleGrid');
  grid.innerHTML='';
  list.forEach(role=>{
    const el=document.createElement('div');
    el.className='panel role-card';
    el.innerHTML=`<strong>${role.title}</strong><p class="muted" style="margin:.4rem 0 0">${role.summary.slice(0,110)}…</p>`;
    el.onclick=()=>{
      document.querySelectorAll('.role-card').forEach(c=>c.classList.remove('active'));
      el.classList.add('active');
      $('roleDetail').innerHTML=`
        <h2>${role.title}</h2>
        <p class="lead">${role.summary}</p>
        <p><strong>Skills</strong><br/>${role.skills.map(s=>`<span class="tag">${s}</span>`).join('')}</p>
        <p><strong>Sample bullets</strong> (edit before using)</p>
        <ul class="clean">${role.bullets.map(b=>`<li>${b}</li>`).join('')}</ul>
        <div class="row"><button class="btn btn-secondary" id="useBullets">Copy bullets into CV Experience</button></div>`;
      $('useBullets').onclick=()=>{
        const block = `${role.title} — Company (Dates)\n`+role.bullets.map(b=>`- ${b}`).join('\n');
        $('experience').value = ($('experience').value? $('experience').value+'\n\n':'') + block;
        renderCv(); show('cv');
      };
    };
    grid.appendChild(el);
  });
});

$('btnStar').onclick = async ()=>{
  $('ivOut').textContent='Working…';
  $('btnStar').disabled=true;
  try{
    const r=await fetch('/api/ai/star',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:$('ivRole').value,question:$('ivQ').value,notes:$('ivNotes').value})});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error||'failed');
    $('ivOut').textContent=j.text;
  }catch(e){$('ivOut').textContent=String(e.message||e);}
  finally{$('btnStar').disabled=false;}
};
</script>
</body></html>
"""


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/api/health")
def health():
    mode = os.getenv("AGENCY_LLM", "mock").lower()
    model = os.getenv("AGENCY_LLM_MODEL", "(default)")
    return jsonify(
        {
            "ok": True,
            "llm_mode": mode,
            "model": model if mode == "openai" else "mock",
            "roles": len(ROLES),
        }
    )


@app.get("/api/roles")
def api_roles():
    return jsonify(ROLES)


@app.post("/api/ai/bullets")
def api_bullets():
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "professional").strip()
    notes = (data.get("notes") or "").strip()
    system = (
        "You are an HR-informed CV writer for Elevate Edge. "
        "Write 4 strong, truthful-sounding achievement bullets for a CV. "
        "Use action verbs and measurable outcomes where possible. "
        "Do not invent employers or fake credentials. "
        "Return bullets only, each on its own line starting with '- '."
    )
    user = f"Target role/headline: {role}\n\nCandidate notes:\n{notes or '(none — write flexible examples clearly marked as examples)'}"
    try:
        text = llm_complete(system, user)
        return jsonify({"text": text})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


@app.post("/api/ai/star")
def api_star():
    data = request.get_json(silent=True) or {}
    role = (data.get("role") or "").strip()
    question = (data.get("question") or "").strip()
    notes = (data.get("notes") or "").strip()
    system = (
        "You are an interview coach for Elevate Edge. "
        "Rewrite the user's notes into a clear STAR answer "
        "(Situation, Task, Action, Result). Be concise and professional. "
        "Do not invent facts not implied by the notes."
    )
    user = f"Role: {role}\nQuestion: {question}\nNotes:\n{notes}"
    try:
        text = llm_complete(system, user)
        return jsonify({"text": text})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


def main():
    host = os.getenv("ELEVATE_HOST", "127.0.0.1")
    # 8088 — safe in Chrome. Avoid 5060 (SIP; ERR_UNSAFE_PORT).
    port = int(os.getenv("ELEVATE_PORT", "8088"))
    print(f"Elevate Edge → http://{host}:{port}")
    print("Stop with Ctrl+C")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
