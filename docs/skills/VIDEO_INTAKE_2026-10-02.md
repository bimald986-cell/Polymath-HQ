# Capability intake from TikTok video (Duncan Rogoff / @duncanrogoff) — 2026-10-02

Five relatively new high-star repos recommended for Claude / coding-agent users. Reviewed and forked into the account as study / skills libraries where useful for Polymath-HQ and the 30-day income path.

## Repos

| # | Repo | Why it matters for HQ |
|---|------|------------------------|
| 5 | **Tencent/BrowserSkill** | Agents use the user’s real logged-in browser (CLI + extension). Critical pattern for authenticated workflows without stealing the main session. |
| 4 | **Tencent/WeKnora** | Open-source LLM knowledge platform: docs → RAG + autonomous reasoning agent + self-maintaining Wiki. Strong reference for HQ knowledge / Horizon memory. (Large; study rather than full production couple.) |
| 3 | **addyosmani/agent-skills** | Production engineering skills (spec/plan/build/test/review/security…). Gold standard for how we should write and package our own skills. |
| 2 | **alibaba/open-code-review** | Hybrid deterministic + LLM line-level code review, battle-tested at Alibaba scale. Model for review agents and lighter commercial skill packs. |
| 1 | **cloudflare/security-audit-skill** | Structured 6-phase security audit skill with verification. Model for evidence-based, multi-agent safety workflows. |

## Actions taken

- Forked: BrowserSkill, agent-skills, open-code-review, security-audit-skill into `bimald986-cell/*`.
- Registered in `core/projects.yaml` as study-fork / skills-library entries.
- Linked to post-book income stream (`docs/INCOME_STREAM_POST_BOOK_SKILLS.md`) and school redesign kit.

## How to use with Claude / agents

Most of these install via paste-repo-link or `npx skills add …`. Prefer studying patterns and selective adoption into HQ policy/agent loops rather than blind full integration.

WeKnora is large and enterprise-oriented; treat as architecture reference for knowledge + agent + wiki, not a mandatory dependency.
