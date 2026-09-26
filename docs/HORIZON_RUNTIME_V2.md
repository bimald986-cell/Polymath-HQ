# Horizon Runtime v2

Runtime v2 adds the durable core required for unattended work.

## Implemented
- SQLite/WAL durable work queue with priorities, leases, retries and recovery of expired work.
- Scoped candidate memory with provenance, confidence and status.
- Worker heartbeat records.
- Daily budget-unit enforcement.
- Evidence/provenance records with an explicit promotion rule.
- Guarded GitHub change-set contract: only `horizon/*` branches, no protected branches, workflow/security controls or secret material.
- Standard President Brief generation.
- Durable worker class that claims work, calls Horizon, stores candidate results and survives transient work failures.

## Deliberate boundaries
Runtime v2 does not grant merge authority. It also does not contain GitHub credentials, LLM secrets or browser credentials. Those belong in the deployment environment, never the repository.

The GitHub execution adapter must translate a validated `ReviewChangeSet` into branch/file/PR API calls using a narrowly scoped credential. The adapter must not expose merge, repository administration, secret management or protected-branch writes.

## Deployment requirements
1. persistent volume for `.horizon/horizon.db`
2. configured LLM backend
3. scoped GitHub App/token for contents + pull requests on review branches
4. health/restart policy
5. provider budget values
6. optional research/browser adapters with provenance

## End-to-end acceptance test
1. queue an improvement task
2. worker claims it and writes heartbeat
3. Horizon researches/reasons using approved adapters
4. candidate knowledge is stored with provenance
5. validated implementation is written to a new `horizon/*` branch
6. tests run
7. President-Brief PR is opened
8. worker stops at the merge gate
9. President reviews and merges/rejects
