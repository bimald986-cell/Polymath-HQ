# HQ skills

## Design engineering (from fork)

Source fork: [bimald986-cell/emilkowalski_skills](https://github.com/bimald986-cell/emilkowalski_skills)

Preferred fuller upstream install:

```bash
npx skills@latest add emilkowalski/skills
```

### Skills available in the fork

| Skill | Use when |
|-------|----------|
| `emil-design-eng` | Building or reviewing UI polish, components, motion decisions |
| `review-animations` | Strict pass/fail review of animation code |
| `animation-vocabulary` | Naming a motion effect precisely for prompts |
| `apple-design` | Fluid, restrained interface motion patterns |

### Apply to

- `elevate-edge/` career web MVP
- `intelligent-agency` dashboard / webapp
- `mind-mythos` dashboard (subtle motion only; brand is audio-first)

### Rules of thumb (from the skills — summary)

- Prefer **ease-out** for enter animations; avoid **ease-in** for UI chrome
- UI motion usually **under 300ms**
- Do **not** animate actions users trigger hundreds of times/day
- Never start from `scale(0)`; use ~`0.95` + opacity
- Review with a Before / After / Why table when auditing code
