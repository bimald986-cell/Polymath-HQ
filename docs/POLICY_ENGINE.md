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
