# Polymath-HQ

Headquarters for multi-domain intelligent systems.

This repository currently hosts **Intelligent Agency** — a hierarchical, config-driven multi-agent organisation (President → Directors → Agents) that routes questions to the right specialist field.

## Projects

| Project | Path | Description |
|---------|------|-------------|
| **Intelligent Agency** | [`intelligent-agency/`](intelligent-agency/) | Hierarchical multi-domain AI agent system |

## Quick start (Intelligent Agency)

```bash
cd intelligent-agency
pip install -r requirements.txt

python cli.py tree
python cli.py find "how do I fertilise my tomato crop"
python cli.py ask  "debug my python API that returns 500 errors"
```

Runs offline with a mock LLM by default. See [`intelligent-agency/README.md`](intelligent-agency/README.md) for connecting a real model and extending the org chart.

## Domains (Directors)

Education · Learning · Coding · Hospitality · Marketing · Shares & Trading · Finance · Business · Product Development · Agriculture · Automation · Electronics · Healthcare · Legal · AI & Intelligence · Science · Cybersecurity · Data & Analytics · **Engineering** · **Environment & Climate** · **Government & Policy** · **Real Estate** · **Media & Journalism** · **Languages & Translation** · **Psychology** · **Philosophy & Ethics** · General

## License

MIT — see [intelligent-agency/LICENSE](intelligent-agency/LICENSE).
