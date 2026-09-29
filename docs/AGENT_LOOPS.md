# Agent loops in Polymath HQ

## Pattern

```
for step in 1..max_steps:
    plan next tool
    policy.check(tool)   # hard gate
    execute / observe
    if terminal → stop
stop if max_steps hit
```

Implemented in `intelligent-agency/src/agency/agent_loop.py` as `run_agent_loop`.

## Rules

1. **Cap iterations** — default `max_steps=8`.
2. **Policy before side effects** — irreversible tools need President authorization.
3. **Terminal is explicit** — step returns `terminal: True`, not vibes.
4. **No unbounded self-modification** — loops improve *task outcomes*, not rewrite HQ without a human PR.

## Related

- `PolicyEngine` — risk classification + audit log
- `HorizonRuntime` — scheduled cycles with backoff (outer loop)
- Mind & Mythos converge gate — verified media before owner review
