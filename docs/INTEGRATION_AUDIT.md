# Upstream Integration Audit

This document records what HQ may learn from the reviewed forks. It is an engineering map, not permission to copy code indiscriminately.

| Source | Valuable capabilities | HQ approach | License note |
|---|---|---|---|
| `the-agency` | specialist roles, workstreams, inter-session collaboration, pause/pickup, quality gates, safety hooks | adapt framework patterns and compatible MIT components after file-level review | core framework MIT; bundled app workstreams may carry separate reference-source terms |
| `TencentDB-Agent-Memory` | layered chat memory, skills, Wiki, CodeGraph, agent loadouts, ACLs, provenance | primary design reference for HQ memory/knowledge plane; integrate compatible components incrementally | MIT in reviewed fork |
| `memoryhub` | centralized memory API, immediate indexing, hybrid exact/semantic retrieval, human-readable Markdown | use simple storage/retrieval ideas where they complement the primary memory plane | MIT |
| `browser-use` | browser agent, custom tools, local/cloud browser adapters | build an HQ browser adapter with policy, approvals and audit trail | open-source library documented as MIT; hosted services are separate |
| `openmontage` | production pipelines, provider selection, storyboard approvals, cost tracking, narration/music/subtitles, media QA | use as architectural research; independently implement HQ media workflow or isolate as an external service | AGPLv3: do not copy into private HQ core without a deliberate licensing decision |

## Integration policy
1. Inventory before import.
2. Check file-level licenses and notices.
3. Prefer adapters over vendoring large frameworks.
4. Keep upstream attribution where required.
5. Never commit secrets or copied environment files.
6. Sandbox new dependencies and run security/test gates.
7. Promote only measured capabilities into the HQ registry.
8. Preserve a provenance record for every imported/adapted component.
