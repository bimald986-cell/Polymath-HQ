# Polymath-HQ

Headquarters for multi-domain intelligent systems and ventures.

## Projects

| Project | Path | Description |
|---------|------|-------------|
| **Intelligent Agency** | [`intelligent-agency/`](intelligent-agency/) | Hierarchical multi-domain AI agent system |
| **Elevate Edge** | [`docs/elevate-edge/`](docs/elevate-edge/) | Career service venture board (CV, LinkedIn, coaching) + Pocket HR roadmap |

## Quick start (Intelligent Agency)

```bash
cd intelligent-agency
pip install -r requirements.txt

python cli.py tree
python cli.py find "rewrite my resume for a marketing manager role"
python cli.py ask  "help me structure a STAR interview answer"
```

Optional local browser UI (Ollama or any OpenAI-compatible backend):

```bash
# see intelligent-agency/run-web-ollama.bat on Windows
python webapp.py
# open http://127.0.0.1:5000
```

## Ventures

- **Elevate Edge** — start as manual career services; scale in Nepal later; product path = Pocket HR.  
  Docs: [docs/elevate-edge/README.md](docs/elevate-edge/README.md)

## License

MIT — see [intelligent-agency/LICENSE](intelligent-agency/LICENSE).
