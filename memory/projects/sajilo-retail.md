# Sajilo Retail
Repository: bimald986-cell/retail-platform
Purpose: retail/POS platform.
Durable rule: existing tenant-scoped sale/inventory idempotency is the canonical retry mechanism; do not create a competing system.
Current gate: PostgreSQL end-to-end proof for sale, payment, one stock deduction, same-key retry, daily summary and rollback on failure.
No production-readiness claim without real verification.
