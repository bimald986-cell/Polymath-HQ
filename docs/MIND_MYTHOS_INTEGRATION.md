# Mind & Mythos integration

Project registry entry: [`core/projects.yaml`](../core/projects.yaml)  
GitHub repo: [bimald986-cell/mind-mythos](https://github.com/bimald986-cell/mind-mythos)

## Goal
Let the HQ dashboard and Horizon worker find Mind & Mythos (M&M), propose improvements, and push review-branch updates automatically. **Merge to `main` stays a human President decision.**

## Horizon standing task (recurring scans)
When the Horizon worker runs, use a task like:

```text
Scan registered projects, especially mind-mythos. Propose or implement highest-value review-branch updates and open President-Brief PRs. Never merge.
```

## GitHub auth for the worker
The worker needs a token that can:

- read + write `bimald986-cell/mind-mythos`
- create branches and pull requests
- **not** required to merge

Without that token, dashboard commands queue but nothing lands in M&M.

## Same database path
Dashboard and Horizon worker must share `HORIZON_DB_PATH` (same `.horizon/horizon.db`). Otherwise commands sit forever in the queue.

Default (local):

```text
intelligent-agency/.horizon/horizon.db
```

## Day-to-day use
1. Start dashboard (`start_hq_dashboard.bat`).
2. Start Horizon worker (same machine / same DB).
3. Paste a Command HQ job (examples below).
4. Watch **Activity** for the job → done.
5. Open the PR on **mind-mythos** → review → merge yourself.

### Full command (first structured pass)

```text
Inspect project Mind & Mythos at github.com/bimald986-cell/mind-mythos.

Tasks:
1. Read README.md and productions/001-why-life-feels-faster.md.
2. Compare current repo structure to the brand rules in the README (voice, runtime philosophy, learning loop, platform packaging, dashboard claim).
3. Produce the highest-value concrete improvements:
   - folder structure stubs if missing (brand/, research/, packages/, metrics/, dashboard/)
   - productions/_template.md extracted from 001
   - fix or implement the claimed dashboard/ path
   - one production-002 idea brief if useful
4. Implement approved-safe file changes on a horizon/* branch only.
5. Open a President-Brief pull request into mind-mythos (do not merge).
6. Store a short memory note under scope=mind-mythos with what changed and what still needs human decision.
```

### Shorter recurring command

```text
Inspect mind-mythos. Implement the next highest-value structural or production improvement on a horizon/* branch and open a President-Brief PR. Do not merge.
```

## Authority boundary

| Action | Allowed |
|--------|---------|
| Inspect mind-mythos | Yes |
| Create/modify files on `horizon/*` | Yes |
| Open / update PR | Yes |
| Merge to `main` | **No** (President only) |
| Push secrets / workflow security files | No |

## Honest limit (current)
Today HQ can **queue** M&M work and **advise** on it. Automatic file push + PR only happens after:

- Horizon worker is running
- GitHub credentials for `mind-mythos` exist
- a target-repo path is coded/configured to use `core/projects.yaml`

Chat alone cannot push. The durable queue + Horizon + GitHub adapter can.

## Related docs
- [HQ Dashboard](HQ_DASHBOARD.md)
- [Horizon Runtime](HORIZON_RUNTIME.md)
- [Continuous improvement workflow](../workflows/continuous-improvement/README.md)
