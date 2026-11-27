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

import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

from flask import (
    Blueprint,
    Flask,
    current_app,
    g,
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash, generate_password_hash

import store

ROOT = Path(__file__).resolve().parent
ROLES_PATH = ROOT / "data" / "roles.json"
DEFAULT_DB_PATH = ROOT / "data" / "elevate.db"

# Reuse the Intelligent Agency LLM backend.
_AGENCY_SRC = ROOT.parent / "intelligent-agency" / "src"
if _AGENCY_SRC.is_dir() and str(_AGENCY_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENCY_SRC))

# The AI path must never pretend to be a model. If the backend package cannot be
# imported we keep the reason and report it -- we do not substitute a mock that
# answers with HTTP 200. (The old code did exactly that, and `/api/health` then
# echoed the AGENCY_LLM env var, so the app claimed "openai" while returning
# canned text.)
_AGENCY_IMPORT_ERROR: Exception | None = None
MockBackend = None
LLMConfigError: type = Exception
try:  # pragma: no cover - exercised by the environment, asserted in tests
    from agency.llm import LLMConfigError, MockBackend, get_backend  # type: ignore  # noqa: F811
except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
    _AGENCY_IMPORT_ERROR = exc
    get_backend = None  # type: ignore[assignment]


class ProviderUnavailable(RuntimeError):
    """No real model can answer right now. Never rendered as a normal answer."""


bp = Blueprint("elevate", __name__)

with open(ROLES_PATH, encoding="utf-8") as f:
    ROLES = json.load(f)


def _analysis_mode(backend) -> str:
    """What would answer a call: 'live', 'simulation', 'unknown' or 'unavailable'."""
    if backend is None:
        return "unavailable"
    if MockBackend is not None and isinstance(backend, MockBackend):
        return "simulation"
    if type(backend).__name__ == "MockBackend":
        return "simulation"
    if getattr(backend, "base_url", None):
        return "live"
    # A configured provider (e.g. the HQ's router) decides per call, so it cannot
    # be classified before one runs -- but it is not a mock.
    return "unknown"


def _backend():
    """The backend that will answer, or :class:`ProviderUnavailable`. No mock fallback."""
    factory = current_app.config.get("ELEVATE_BACKEND_FACTORY")
    if factory is not None:
        return factory()
    if get_backend is None:
        raise ProviderUnavailable(
            "The AI backend package could not be imported "
            f"({type(_AGENCY_IMPORT_ERROR).__name__}: {_AGENCY_IMPORT_ERROR}). "
            "Install elevate-edge/requirements.txt and keep the agency package reachable."
        )
    try:
        return get_backend()
    except LLMConfigError as exc:
        raise ProviderUnavailable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - a broken config is a status, not a crash
        raise ProviderUnavailable(
            f"The AI provider is misconfigured ({type(exc).__name__})."
        ) from exc


def ai_status() -> dict:
    """Report the backend that really answers, not the one the env vars name."""
    try:
        backend = _backend()
    except ProviderUnavailable as exc:
        return {
            "analysis_mode": "unavailable",
            "live": False,
            "model": None,
            "detail": str(exc),
        }
    mode = _analysis_mode(backend)
    model = getattr(backend, "model", None)
    if mode == "simulation":
        detail = (
            "No provider is configured, so the backend would answer with canned text. "
            "Set AGENCY_LLM=openai with AGENCY_LLM_BASE_URL / AGENCY_LLM_API_KEY / "
            "AGENCY_LLM_MODEL (or a local Ollama endpoint)."
        )
    elif mode == "live":
        detail = f"A real provider is configured; answers come from {model or 'the configured model'}."
    else:
        detail = "A provider is configured but which one answers is decided per call."
    return {"analysis_mode": mode, "live": mode in ("live", "unknown"), "model": model, "detail": detail}


def llm_complete(system: str, user: str) -> str:
    backend = _backend()
    if _analysis_mode(backend) == "simulation":
        raise ProviderUnavailable(
            "No provider is configured, so there is no model answer to return."
        )
    text = backend.complete(system, user)
    if not isinstance(text, str) or not text.strip():
        raise ProviderUnavailable("The provider returned an empty answer.")
    return text


