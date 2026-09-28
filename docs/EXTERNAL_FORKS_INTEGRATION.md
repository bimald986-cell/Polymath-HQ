# External forks — what HQ adopts

Horizon registered four study/capability forks under `bimald986-cell` on 2026-09-28.
This doc is the integration contract: **what to take**, **what not to take**, and **where it lands**.

## Fork inventory

| Local fork | Upstream | HQ use |
|------------|----------|--------|
| [automaton](https://github.com/bimald986-cell/automaton) | Conway-Research/automaton | Patterns: agent loop, policy engine, heartbeat, treasury *limits as design*, constitution hierarchy |
| [deepseek-harness](https://github.com/bimald986-cell/deepseek-harness) | deepseek-ai/deepseek-harness | Patterns: plugin architecture, profiles, sandbox isolation; experimental runtime only |
| [emilkowalski_skills](https://github.com/bimald986-cell/emilkowalski_skills) | attentiondotnet / emilkowalski | **Adopt**: design & animation skills for Elevate Edge and dashboards |
| [public-apis](https://github.com/bimald986-cell/public-apis) | public-apis/public-apis | **Reference**: curated tool ideas; maintain a slim allowlist in HQ |

## Adoption rules

1. **License** — All four are MIT. Attribution in THIRD_PARTY or docs when substantial text/code is copied.
2. **No Conway coupling** — Automaton may depend on Conway Cloud, wallets, USDC. HQ must not require those for core routing.
3. **No silent production harness** — DeepSeek Harness is developer preview; run only in disposable environments; read `SAFETY.md`.
4. **Skills yes, full runtime optional** — Prefer skill files and small Python modules inside `intelligent-agency` over vendoring entire TS monorepos.
5. **Public APIs** — Do not call random catalog endpoints. Promote APIs into an allowlist with auth, rate limits, and owner review.
6. **Merge boundary** — Horizon implements on `horizon/*` branches; President merges.

## Concrete next implementations (priority)

### P0 — Design skills (low risk, high UI payoff)
- Point Elevate Edge / web UIs at `emilkowalski_skills` (or install upstream `npx skills add emilkowalski/skills`).
- Use **review-animations** checklist before shipping motion on career MVP.

### P1 — Policy skeleton in intelligent-agency
Inspired by automaton (reimplemented, not copied):
- Tool risk levels: `read` / `write_local` / `network` / `irreversible`
- Block irreversible actions without President-level flag
- Log every tool invocation with provenance (already partial in agency)

### P2 — Heartbeat / scheduled scan for Horizon
Inspired by automaton heartbeat:
- Scheduled "scan capability registry vs forks" job (docs + optional script)
- Does not auto-merge; only opens briefs

### P3 — Plugin-shaped tools (DSH ideas)
- Optional tool plugins under `intelligent-agency/src/agency/tools/` with a common interface
- Start with: local file read, GitHub worker (exists), allowlisted HTTP GET

### P4 — Curated public API allowlist
Create `core/public_api_allowlist.yaml` with a handful of endpoints useful to RateBridge / research (FX, weather, geocoding) — populated later from the public-apis fork after review.

## Mapping to existing HQ layout

```
Polymath-HQ/
  core/projects.yaml              ← forks registered
  core/capability_registry.yaml ← inspirations updated
  docs/EXTERNAL_FORKS_INTEGRATION.md  ← this file
  docs/skills/                    ← design skill pointers
  intelligent-agency/             ← future policy + tools plugins
  elevate-edge/                   ← UI craft from design skills
```

## Explicit non-goals

- Running self-replicating paid automatons in production HQ
- Merging DeepSeek Harness as the default runtime without isolation + President sign-off
- Rehosting the entire public-apis README as a product surface
