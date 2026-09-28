# Cross-repo improvement snapshot

Living notes for Polymath HQ products and study forks. Update when PRs land.

## Priority matrix

| Repo | Highest-leverage next step | Status |
|------|----------------------------|--------|
| **astrolab-v6** | Merge green CI (#37), adopt Sacred Studio (#38), implement design tokens/buttons | In progress on public-beta |
| **mind-mythos** | Enforce physical media before review; learning-loop JSON; keep publish locked | CI + backlog PR |
| **RateBridge** | Verify real provider fees for Kuwait→Nepal only; never rank placeholders | Trust-first |
| **Polymath-HQ** | PolicyEngine wired; Horizon PRs only; no financial auto-execution | Foundation |
| **automaton / deepseek-harness** | Study only; no production coupling | Study |
| **emilkowalski_skills** | Source of UI craft for all products | Active |
| **public-apis** | Curated allowlist already in HQ | Active |

## Shared rules

1. **President merges** — Horizon opens `horizon/*` PRs; humans merge.
2. **No invented authority** — charts, FX rankings, and media files must be real or clearly absent.
3. **Policy before power** — irreversible GitHub actions and spend stay blocked without President flag.
4. **Design craft** — Emil rules + product-specific UI_CRAFT (Sacred Studio for AstroLab; calm dashboard for M&M).

## Suggested weekly rhythm

1. Green CI on open product PRs  
2. One AstroLab public-beta improvement  
3. One Mind & Mythos production artifact toward EP001 review  
4. One RateBridge verified data point (if research available)  
5. HQ capability_scan / policy tests  
