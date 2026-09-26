# Horizon Autonomous Runtime

## Goal
Keep Horizon working without requiring a human to manually start every improvement scan, while preserving the President's exclusive merge decision.

## Two execution modes

### 1. GitHub scheduled cycle
`.github/workflows/horizon-scheduled.yml` wakes Horizon every four hours and can also be started manually. Each run tests HQ first, performs one bounded improvement cycle, and stores the audit output as a workflow artifact.

This mode is intentionally read-only at the GitHub Actions permission layer in v1. It can inspect and recommend safely. Branch/PR mutation is delegated to a separately authenticated worker when configured.

### 2. Persistent worker
`python intelligent-agency/horizon_runtime.py` runs continuously on a machine/container. It executes a cycle, sleeps, and retries failures with bounded exponential backoff.

Environment variables:
- `HORIZON_INTERVAL_SECONDS` default `3600`
- `HORIZON_STATE_DIR` default `.horizon`
- `HORIZON_TASK` standing cycle instruction
- existing `AGENCY_LLM*` variables configure the model backend

## Runtime guarantees
- minimum cycle interval: 60 seconds
- append-only JSONL audit trail
- UTC timestamps
- transient failures do not kill the daemon
- bounded exponential retry backoff
- tests execute before scheduled GitHub cycles
- scheduled runs use concurrency control so cycles do not overlap
- Horizon retains `merge_pull_request: false`

## Important boundary
Scheduling makes Horizon wake up on its own. It does not magically provide web/GitHub credentials, model credits, or a permanently running computer. Those are runtime dependencies and must be connected explicitly.

For unattended implementation, deploy the persistent worker on an always-on service with a narrowly scoped GitHub credential and configured LLM/research adapters. The worker may create review branches and PRs, but `main` promotion remains a human action.

## Recommended next layer
1. durable work queue and SQLite/Postgres state
2. GitHub adapter that creates `horizon/*` branches and President-Brief PRs
3. research/browser adapter with source provenance
4. memory/skills/Wiki/CodeGraph persistence
5. heartbeat and stale-run detection
6. budget/rate limits and per-tool permission policy
7. notifications when a President decision is required
