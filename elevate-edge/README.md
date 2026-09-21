# Elevate Edge — Career Service App (MVP)

Local web application for the **Elevate Edge** venture inside Polymath-HQ.

## Features (what you can see now)

| Area | What it does |
|------|----------------|
| **Home** | Brand pitch + navigation |
| **Packages** | Edge Start / Pro / Career pricing board + intake fields |
| **CV Builder** | Structured form, Modern/Classic preview, save in browser, print to PDF |
| **Role Guide** | 8 starter roles with skills + sample bullets (copy into CV) |
| **Interview** | STAR answer helper (AI if Ollama connected) |
| **AI assists** | Bullet suggestions + STAR rewrite via same env as Intelligent Agency |

## Run (Windows + Ollama)

1. Start **Ollama**.
2. Double-click `run-ollama.bat` **or**:

```bat
cd elevate-edge
set AGENCY_LLM=openai
set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
set AGENCY_LLM_API_KEY=ollama
set AGENCY_LLM_MODEL=gemma2:2b
python -m pip install -r requirements.txt
python app.py
```

3. Open **http://127.0.0.1:5060**

Without Ollama, the app still runs; AI buttons return mock/offline text. CV builder and Role Guide work offline.

## Port

Default **5060** (so it does not clash with other local apps on 5000).

```bat
set ELEVATE_PORT=5060
```

## Roadmap linkage

- Service business plan: [`docs/elevate-edge/`](../docs/elevate-edge/)
- Future product name **Pocket HR**: [`docs/elevate-edge/pocket-hr-roadmap.md`](../docs/elevate-edge/pocket-hr-roadmap.md)
- Agency routing for career questions: director **Career Services** in Intelligent Agency
