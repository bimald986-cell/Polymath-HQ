# Polymath HQ Cognitive Core

## Mission
Polymath HQ is the master orchestration system for research, product creation, software, media, education, analysis, and future project types. HQ should learn reusable workflows, preserve evidence, coordinate specialist agents, and improve its own processes without silently changing production systems.

## Governance
- **President**: human authority. Sets goals, approves consequential actions, budgets, publishing, deployment, external communications, financial actions, and major architectural changes.
- **Director**: operational orchestrator. Converts goals into plans, assigns agents/tools, tracks dependencies, and assembles results.
- **President Advisor (Horizon)**: continuous improvement and horizon-scanning agent. Challenges assumptions, studies new capabilities, detects gaps, proposes experiments, and maintains an evidence-backed improvement backlog. Horizon advises; it does not override the President or silently deploy self-modifications.
- **Reviewer/Auditor**: independent quality and safety gate.

## Core layers
1. `core/` orchestration, planning, policy, events, capability registry.
2. `agents/` role contracts and specialist agents.
3. `memory/` layered memory, skills, wiki, code graph, provenance and retrieval.
4. `tools/` adapters for browser, GitHub, files, web, coding, media and connectors.
5. `workflows/` reusable pipelines for software, research, media, publishing, education and market intelligence.
6. `qa/` tests, reviewers, safety checks and release gates.
7. `projects/` thin project adapters and project-specific state.
8. `control/` approvals, audit log, dashboard and observability.

## Imported design lessons
### The Agency
Adopt role specialization, workstreams, persistent handoffs, inter-session collaboration, quality gates and safe command/tool boundaries. Do not import unrelated reference-source applications.

### TencentDB Agent Memory
Use its concepts as the primary memory model: layered memories, reusable skills, Wiki, CodeGraph, ownership/version/status, role/agent loadouts, and controlled visibility. Preserve provenance for every learned asset.

### MemoryHub
Borrow simple human-readable memory storage and hybrid semantic/exact retrieval principles where they reduce complexity.

### Browser Use
Integrate through an adapter rather than copying the repository. Browser actions must obey allowlists, approval rules, credential boundaries and audit logging.

### OpenMontage
Study pipeline selection, provider registry, storyboards, creative approval gates, cost tracking, media QA and reproducible production manifests. Do not copy AGPL code into the private HQ core. Reimplement needed ideas independently or keep OpenMontage as a clearly separated external service if ever used.

## Learning loop
`Observe -> Capture evidence -> Distill -> Propose -> Sandbox experiment -> Evaluate -> Human/reviewer approval -> Promote -> Monitor -> Learn`

Learning is never equivalent to autonomous production modification. Proposed improvements are versioned, testable and reversible.

## Capability contract
Every capability declares:
- purpose and owner
- accepted inputs / produced outputs
- tools and model requirements
- permissions and external side effects
- expected cost/latency
- evidence/provenance requirements
- tests and quality gates
- rollback/failure behavior

## Non-negotiable principles
- Human authority over consequential actions.
- Evidence before confidence.
- No fabricated capabilities or sources.
- Least privilege for agents and tools.
- Secrets never committed to Git.
- External actions are auditable.
- New third-party code is license-reviewed before incorporation.
- Experiments run in sandboxes before promotion.
- Memory is scoped; retrieval should provide the minimum relevant context.
- Project-specific truth remains distinguishable from global HQ knowledge.
