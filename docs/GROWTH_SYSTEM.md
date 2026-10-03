# HQ Automated Growth System

## Purpose

Polymath HQ has 33 directors. Growth must not depend on ad-hoc edits alone.
This document links **every director**, **R&D**, **Horizon**, and the **Skills**
department into one closed loop so the org chart and skill library can expand
when real capability gaps appear — under human President authority.

## Core principle

> **Skills is the factory. R&D is the scout. Horizon is the continuous scanner.
> Directors are the demand signal. The President is the merge gate.**

No agent merges its own change to `agency.yaml`. Growth always ends in a
President Brief + PR.

---

## Roles in the growth loop

| Actor | Role in growth |
|-------|----------------|
| **Any Director** | Emits demand: "we lack X" or "requests keep routing poorly" |
| **Research & Development** | Discovers novel capabilities, experiments, white-space agents |
| **Horizon (President Advisor)** | Continuous gap scan; proposes improvements; implements on branches |
| **Skills department** | Designs agents/skills, packages specs, maintains the library |
| **Human President** | Approves merge of org-chart / skill-library changes |

### Skills agents (factory)

| Agent | Growth duty |
|-------|-------------|
| **Cross-Department Liaison** | Intake of requests from directors + R&D |
| **Capability Gap Analyst** | Scores missing coverage vs current `agency.yaml` |
| **Skill Architect** | Designs skill / competency models |
| **Agent Designer** | Writes name, mission, keywords, boundaries |
| **Skill Pack Builder** | Packages reusable templates |
| **Skills Librarian** | Versions, catalogues, deprecates |

---

## Growth loop (canonical)

```
Observe (Director traffic, R&D findings, Horizon scan, routing misses)
    → Capture (CapabilityRequest record)
    → Skills intake (Liaison + Gap Analyst)
    → Design (Skill Architect + Agent Designer)
    → Package (Skill Pack Builder + Librarian)
    → Implement on branch (Horizon / Skills via GitHub worker)
    → President Brief + PR
    → Human merge decision
    → Loader rebuilds hierarchy
    → Monitor routing quality
    → Learn (memory + registry status update)
```

This mirrors the Cognitive Core learning loop and Horizon's
`SCAN → VERIFY → CONNECT → CHALLENGE → DESIGN → IMPLEMENT ON BRANCH → TEST → REVIEW → PR`.

---

## How directors are linked

Every director is a **demand node**. When its agents cannot serve a recurring
class of request, or when R&D proposes a capability that belongs under that
director, a `CapabilityRequest` is filed.

### Demand signals (examples)

| Signal | Source | Example |
|--------|--------|---------|
| Routing miss | President / registry rank | Query repeatedly lands on General |
| Explicit ask | Human or Director | "We need a Patent Scout under Legal" |
| R&D experiment | Research & Development | New interdisciplinary agent prototype |
| Horizon scan | President Advisor | Capability registry status = planned with strong evidence |
| External skill pack | Skills Librarian | Importable skill from study forks |

### Supply path

All signals converge on **Skills**. Skills does **not** invent departments
without evidence; it formalises them into YAML-ready specs.

---

## CapabilityRequest schema

Stored in `core/growth/capability_requests.yaml` (backlog) and optionally
enqueued as StateStore work items (`kind: skill_request`).

```yaml
id: req-YYYYMMDD-NNN
status: proposed | accepted | designing | packaged | pr_open | merged | rejected
priority: 1-100   # lower = sooner
requested_by: director_name | R&D | Horizon | human
target_director: existing director name | "new"
proposed_name: "Patent Scout"
kind: agent | skill | director
rationale: |
  Why this is needed; evidence of gap.
keywords: [list]
suggested_description: "..."
suggested_system_prompt: optional
evidence:
  - type: routing_miss | rnd_finding | horizon_scan | human
    detail: "..."
acceptance_criteria:
  - "Routes queries about patents away from General"
  - "Keywords include patent, ip, prior-art"
```

---

## Org-chart growth rules

1. **Prefer agents under existing directors** before creating new directors.
2. **New directors** require: clear domain not covered by keyword sets,
   at least 2–3 proposed agents, and Horizon or R&D corroboration.
3. **Keywords** must be distinct enough that `registry.rank` does not
   constantly collide with neighbouring directors.
4. **General** remains the last-resort catch-all; growth should shrink
   General's load over time.
5. **Security, Finance, Legal, Healthcare** changes stay conservative
   (disclaimers, no advice claims).

---

## Integration points in code

| Component | Growth use |
|-----------|------------|
| `config/agency.yaml` | Source of truth for directors/agents (loader) |
| `core/capability_registry.yaml` | Status of HQ-level capabilities |
| `core/growth/capability_requests.yaml` | Request backlog |
| `StateStore` work kinds | `skill_request`, `agent_proposal`, `org_chart_patch` |
| `HorizonRuntime` | Periodic gap scan → enqueue requests |
| `scripts/capability_scan.py` | Registry vs forks health |
| `scripts/growth_intake.py` | CLI to file a CapabilityRequest |
| Skills agents | Design + package responses to backlog items |

---

## Automated (but not autonomous) growth

"Automated" means:

- Structured intake
- Ranking / prioritisation by Skills
- Spec generation ready for YAML
- Horizon can open the PR

It does **not** mean silent merge or unbounded self-modification.
Merge boundary remains absolute (see Horizon AGENT.md and PolicyEngine).

---

## Success metrics

- Fewer queries falling to General for known domains
- Time from request → merged agent
- Provenance completeness of each new agent/skill
- Zero unauthorized merges of `agency.yaml`
- R&D proposals that become durable agents (not one-off chat)

---

## Next operational steps

1. File requests via `python intelligent-agency/scripts/growth_intake.py ...`
2. Skills / Horizon triage backlog in `core/growth/capability_requests.yaml`
3. Horizon implements accepted specs on `horizon/growth-*` branches
4. President merges with Brief
5. Re-run `cli.py tree` and routing checks
