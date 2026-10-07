# Portfolio Memory Router Setup

## Goal
Give multiple AI coding/chat systems a small shared project map without loading every repository on every request.

## Canonical memory
- `AGENTS.md`: universal routing and verification contract.
- `memory/PORTFOLIO_INDEX.md`: compact project map.
- `memory/projects/*.md`: one concise capsule per project.
- `.claude/skills/portfolio-memory/SKILL.md`: Claude-compatible skill entry.
- `.agents/skills/portfolio-memory/SKILL.md`: portable skill entry for agents that support this convention.

## Agent behavior
At session/task start, do not ingest every project. When an existing project is mentioned, load the index, then only that project's capsule. Inspect live repository evidence only when freshness or action requires it.

## Updating memory
Update a capsule only after a durable decision or verified milestone. Keep historical detail in project docs/issues/Git, not memory. Include a current gate and verification pointers rather than long narratives.

## Other chatbots
If a tool cannot auto-discover AGENTS.md or SKILL.md, give it this instruction:
"Use Polymath-HQ/AGENTS.md as the portfolio routing contract. Read memory/PORTFOLIO_INDEX.md, then load only the capsule for the project I mention. Treat memory as navigation context and verify live repo state before consequential claims or changes."

If the chatbot has no GitHub/repository access, attach/copy only AGENTS.md, PORTFOLIO_INDEX.md and the relevant project capsule.

## Safety
Never store passwords, API keys, access tokens, private keys, sensitive personal records or unnecessary PII in portfolio memory.
