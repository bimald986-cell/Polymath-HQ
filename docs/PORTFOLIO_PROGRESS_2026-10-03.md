# HQ Portfolio Progress Pass — 2026-10-03

## Purpose
Run the HQ director/agent model across the active product portfolio, identify the next smallest useful increment per repo, then execute those increments through repo-local work.

## Active product portfolio
- Polymath-HQ: make portfolio orchestration explicit and auditable.
- retail-platform (Sajilo Retail): next increment after POS core is reliability/idempotency + end-to-end sale test.
- mind-mythos: harden publishing pipeline, especially Instagram-safe media validation/re-encode after repeated upload failures.
- astrolab-v6: continue modular extraction from report.html while preserving calculations/output; add regression coverage around extracted modules.
- wonder-to-wisdom: add publishing QA gate for character consistency, story/book packaging, and media manifests.
- RateBridge: strengthen live-rate provenance/staleness handling and corridor verification.
- 90-Days-of-AI: rename learner-facing framing away from “90 days” and make lessons source-linked and progress-driven.
- open-educators: define the next teacher-side MVP slice and connect it to Wonder to Wisdom without duplicating curriculum truth.

## Agent routing
Each product increment should pass through: Research/Gap analysis → Product scope → Builder/Engineer → QA/Security where applicable → evidence in commit/tests/docs.

## Governance
HQ can identify and implement bounded reversible increments. Publishing, production deployment, financial actions, destructive operations, and claims requiring external approval remain explicit human decisions.