def _str_field(data: dict, name: str, default: str = "") -> str:
    """A string field or a 400 -- never an AttributeError 500."""
    value = data.get(name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"'{name}' must be a string.")
    return value.strip()


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
nav a{color:var(--muted);padding:.45rem .75rem;border:1px solid var(--line);border-radius:999px;font-size:.9rem}
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
    <a href="/account">Account</a>
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
          <button class="btn btn-secondary" id="btnSaveAccount">Save to my account</button>
          <button class="btn btn-secondary" id="btnLoadAccount">Load my account CV</button>
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
  const live = j.llm_mode === 'live';
  $('healthLine').textContent = live
    ? `AI: live · model: ${j.model} · roles loaded: ${j.roles}`
    : `AI: ${j.llm_mode} · roles loaded: ${j.roles} — the AI buttons refuse rather than fake an answer.`;
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

function cvState(){
  return {name:$('name').value,headline:$('headline').value,contact:$('contact').value,summary:$('summary').value,experience:$('experience').value,education:$('education').value,skills:$('skills').value,tpl:$('tpl').value};
}
$('btnSave').onclick = ()=>{
  localStorage.setItem('elevate_edge_cv', JSON.stringify(cvState()));
  alert('Saved in this browser.');
};
$('btnSaveAccount').onclick = async ()=>{
  $('aiOut').style.display='block'; $('aiOut').textContent='Saving to your account…';
  const r = await fetch('/api/cv',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:cvState(),title:$('name').value})});
  if(r.status===401){ $('aiOut').textContent='Not signed in. Open Account → Log in to keep a CV on the server.'; return; }
  const j = await r.json().catch(()=>({}));
  $('aiOut').textContent = r.ok ? 'Saved to your account.' : (j.error||'Could not save.');
};
$('btnLoadAccount').onclick = async ()=>{
  const r = await fetch('/api/cv');
  if(r.status===401){ $('aiOut').style.display='block'; $('aiOut').textContent='Not signed in. Open Account → Log in to load your account CV.'; return; }
  const j = await r.json();
  $('aiOut').style.display='block';
  if(!j.cv){ $('aiOut').textContent='No CV stored on your account yet.'; return; }
  Object.keys(j.cv).forEach(k=>{ if($(k)) $(k).value = j.cv[k]; });
  renderCv(); $('aiOut').textContent='Loaded from your account.';
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


# ------------------------------------------------------------- sessions ----
MIN_PASSWORD = 10
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 10 * 60
# Failures per email, in this process only: enough for "5 failures per email per
# 10 minutes -> 429", and a restart simply forgets them.
LOGIN_FAILURES: dict[str, list[float]] = {}


def _db():
    if "db" not in g:
        g.db = store.connect(current_app.config["ELEVATE_DB_PATH"])
    return g.db


def _close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _too_large(exc):
    return jsonify({"error": "Request body is too large."}), 413


def csrf_token() -> str:
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token


def _csrf_ok() -> bool:
    expected = session.get("csrf")
    supplied = request.headers.get("X-CSRF-Token")
    if not supplied and request.form:
        supplied = request.form.get("csrf_token")
    if not supplied:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            supplied = payload.get("csrf_token")
    return bool(expected) and bool(supplied) and hmac.compare_digest(str(expected), str(supplied))


def _csrf_failure():
    return jsonify({"error": "Security token missing or invalid. Reload the page and try again."}), 400


def _request_data() -> dict:
    data: dict = {}
    if request.form:
        data.update(dict(request.form))
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        for key, value in payload.items():
            data.setdefault(key, value)
    return data


def _wants_json() -> bool:
    return bool(request.is_json) or "application/json" in request.headers.get("Accept", "")


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = store.get_user(_db(), user_id)
    if user is None:  # deleted or tampered session
        session.clear()
    return user


def _start_session(user_id: int) -> None:
    """Log in: regenerate the session (new cookie, fresh CSRF token)."""
    session.clear()
    session["user_id"] = int(user_id)
    session["csrf"] = secrets.token_urlsafe(32)


def _recent_failures(email: str) -> list[float]:
    now = time.time()
    failures = [t for t in LOGIN_FAILURES.get(email, []) if now - t < LOGIN_WINDOW_SECONDS]
    if failures:
        LOGIN_FAILURES[email] = failures
    else:
        LOGIN_FAILURES.pop(email, None)
    return failures


def login_blocked(email: str) -> bool:
    return len(_recent_failures(email)) >= LOGIN_MAX_FAILURES


def _record_login_failure(email: str) -> None:
    _recent_failures(email)
    LOGIN_FAILURES.setdefault(email, []).append(time.time())


def _clear_login_failures(email: str) -> None:
    LOGIN_FAILURES.pop(email, None)


def _email_problem(email: str) -> str | None:
    if not email or " " in email or email.count("@") != 1 or len(email) > 254:
        return "Enter a valid email address."
    local, _, domain = email.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return "Enter a valid email address."
    return None


def _password_problem(password: str) -> str | None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    return None


# ----------------------------------------------------------------- pages ----
LAYOUT = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{{ title }} — Elevate Edge</title>
<style>
:root{--bg:#0c1220;--panel:#141c2b;--line:#2a364a;--text:#eef2ff;--muted:#93a0b8;--accent:#3b82f6;--accent2:#14b8a6}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,system-ui,sans-serif;background:var(--bg);color:var(--text)}
a{color:var(--accent2);text-decoration:none}
header{display:flex;gap:1rem;justify-content:space-between;align-items:center;padding:1rem 1.25rem;border-bottom:1px solid var(--line);flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.02em}.brand span{color:var(--accent2)}
nav{display:flex;gap:.9rem;flex-wrap:wrap;align-items:center}
main{max-width:820px;margin:0 auto;padding:1.25rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1.1rem;margin-bottom:1rem}
label{display:block;font-size:.78rem;color:var(--muted);margin:.7rem 0 .25rem;text-transform:uppercase;letter-spacing:.04em}
input{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:.65rem .75rem;font:inherit}
button{border:none;border-radius:10px;padding:.65rem 1rem;font:inherit;font-weight:600;cursor:pointer;background:linear-gradient(135deg,var(--accent),#2563eb);color:#fff;margin-top:.9rem}
button.danger{background:#b91c1c}
.muted{color:var(--muted);font-size:.9rem}
.err{color:#fca5a5}
.ok{color:#6ee7b7}
footer{text-align:center;color:var(--muted);font-size:.75rem;padding:1.5rem}
</style></head>
<body>
<header>
  <div class="brand">Elevate <span>Edge</span></div>
  <nav>
    <a href="/">Home</a>
    <a href="/account">Account</a>
    <a href="/signup">Sign up</a>
    <a href="/login">Log in</a>
  </nav>
</header>
<main>{{ body }}</main>
<footer>Elevate Edge · Polymath-HQ · Suggestions are not legal or employment advice</footer>
</body></html>"""


def _render(title: str, body: str, status: int = 200):
    return render_template_string(LAYOUT, title=title, body=Markup(body)), status


def _signup_form(error: str = "", email: str = "") -> str:
    message = f'<p class="err">{escape(error)}</p>' if error else ""
    return f"""
<div class="panel">
  <h2>Create your account</h2>
  <p class="muted">A free account keeps your CV on the server and gives you
  {store.PLANS['free']} AI drafts per 30 days. No card, no payment — nothing is charged.</p>
  {message}
  <form method="post" action="/signup">
    <input type="hidden" name="csrf_token" value="{csrf_token()}"/>
    <label for="email">Email</label>
    <input id="email" name="email" type="email" autocomplete="email" value="{escape(email)}" required/>
    <label for="password">Password (at least {MIN_PASSWORD} characters)</label>
    <input id="password" name="password" type="password" autocomplete="new-password"
           minlength="{MIN_PASSWORD}" required/>
    <button type="submit">Create account</button>
  </form>
  <p class="muted">Already registered? <a href="/login">Log in</a>.</p>
</div>"""


def _login_form(error: str = "", email: str = "") -> str:
    message = f'<p class="err">{escape(error)}</p>' if error else ""
    return f"""
<div class="panel">
  <h2>Log in</h2>
  {message}
  <form method="post" action="/login">
    <input type="hidden" name="csrf_token" value="{csrf_token()}"/>
    <label for="email">Email</label>
    <input id="email" name="email" type="email" autocomplete="email" value="{escape(email)}" required/>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required/>
    <button type="submit">Log in</button>
  </form>
  <p class="muted">No account yet? <a href="/signup">Sign up</a>.</p>
</div>"""


def _account_page(user, error: str = "", notice: str = "") -> str:
    usage = store.ai_usage(_db(), user["id"])
    message = f'<p class="err">{escape(error)}</p>' if error else ""
    notice_html = f'<p class="ok">{escape(notice)}</p>' if notice else ""
    return f"""
<div class="panel">
  <h2>Your account</h2>
  {message}{notice_html}
  <p><strong>Email</strong><br/>{escape(user['email'])}</p>
  <p><strong>Plan</strong><br/>{escape(usage['plan'])}</p>
  <p><strong>AI drafts this period</strong><br/>
     {usage['used']} used · {usage['remaining']} left of {usage['limit']}
     (30-day window starting {escape(usage['period_start'])})</p>
  <p class="muted">Upgrading is done by the operator: <code>python admin.py grant {escape(user['email'])} pro</code>.
  Payments are not wired yet, so nothing can be charged here.</p>
  <form method="post" action="/logout">
    <input type="hidden" name="csrf_token" value="{csrf_token()}"/>
    <button type="submit">Log out</button>
  </form>
</div>
<div class="panel">
  <h2>Delete account</h2>
  <p class="muted">This deletes your account and the CV stored with it. It cannot be undone.</p>
  <form method="post" action="/api/account/delete">
    <input type="hidden" name="csrf_token" value="{csrf_token()}"/>
    <label for="password">Confirm your password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required/>
    <button type="submit" class="danger">Delete my account</button>
  </form>
</div>"""


# ------------------------------------------------------------------ gate ----
def _entitlement() -> dict:
    """Who is asking, and how much AI they have left. The only source of truth."""
    user = current_user()
    if user is not None:
        usage = store.ai_usage(_db(), user["id"])
        return {"kind": "user", "user_id": user["id"], "email": user["email"], **usage}
    used = session.get("anon_ai_calls", 0)
    if not isinstance(used, int) or used < 0:
        used = 0
    limit = store.PLANS["free"]
    return {
        "kind": "anonymous",
        "plan": "anonymous (not signed in)",
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
    }


def _upgrade_path(ent: dict) -> str:
    if ent["kind"] == "user":
        return (
            "Upgrade to Pro (200 AI drafts per 30 days): the operator runs "
            f"`python admin.py grant {ent['email']} pro`. Payments are not connected yet, "
            "so nothing is charged."
        )
    return (
        "Create a free account at /signup, or ask the operator for a Pro account "
        "(200 AI drafts per 30 days). Payments are not connected yet, so nothing is charged."
    )


def _record_successful_call(ent: dict) -> None:
    if ent["kind"] == "user":
        store.record_ai_call(_db(), ent["user_id"])
    else:
        session["anon_ai_calls"] = int(ent["used"]) + 1


# ---------------------------------------------------------------- routes ----
@bp.get("/")
def home():
    return render_template_string(PAGE)


@bp.get("/signup")
def signup_page():
    return _render("Sign up", _signup_form())


@bp.post("/signup")
def signup():
    if not _csrf_ok():
        return _csrf_failure()
    data = _request_data()
    email = store.normalize_email(data.get("email") if isinstance(data.get("email"), str) else "")
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    wants_json = _wants_json()

    problem = _email_problem(email)
    if problem is None:
        problem = _password_problem(password)
    if problem is not None:
        if wants_json:
            return jsonify({"error": problem}), 400
        return _render("Sign up", _signup_form(problem, email), 400)

    try:
        user_id = store.create_user(_db(), email, generate_password_hash(password))
    except store.DuplicateEmail:
        message = "That email is already registered. Try logging in instead."
        if wants_json:
            return jsonify({"error": message}), 409
        return _render("Sign up", _signup_form(message, email), 409)

    _start_session(user_id)
    if wants_json:
        return jsonify({"email": email, "plan": "free"}), 201
    return redirect("/account", code=303)


@bp.get("/login")
def login_page():
    return _render("Log in", _login_form())


@bp.post("/login")
def login():
    if not _csrf_ok():
        return _csrf_failure()
    data = _request_data()
    email = store.normalize_email(data.get("email") if isinstance(data.get("email"), str) else "")
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    wants_json = _wants_json()

    if login_blocked(email):
        message = "Too many failed logins for that email. Try again in 10 minutes."
        if wants_json:
            return jsonify({"error": message}), 429
        return _render("Log in", _login_form(message, email), 429)

    user = store.get_user_by_email(_db(), email)
    if user is None or not check_password_hash(user["password_hash"], password):
        _record_login_failure(email)
        message = "Email or password is incorrect."
        if wants_json:
            return jsonify({"error": message}), 401
        return _render("Log in", _login_form(message, email), 401)

    _clear_login_failures(email)
    _start_session(user["id"])
    if wants_json:
        return jsonify({"email": user["email"], "plan": user["plan"]}), 200
    return redirect("/account", code=303)


@bp.post("/logout")
def logout():
    if not _csrf_ok():
        return _csrf_failure()
    session.clear()
    if _wants_json():
        return jsonify({"ok": True}), 200
    return redirect("/", code=303)


@bp.get("/account")
def account():
    user = current_user()
    if user is None:
        return redirect("/login", code=303)
    return _render("Your account", _account_page(user))


@bp.get("/api/cv")
def api_cv_get():
    user = current_user()
    if user is None:
        return jsonify({"error": "Sign in to use your account CV."}), 401
    cv = store.get_cv(_db(), user["id"])
    return jsonify(
        {
            "cv": cv["content"] if cv else None,
            "title": cv["title"] if cv else None,
            "updated_at": cv["updated_at"] if cv else None,
        }
    )


@bp.put("/api/cv")
def api_cv_put():
    user = current_user()
    if user is None:
        return jsonify({"error": "Sign in to save a CV to your account."}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "content" not in data:
        return jsonify({"error": "Send JSON with 'content' (the CV builder state)."}), 400
    content = data["content"]
    if not isinstance(content, (dict, str)):
        return jsonify({"error": "'content' must be an object or a string."}), 400
    title = data.get("title")
    if title is not None and not isinstance(title, str):
        return jsonify({"error": "'title' must be a string."}), 400
    # Any 'id'/'user_id' the caller sends is ignored: the row is chosen by session.
    updated = store.save_cv(_db(), user["id"], content, title)
    return jsonify({"ok": True, "updated_at": updated})


@bp.post("/api/account/delete")
def api_account_delete():
    wants_json = _wants_json()
    user = current_user()
    if user is None:
        if wants_json:
            return jsonify({"error": "Sign in first."}), 401
        return redirect("/login", code=303)
    if not _csrf_ok():
        return _csrf_failure()
    data = _request_data()
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    if not password or not check_password_hash(user["password_hash"], password):
        message = "Password is incorrect. Your account was not deleted."
        if wants_json:
            return jsonify({"error": message}), 403
        return _render("Your account", _account_page(user, error=message), 403)
    store.delete_user(_db(), user["id"])
    session.clear()
    if wants_json:
        return jsonify({"ok": True}), 200
    return redirect("/", code=303)


@bp.get("/api/health")
def health():
    status = ai_status()
    return jsonify(
        {
            "ok": True,
            "llm_mode": status["analysis_mode"],
            "model": status["model"] or "none",
            "roles": len(ROLES),
            "ai": status,
        }
    )


@bp.get("/api/roles")
def api_roles():
    return jsonify(ROLES)


def _ai_answer(system: str, user: str):
    """One AI call: is AI real, has the caller credit, then call the provider.

    The gate is checked *before* the provider is called, so a capped caller never
    costs a token; the counter is incremented only after a successful answer.
    """
    status = ai_status()
    if not status["live"]:
        return (
            jsonify(
                {
                    "error": f"AI is not available. {status['detail']} No AI text was produced.",
                    "analysis_mode": status["analysis_mode"],
                    "ai_available": False,
                }
            ),
            503,
        )

    entitlement = _entitlement()
    if entitlement["used"] >= entitlement["limit"]:
        upgrade = _upgrade_path(entitlement)
        return (
            jsonify(
                {
                    "error": (
                        f"AI limit reached: {entitlement['limit']} drafts per 30 days on the "
                        f"{entitlement['plan']} plan. No AI text was produced and the provider "
                        f"was not called. {upgrade}"
                    ),
                    "limit": entitlement["limit"],
                    "used": entitlement["used"],
                    "remaining": 0,
                    "plan": entitlement["plan"],
                    "upgrade": upgrade,
                }
            ),
            402,
        )

    try:
        text = llm_complete(system, user)
    except ProviderUnavailable as exc:
        return (
            jsonify(
                {
                    "error": f"The AI provider is not answering. {exc} Nothing was generated.",
                    "analysis_mode": status["analysis_mode"],
                    "ai_available": False,
                }
            ),
            503,
        )
    except Exception:  # noqa: BLE001 - provider internals never reach the browser
        return (
            jsonify({"error": "The AI provider failed. Please try again later."}),
            502,
        )

    _record_successful_call(entitlement)  # only a success is counted
    return (
        jsonify(
            {
                "text": text,
                "plan": entitlement["plan"],
                "remaining": max(0, entitlement["limit"] - entitlement["used"] - 1),
            }
        ),
        200,
    )


@bp.post("/api/ai/bullets")
def api_bullets():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object with 'role' and 'notes'."}), 400
    try:
        role = _str_field(data, "role") or "professional"
        notes = _str_field(data, "notes")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    system = (
        "You are an HR-informed CV writer for Elevate Edge. "
        "Write 4 strong, truthful-sounding achievement bullets for a CV. "
        "Use action verbs and measurable outcomes where possible. "
        "Do not invent employers or fake credentials. "
        "Return bullets only, each on its own line starting with '- '."
    )
    user = f"Target role/headline: {role}\n\nCandidate notes:\n{notes or '(none — write flexible examples clearly marked as examples)'}"
    return _ai_answer(system, user)


@bp.post("/api/ai/star")
def api_star():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object with 'role', 'question' and 'notes'."}), 400
    try:
        role = _str_field(data, "role")
        question = _str_field(data, "question")
        notes = _str_field(data, "notes")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    system = (
        "You are an interview coach for Elevate Edge. "
        "Rewrite the user's notes into a clear STAR answer "
        "(Situation, Task, Action, Result). Be concise and professional. "
        "Do not invent facts not implied by the notes."
    )
    user = f"Role: {role}\nQuestion: {question}\nNotes:\n{notes}"
    return _ai_answer(system, user)


def _secret_key(dev: bool) -> str:
    key = os.getenv("ELEVATE_SECRET_KEY", "").strip()
    if key:
        return key
    if dev:
        print(
            "!! ELEVATE_SECRET_KEY is not set. Running in development mode with an\n"
            "!! ephemeral session key: every restart logs everyone out. Never run a\n"
            "!! real deployment this way -- set ELEVATE_SECRET_KEY.",
            file=sys.stderr,
        )
        return secrets.token_hex(32)
    raise RuntimeError(
        "ELEVATE_SECRET_KEY is not set, so sessions cannot be signed. Refusing to start. "
        "Set ELEVATE_SECRET_KEY to a long random value, or ELEVATE_DEV=1 for local "
        "development only (ephemeral key, one loud warning)."
    )


def create_app(config: dict | None = None) -> Flask:
    """Build the app. Refuses to start without a session secret outside dev."""
    config = dict(config or {})
    dev = os.getenv("ELEVATE_DEV", "") == "1"
    application = Flask(__name__)
    application.config.update(
        MAX_CONTENT_LENGTH=64 * 1024,
        ELEVATE_DB_PATH=os.getenv("ELEVATE_DB_PATH") or str(DEFAULT_DB_PATH),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not dev,
        ELEVATE_DEV=dev,
        SECRET_KEY=config.get("SECRET_KEY") or _secret_key(dev),
    )
    application.config.update(config)
    store.init_db(application.config["ELEVATE_DB_PATH"])
    application.register_blueprint(bp)
    application.teardown_appcontext(_close_db)
    application.register_error_handler(413, _too_large)
    return application


app = create_app()


def main():
    host = os.getenv("ELEVATE_HOST", "127.0.0.1")
    # 8088 — safe in Chrome. Avoid 5060 (SIP; ERR_UNSAFE_PORT).
    port = int(os.getenv("ELEVATE_PORT", "8088"))
    print(f"Elevate Edge → http://{host}:{port}")
    print(f"Database: {app.config['ELEVATE_DB_PATH']}")
    print("Stop with Ctrl+C")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
