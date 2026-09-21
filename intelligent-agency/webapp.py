#!/usr/bin/env python3
"""Local browser UI for Intelligent Agency.

    set AGENCY_LLM=openai
    set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
    set AGENCY_LLM_API_KEY=ollama
    set AGENCY_LLM_MODEL=gemma2:2b
    python webapp.py

Then open http://127.0.0.1:5000
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from flask import Flask, jsonify, render_template_string, request

from agency import build_agency

app = Flask(__name__)
PRESIDENT = build_agency()

PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Polymath HQ — Intelligent Agency</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --border: #2d3a4f;
      --text: #e7ecf3;
      --muted: #8b9bb4;
      --accent: #3b82f6;
      --accent2: #22c55e;
      --warn: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }
    header h1 {
      margin: 0;
      font-size: 1.15rem;
      font-weight: 600;
    }
    header span { color: var(--muted); font-size: 0.85rem; }
    main {
      max-width: 880px;
      margin: 0 auto;
      padding: 1.25rem;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem;
      margin-bottom: 1rem;
    }
    label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 0.35rem; }
    textarea {
      width: 100%;
      min-height: 100px;
      resize: vertical;
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.75rem;
      font: inherit;
    }
    textarea:focus { outline: 2px solid var(--accent); border-color: transparent; }
    .row {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      margin-top: 0.75rem;
    }
    button {
      border: none;
      border-radius: 8px;
      padding: 0.6rem 1rem;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    button.primary { background: var(--accent); color: white; }
    button.secondary { background: var(--border); color: var(--text); }
    button:disabled { opacity: 0.55; cursor: wait; }
    .route {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.5rem;
      margin-bottom: 0.75rem;
    }
    .pill {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.55rem 0.7rem;
    }
    .pill strong { display: block; font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .pill span { font-size: 0.95rem; }
    .answer {
      white-space: pre-wrap;
      line-height: 1.5;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.9rem;
      min-height: 4rem;
    }
    .error { color: #fca5a5; }
    .find-list { margin: 0; padding-left: 1.1rem; color: var(--muted); }
    .find-list li { margin: 0.25rem 0; }
    .find-list b { color: var(--accent2); }
    footer {
      text-align: center;
      color: var(--muted);
      font-size: 0.75rem;
      padding: 1rem;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Polymath HQ · Intelligent Agency</h1>
      <span>Local browser UI · routes to specialist agents</span>
    </div>
    <span id="backendHint">Backend: check /api/health</span>
  </header>
  <main>
    <div class="card">
      <label for="q">Your request</label>
      <textarea id="q" placeholder="e.g. write a short lesson plan about fractions for grade 5"></textarea>
      <div class="row">
        <button class="primary" id="askBtn" type="button">Ask agency</button>
        <button class="secondary" id="findBtn" type="button">Find field only</button>
      </div>
    </div>
    <div class="card" id="resultCard" hidden>
      <div class="route">
        <div class="pill"><strong>President</strong><span id="rPres">—</span></div>
        <div class="pill"><strong>Director</strong><span id="rDir">—</span></div>
        <div class="pill"><strong>Agent</strong><span id="rAgent">—</span></div>
      </div>
      <label>Answer</label>
      <div class="answer" id="rAnswer"></div>
      <div id="findBlock" hidden style="margin-top:1rem">
        <label>Top matching fields</label>
        <ol class="find-list" id="findList"></ol>
      </div>
    </div>
  </main>
  <footer>Runs only on your machine · uses AGENCY_LLM_* env vars (Ollama / OpenAI-compatible)</footer>
  <script>
    async function health() {
      try {
        const r = await fetch("/api/health");
        const j = await r.json();
        document.getElementById("backendHint").textContent =
          `Directors: ${j.directors} · LLM mode: ${j.llm_mode} · model: ${j.model}`;
      } catch (e) {
        document.getElementById("backendHint").textContent = "API offline";
      }
    }
    health();

    const qEl = document.getElementById("q");
    const askBtn = document.getElementById("askBtn");
    const findBtn = document.getElementById("findBtn");
    const resultCard = document.getElementById("resultCard");
    const findBlock = document.getElementById("findBlock");

    function setBusy(busy) {
      askBtn.disabled = busy;
      findBtn.disabled = busy;
      askBtn.textContent = busy ? "Working…" : "Ask agency";
    }

    askBtn.onclick = async () => {
      const query = qEl.value.trim();
      if (!query) return;
      setBusy(true);
      resultCard.hidden = false;
      findBlock.hidden = true;
      document.getElementById("rAnswer").textContent = "Routing and generating… (first Ollama reply can take a minute)";
      document.getElementById("rAnswer").className = "answer";
      try {
        const r = await fetch("/api/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.statusText);
        document.getElementById("rPres").textContent = j.president || "—";
        document.getElementById("rDir").textContent = j.director || "—";
        document.getElementById("rAgent").textContent = j.agent || "—";
        document.getElementById("rAnswer").textContent = j.answer || "";
      } catch (e) {
        document.getElementById("rAnswer").textContent = String(e.message || e);
        document.getElementById("rAnswer").className = "answer error";
      } finally {
        setBusy(false);
      }
    };

    findBtn.onclick = async () => {
      const query = qEl.value.trim();
      if (!query) return;
      setBusy(true);
      resultCard.hidden = false;
      findBlock.hidden = false;
      document.getElementById("rAnswer").textContent = "Matching fields only (no model call).";
      document.getElementById("rAnswer").className = "answer";
      try {
        const r = await fetch("/api/find", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || r.statusText);
        document.getElementById("rPres").textContent = j.president || "Atlas";
        document.getElementById("rDir").textContent = j.matches?.[0]?.name || "—";
        document.getElementById("rAgent").textContent = "(find only)";
        const ol = document.getElementById("findList");
        ol.innerHTML = "";
        (j.matches || []).forEach((m) => {
          const li = document.createElement("li");
          li.innerHTML = `<b>${m.score.toFixed(2)}</b> — ${m.name}: ${m.description}`;
          ol.appendChild(li);
        });
      } catch (e) {
        document.getElementById("rAnswer").textContent = String(e.message || e);
        document.getElementById("rAnswer").className = "answer error";
      } finally {
        setBusy(false);
      }
    };

    qEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) askBtn.click();
    });
  </script>
</body>
</html>
"""


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/api/health")
def health():
    mode = os.getenv("AGENCY_LLM", "mock").lower()
    model = os.getenv("AGENCY_LLM_MODEL", "(default)")
    base = os.getenv("AGENCY_LLM_BASE_URL", "")
    return jsonify(
        {
            "ok": True,
            "directors": len(PRESIDENT.directors),
            "llm_mode": mode,
            "model": model if mode == "openai" else "mock",
            "base_url": base,
        }
    )


@app.post("/api/ask")
def api_ask():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    try:
        result = PRESIDENT.handle(query)
        return jsonify(result)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return jsonify({"error": str(exc)}), 500


@app.post("/api/find")
def api_find():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    ranked = PRESIDENT.find_directors(query, top_k=5)
    matches = [
        {"name": d.name, "description": d.description, "score": float(s)}
        for d, s in ranked
    ]
    return jsonify({"president": PRESIDENT.name, "matches": matches})


def main():
    host = os.getenv("AGENCY_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("AGENCY_WEB_PORT", "5000"))
    print(f"Intelligent Agency UI → http://{host}:{port}")
    print("Stop with Ctrl+C")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
