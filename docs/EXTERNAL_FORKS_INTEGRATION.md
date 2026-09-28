# External forks — what HQ adopts

Horizon registered four study/capability forks under `bimald986-cell` on 2026-09-28.
This doc is the integration contract: **what to take**, **what not to take**, and **where it lands**.

## Fork inventory

| Local fork | Upstream | HQ use |
|------------|----------|--------|
| [automaton](https://github.com/bimald986-cell/automaton) | Conway-Research/automaton | Patterns: agent loop, policy engine, heartbeat, treasury *limits as design*, constitution hierarchy |
| [deepseek-harness](https://github.com/bimald986-cell/deepseek-harness) | deepseek-ai/deepseek-harness | Patterns: plugin architecture, profiles, sandbox isolation; experimental runtime only |
| [emilkowalski_skills](https://github.com/bimald986-cell/emilkowalski_skills) | attentiondotnet / emilkowalski | **Adopt**: design & animation skills for Elevate Edge, HQ dashboards, **AstroLab UI** |
| [public-apis](https://github.com/bimald986-cell/public-apis) | public-apis/public-apis | **Reference**: curated tool ideas; slim allowlist in `core/public_api_allowlist.yaml` |

## Adoption rules

1. **License** — All four are MIT. Attribution in THIRD_PARTY or docs when substantial text/code is copied.
2. **No Conway coupling** — Automaton may depend on Conway Cloud, wallets, USDC. HQ must not require those for core routing.
3. **No silent production harness** — DeepSeek Harness is developer preview; run only in disposable environments; read `SAFETY.md`.
4. **Skills yes, full runtime optional** — Prefer skill files and small Python modules inside `intelligent-agency` over vendoring entire TS monorepos.
5. **Public APIs** — Do not call random catalog endpoints. Promote APIs into `core/public_api_allowlist.yaml` with auth, rate limits, and owner review.
6. **Merge boundary** — Horizon implements on `horizon/*` branches; President merges.

## Implementation status (2026-09-28)

| Priority | Item | Status |
|----------|------|--------|
| P0 | Design skills (Elevate Edge, HQ UI, AstroLab) | **In progress** — docs + registry; UI_CRAFT on AstroLab PR |
| P1 | Policy skeleton | **Done** — `intelligent-agency/src/agency/policy.py` + tests |
| P2 | Capability scan script | **Done** — `intelligent-agency/scripts/capability_scan.py` |
| P3 | Plugin-shaped tools | Planned |
| P4 | Public API allowlist | **Done** — `core/public_api_allowlist.yaml` (candidates only) |

## Mapping to existing HQ layout

```
Polymath-HQ/
  core/projects.yaml
  core/capability_registry.yaml
  core/public_api_allowlist.yaml
  docs/EXTERNAL_FORKS_INTEGRATION.md
  docs/skills/
  intelligent-agency/src/agency/policy.py
  intelligent-agency/scripts/capability_scan.py
  elevate-edge/
```

## Explicit non-goals

- Running self-replicating paid automatons in production HQ
- Merging DeepSeek Harness as the default runtime without isolation + President sign-off
- Rehosting the entire public-apis README as a product surface
