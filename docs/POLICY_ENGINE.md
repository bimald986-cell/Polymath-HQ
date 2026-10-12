# PolicyEngine — what it is and how HQ uses it

## Plain English

**PolicyEngine** is a small gatekeeper inside Intelligent Agency. Before Horizon (or a worker) does something sensitive, the code asks:

1. What **risk** is this tool? (`read` → `write_local` → `network` → `irreversible`)
2. If it is **irreversible** (merge, push to main, spend money, shell), is there an explicit **President authorization** flag?
3. If it is **network**, is the target on an optional allowlist?
4. Log the decision for audit.

It does **not** replace you. It blocks the runtime from doing dangerous things on its own.

## Where it is wired

| Location | What is checked |
|----------|-----------------|
| `github_worker.GitHubGuard.validate` | Review changesets; protected branch push |
| `github_worker.GitHubGuard.deny_merge` | Explicit merge attempts |
| `advisor.PresidentAdvisor.can` / `require_action` | Authority flag **and** policy tool risk |
| `worker.DurableHorizonWorker` | `enqueue_work`, `memory_remember` |

## Example

```python
from agency.policy import default_engine
from agency.github_worker import GitHubGuard, ReviewChangeSet

eng = default_engine()

# OK — horizon branch + review changeset
GitHubGuard.validate(
    ReviewChangeSet("Improve X", "horizon/improve-x", "summary"),
    policy=eng,
)

# Blocked — merge without President
try:
    GitHubGuard.deny_merge(policy=eng)
except PermissionError:
    print("blocked as designed")
```

## What you still decide

- Merging PRs on GitHub
- Promoting allowlist candidates in `core/public_api_allowlist.yaml`
- Any real money, credentials, or production deploy

## Tests

```bash
cd intelligent-agency
pytest -q tests/test_policy.py tests/test_policy_wiring.py
```

## Where the audit trail lives (updated 2026-10-11)
Every engine writes each decision to a `PolicyAuditSink` (`src/agency/policy.py`).
`default_engine()` hands every caller the **same process-wide sink**, so a decision
survives the call that produced it. Previously `default_engine()` built a fresh
engine per call, so the decision was discarded the moment it was made - which is why
nothing in HQ could show what its governance had actually decided.

The worker makes that trail durable: `horizon_worker_main.build_worker` sets
`HORIZON_POLICY_AUDIT_PATH` to `<queue dir>/policy_audit.jsonl` unless you point it
elsewhere, and the sink appends one JSON object per line. That file is the greppable
record of what governance allowed or refused, and it outlives the process:

```bash
grep github_review_changeset intelligent-agency/.horizon/policy_audit.jsonl
```

## The worker refuses to run on mock (updated 2026-10-11)
`python -m agency.horizon_worker_main` now **requires a live LLM provider by
default** and exits non-zero with an explanatory message when `AGENCY_LLM` is unset
or `mock`. This closes a real gap: an unattended cycle could previously emit canned
mock text that looked like reasoning.

- Development only: pass `--allow-mock-llm`. The worker prints a loud WARNING that
  the run is emitting canned text, then proceeds. Use it for local runs, never for an
  unattended cycle.
- `--require-live-llm` is kept as a deprecated no-op so existing scripts do not break.

Related, in `src/agency/llm.py`: `get_backend()` no longer degrades silently.
`AGENCY_LLM=openai` without `AGENCY_LLM_API_KEY`, and an unrecognised `AGENCY_LLM`
value, both raise `LLMConfigError` instead of answering with mock. `AGENCY_LLM=router`
refuses when no real `AGENCY_PRIMARY_*` / `AGENCY_SECONDARY_*` provider is complete -
local Ollama is appended only when `AGENCY_ALLOW_LOCAL_OLLAMA` opts into it, so a
router can no longer *look* live while running on a local guess.
