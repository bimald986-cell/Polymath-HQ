# Elevate Edge — Career Service App (MVP)

Local web application for the **Elevate Edge** venture inside Polymath-HQ.

## Features

| Area | What it does |
|------|----------------|
| **Home** | Brand pitch + navigation |
| **Packages** | Edge Start / Pro / Career pricing board + intake fields |
| **CV Builder** | Structured form, Modern/Classic preview, save in browser, print to PDF |
| **Role Guide** | 8 starter roles with skills + sample bullets |
| **Interview** | STAR answer helper (AI if Ollama connected) |

## Run (Windows + Ollama)

```bat
cd elevate-edge
run-ollama.bat
```

Or:

```bat
set AGENCY_LLM=openai
set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
set AGENCY_LLM_API_KEY=ollama
set AGENCY_LLM_MODEL=gemma2:2b
set ELEVATE_PORT=8088
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8088**

### Port note

Do **not** use port **5060** — Chrome blocks it (`ERR_UNSAFE_PORT`, SIP). Default is **8088**.

## Without AI

App still runs; CV Builder and Role Guide work offline. AI buttons need Ollama (or another OpenAI-compatible backend).
