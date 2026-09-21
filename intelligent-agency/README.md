# Intelligent Agency

A hierarchical, multi-domain AI agent system.

```
                        President  (Atlas)
                            |  oversees everything
   ┌───────────┬───────────┼───────────┬───────────┐
Education   Coding     Finance    Agriculture   ...   (Directors, one per field)
   |            |          |            |
 Tutor      Debugger   Accountant   Crop Specialist   ...   (Agents, the workers)
```

- **One President** oversees every director and dispatches each request to the
  right field.
- **Each Director** owns a single field (education, coding, hospitality,
  marketing, shares & trading, finance, business, product development,
  agriculture, automation, electronics, and a general catch-all) and routes
  work to its own team.
- **Each Agent** is a specialist that actually does the work.

The whole org chart lives in one file — [`config/agency.yaml`](config/agency.yaml).
Add a new field or a new specialist by editing that file; **no code changes
needed**.

## Quick start

```bash
pip install -r requirements.txt

# See the whole organisation
python cli.py tree

# Ask "which field handles this?"
python cli.py find "how do I fertilise my tomato crop"

# Route a request all the way down and get an answer
python cli.py ask  "debug my python API that returns 500 errors"
```

It runs **offline out of the box** using a built-in mock backend, so you can
see the routing work without any API keys.

## Plugging in a real model

Set these environment variables to use any OpenAI-compatible endpoint —
including a **local gateway such as OmniRoute**:

```bash
export AGENCY_LLM=openai
export AGENCY_LLM_BASE_URL=http://127.0.0.1:20128/v1   # e.g. OmniRoute
export AGENCY_LLM_API_KEY=sk-...
export AGENCY_LLM_MODEL=gpt-4o-mini
```

On Windows PowerShell use `$env:AGENCY_LLM="openai"` etc.

## How routing works

When a request arrives:

1. The **President** scores it against every director's name, description and
   keywords and picks the best-matching field.
2. That **Director** scores it against its own agents and picks the best
   specialist.
3. The **Agent** answers (via the mock backend, or a real model if configured).

Scoring lives in [`src/agency/registry.py`](src/agency/registry.py). It is a
small, dependency-free keyword-overlap ranker today; you can swap it for a
semantic/embedding ranker later without touching the rest of the code.

## Project layout

```
intelligent-agency/
├── cli.py                 # command-line entry point
├── config/agency.yaml     # THE org chart — edit this to extend the agency
├── src/agency/
│   ├── base.py            # Role enum + shared Node base class
│   ├── agent.py           # Agent (worker)
│   ├── director.py        # Director (owns a field + its agents)
│   ├── president.py       # President (oversees all directors)
│   ├── registry.py        # routing / scoring engine
│   ├── llm.py             # pluggable LLM backend (mock + OpenAI-compatible)
│   └── loader.py          # builds the hierarchy from the YAML
├── examples/run_demo.py
└── tests/test_routing.py
```

## Adding a new field

Append to `config/agency.yaml`:

```yaml
  - name: "Healthcare"
    description: "Clinical, wellness and medical information."
    keywords: [health, medical, clinic, patient, wellness]
    agents:
      - {name: "Nurse Advisor", description: "General health info.", keywords: [symptom, care, advice]}
```

Run `python cli.py tree` and it appears immediately.

## Tests

```bash
pip install pytest
pytest -q
```

## Notes & honesty

- The specialists in finance, tax, legal and healthcare-style fields provide
  **general information only**, not professional/licensed advice.
- Answer quality depends on the model you connect. The mock backend is for
  demonstrating routing, not for real answers.

## License

MIT — see [LICENSE](LICENSE).
