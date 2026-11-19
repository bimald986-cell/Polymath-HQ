# Polymath-HQ

Headquarters for multi-domain intelligent systems and ventures.

## Projects

| Project | Path | Description |
|---------|------|-------------|
| **Elevate Edge (app)** | [`elevate-edge/`](elevate-edge/) | **Runnable** career web MVP — CV builder, roles, interview, packages |
| **Intelligent Agency** | [`intelligent-agency/`](intelligent-agency/) | Hierarchical multi-domain AI agent system |
| **Elevate Edge (plan)** | [`docs/elevate-edge/`](docs/elevate-edge/) | Business plan, 90-day steps, Pocket HR + Nepal boards |
| **Mind & Mythos** | external: [mind-mythos](https://github.com/bimald986-cell/mind-mythos) | Audio-first content brand; registered in HQ project registry |

## Capability study forks

Registered under this account for Horizon scanning (see [`docs/EXTERNAL_FORKS_INTEGRATION.md`](docs/EXTERNAL_FORKS_INTEGRATION.md)):

| Fork | Role |
|------|------|
| [automaton](https://github.com/bimald986-cell/automaton) | Agent loop, policy, heartbeat patterns (study) |
| [deepseek-harness](https://github.com/bimald986-cell/deepseek-harness) | Plugin harness (experimental) |
| [emilkowalski_skills](https://github.com/bimald986-cell/emilkowalski_skills) | Design / animation skills (adopt for UI) |
| [public-apis](https://github.com/bimald986-cell/public-apis) | Public API catalog (reference only) |

## Project registry

Known external/internal projects for Horizon and the dashboard:

- [`core/projects.yaml`](core/projects.yaml)
- Capability status: [`core/capability_registry.yaml`](core/capability_registry.yaml)
- Mind & Mythos runbook: [`docs/MIND_MYTHOS_INTEGRATION.md`](docs/MIND_MYTHOS_INTEGRATION.md)
- External forks guide: [`docs/EXTERNAL_FORKS_INTEGRATION.md`](docs/EXTERNAL_FORKS_INTEGRATION.md)
- Skills: [`docs/skills/README.md`](docs/skills/README.md)

## Quick start — Elevate Edge app (see something working)

```bash
cd elevate-edge
pip install -r requirements.txt

# Optional AI (Ollama example)
export AGENCY_LLM=openai
export AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
export AGENCY_LLM_API_KEY=ollama
export AGENCY_LLM_MODEL=gemma2:2b

python app.py
# open http://127.0.0.1:5060
```

Windows: double-click `elevate-edge/run-ollama.bat`.

## Quick start — Intelligent Agency (the HQ)

```bash
cd intelligent-agency
pip install -r requirements.txt

# 1. What is ready, and what is missing (no network calls, no writes)
python cli.py doctor

# 2. The org chart and routing — works with no provider
python cli.py tree
python cli.py find "rewrite my resume for a marketing role"

# 3. Real tools, through the policy gate
python cli.py tools
python cli.py tool read_file --arg path=README.md

# 4. The control room — local only, no authentication, so keep it on 127.0.0.1
python dashboard.py        # http://127.0.0.1:8765
```

**Answers are only real once a provider is set.** With nothing configured, every
surface (dashboard chat, `ask`, `advise`, the scheduled cycle) runs in
`simulation` and says so, returning placeholder text instead of reasoning:

```bash
export AGENCY_LLM=openai                                  # 'openai' = any OpenAI-compatible endpoint
export AGENCY_LLM_BASE_URL=https://api.openai.com/v1      # your endpoint's base, ending /v1
export AGENCY_LLM_MODEL=<model id exactly as the provider spells it>
export AGENCY_LLM_API_KEY=<your key>                      # never commit this
```

Local Ollama works through its OpenAI-compatible endpoint:
`AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1`, `AGENCY_LLM_API_KEY=ollama`.

**Work a registered project.** `--project` takes the repository and default branch
from [`core/projects.yaml`](core/projects.yaml); an unknown project is refused
before any network call, and a contradicting `--repo` is an error, never a silent
pick:

```bash
PYTHONPATH=src python -m agency.horizon_worker_main --once --project polymath-hq
PYTHONPATH=src python -m agency.horizon_worker_main --once --project polymath-hq --publish-github
```

The four-hourly cycle (`.github/workflows/horizon-scheduled.yml`) reads the same
four settings from repository **variables** (`AGENCY_LLM`,
`AGENCY_LLM_BASE_URL`, `AGENCY_LLM_MODEL`) and the **secret**
`AGENCY_LLM_API_KEY`. With nothing set it stays on mock by design and records
`analysis_mode: simulation`; it never silently becomes real. The cycle has no
tools, so it reasons and records a recommendation — it does not open PRs or edit
the repo.

**What a run costs.** `config/prices.yaml` ships empty on purpose, so every run
reports `cost: unknown` rather than a made-up figure. Adding a rate is a data-only
change: one entry naming the exact model, its published per-million-token input
and output prices, and a source URL.

## License

MIT — see [intelligent-agency/LICENSE](intelligent-agency/LICENSE).
