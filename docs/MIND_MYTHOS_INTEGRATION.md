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
The transport now exists in code and is covered by tests, but nothing runs it yet:
- **GitHub adapter: built.** `intelligent-agency/src/agency/github_client.py` creates branches,
  writes files and opens pull requests over `urllib.request`; the token comes from `GITHUB_TOKEN`.
  It cannot merge (`merge_pull_request` always raises), cannot write to
  `main`/`master`/`production`/`release`, and refuses `.github/workflows/`, `.git/`, `.env`, secret
  and credential paths. Missing credentials fail loudly with a non-zero exit.
- **Worker: runnable.** `python -m agency.horizon_worker_main` (or `run_horizon_worker.py`) consumes
  the same queue the dashboard writes to, resolved from the same `HORIZON_DB_PATH`.
  `github_review_changeset` items are published as a review branch + pull request; all other items
  stay advisory.
- **Still required before it runs unattended:** a `GITHUB_TOKEN` with write scope, `GITHUB_REPO`, a
  live LLM provider (`AGENCY_LLM`), and a project-to-repo mapping - `core/projects.yaml` is still read
  by no runtime code, so a target repository must be passed explicitly.
- **Merge remains a human decision**, enforced in code: no path on this transport merges.
Chat alone still cannot push. The durable queue + worker + GitHub adapter now can, when configured.

## Related docs
- [HQ Dashboard](HQ_DASHBOARD.md)
- [Horizon Runtime](HORIZON_RUNTIME.md)
- [Continuous improvement workflow](../workflows/continuous-improvement/README.md)
