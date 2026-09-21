# Intelligent Agency

A hierarchical, multi-domain AI agent system.

```
                        President  (Atlas)
                            |  oversees everything
   ┌───────────┬───────────┼───────────┬───────────┐
Education   Coding     Finance    Healthcare   ...   (Directors, one per field)
   |            |          |            |
 Tutor      Debugger   Accountant   Clinician Info   ...   (Agents, the workers)
```

- **One President** oversees every director and dispatches each request to the
  right field.
- **Each Director** owns a single field and routes work to its own team.
- **Each Agent** is a specialist that actually does the work.

The whole org chart lives in one file — [`config/agency.yaml`](config/agency.yaml).
Add a new field or a new specialist by editing that file; **no code changes
needed**.

## Domains (Directors)

| Field | Focus |
|-------|--------|
| Education | Teaching, curricula, lessons, assessment |
| Learning | Study strategy, research skills, skill paths |
| Coding | Software engineering, debug, DevOps |
| Hospitality | Guests, bookings, events, menus |
| Marketing | SEO, content, social, ads |
| Shares & Trading | Equities, crypto, risk *(general info only)* |
| Finance | Accounting, budget, tax *(general info only)* |
| Business | Strategy, operations, HR |
| Product Development | PM, UX, QA |
| Agriculture | Crops, livestock, soil, pests |
| Automation | Workflows, RPA, IoT |
| Electronics | Circuits, embedded, PCB, sensors |
| **Healthcare** | Clinical concepts, pharmacy, public & mental health *(not medical advice)* |
| **Legal** | Contracts, compliance, litigation, IP *(not legal advice)* |
| **AI & Intelligence** | ML, LLMs, agents, AI ethics |
| **Science** | Research methods, life & physical sciences |
| **Cybersecurity** | Architecture, threats, privacy |
| **Data & Analytics** | Pipelines, BI, statistics |
| General | Catch-all |

## Quick start

```bash
pip install -r requirements.txt

# See the whole organisation
python cli.py tree

# Ask "which field handles this?"
python cli.py find "how do I fertilise my tomato crop"
python cli.py find "review this NDA clause"
python cli.py find "design a RAG pipeline"

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
  - name: "Real Estate"
    description: "Property, leasing and valuation concepts."
    keywords: [property, real-estate, lease, rent, valuation]
    agents:
      - {name: "Leasing Advisor", description: "Lease terms and tenant basics.", keywords: [lease, rent, tenant]}
```

Run `python cli.py tree` and it appears immediately.

## Tests

```bash
pip install pytest
pytest -q
```

## Notes & honesty

- **Healthcare, Legal, Finance, Shares & Trading** specialists provide **general
  information only**. They are **not** licensed medical, legal, tax, or
  investment advice. For emergencies or binding decisions, consult a qualified
  professional in your jurisdiction.
- Answer quality depends on the model you connect. The mock backend is for
  demonstrating routing, not for real answers.

## License

MIT — see [LICENSE](LICENSE).
