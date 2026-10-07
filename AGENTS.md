# Portfolio Memory Router

This file is the small, cross-agent entrypoint for Bimal's project portfolio.

## Rule
Do **not** scan every repository at the start of a task.

1. Read `memory/PORTFOLIO_INDEX.md`.
2. Identify the one or few projects relevant to the request.
3. Read only those capsules under `memory/projects/`.
4. Treat capsule status as a navigation hint, not proof of current GitHub state.
5. Before changing code, deploying, merging, publishing, sending outreach, or making a claim that depends on current state, verify the relevant repo/file/PR/CI directly.
6. After a material project decision or milestone, update that project's capsule and `last_verified`.
7. Never store secrets, credentials, private keys, personal health data, or unnecessary PII in memory files.
8. Prefer concise durable facts: purpose, canonical repo, architecture, current state, next gate, non-negotiables, and pointers.

## Authority
Repository code, tests, current issues/PRs, and canonical project documents outrank these memory capsules when they conflict.

## Token discipline
The index should remain short enough to scan cheaply. Detailed history belongs in project docs, Git history, issues, or dedicated references—not in startup memory.
