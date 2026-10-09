# HQ Evidence Verification Policy

Every HQ agent must distinguish documented information from implementation and verification evidence.

DOCUMENTED:
A statement appears in project memory, README, plans, or other documentation.
This does not establish that the feature exists or works.

IMPLEMENTED:
Relevant code, configuration, or an artifact has been inspected.
This does not establish that the feature passes tests or works in production.

VERIFIED:
A specific claim is supported by relevant test results, CI checks, PR/merge records, deployment checks, or other direct evidence.

Rules:
1. Never claim verification is complete solely from project memory.
2. Never infer that a PR merged, CI passed, or deployment succeeded from plans.
3. State what was checked, where, and when.
4. Identify missing evidence explicitly.
5. Do not describe historical test results as current verification.
6. If evidence is unavailable, use "Not verified in this session."
7. Never invent test counts, commit hashes, deployments, or release status.
8. Separate verified facts from recommendations and proposed next steps.
9. Preserve deterministic source-of-truth boundaries in specialist projects.
10. Do not treat an agent's own assertion as independent verification.

A project is not release-ready until its required verification gates have supporting evidence.
