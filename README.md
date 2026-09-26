# Polymath-HQ

Headquarters for multi-domain intelligent systems and ventures.

## Projects

| Project | Path | Description |
|---------|------|-------------|
| **Elevate Edge (app)** | [`elevate-edge/`](elevate-edge/) | **Runnable** career web MVP — CV builder, roles, interview, packages |
| **Intelligent Agency** | [`intelligent-agency/`](intelligent-agency/) | Hierarchical multi-domain AI agent system |
| **Elevate Edge (plan)** | [`docs/elevate-edge/`](docs/elevate-edge/) | Business plan, 90-day steps, Pocket HR + Nepal boards |
| **Mind & Mythos** | external: [mind-mythos](https://github.com/bimald986-cell/mind-mythos) | Audio-first content brand; registered in HQ project registry |

## Project registry

Known external/internal projects for Horizon and the dashboard:

- [`core/projects.yaml`](core/projects.yaml)
- Mind & Mythos runbook: [`docs/MIND_MYTHOS_INTEGRATION.md`](docs/MIND_MYTHOS_INTEGRATION.md)

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

## Quick start — Intelligent Agency

```bash
cd intelligent-agency
pip install -r requirements.txt
python cli.py tree
python cli.py find "rewrite my resume for a marketing role"
```

## License

MIT — see [intelligent-agency/LICENSE](intelligent-agency/LICENSE).
