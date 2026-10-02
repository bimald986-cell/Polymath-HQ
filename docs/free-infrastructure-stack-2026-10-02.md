# Free infrastructure stack review — 2026-10-02

Source: user-provided video reviewed on 2026-10-02. Current free tiers were independently checked against vendor sources before recording this plan.

## Products shown

| Product | Role | Current free-tier facts | HQ decision |
|---|---|---|---|
| Cloudflare Pages | Frontend/static deployment | $0 plan; 500 builds/month; static asset requests are free/unlimited; Pages Functions share Workers Free quota | Approved option for lightweight public frontends and static dashboards |
| Neon | Serverless Postgres/backend | Free plan currently gives 100 projects; as of 2026-10-02, 1 GB Postgres storage/project, 100 CU-hours/project/month, 10 branches/project; scale-to-zero | Approved option for prototypes/new apps. Do not migrate a working production DB solely to chase free tier. |
| Clerk | Authentication/user management | Hobby $0; no card required; 50,000 monthly retained users per app; unlimited applications; limits apply to some advanced auth features | Approved option where auth is not already securely implemented. Evaluate against existing auth before adoption. |
| Resend | Transactional email | Free $0; 3,000 emails/month; 100/day; 3 domains at time of review | Approved for verification, password reset, alerts and early-stage transactional email. Add quota monitoring. |
| Cloudflare R2 | Object/file storage | Standard storage free allowance: 10 GB-month/month, 1M Class A operations/month, 10M Class B operations/month, free internet egress. Free tier does not apply to Infrequent Access storage. | Approved for media/assets/uploads when object storage is needed. Add usage guardrails. |

## Architecture rule

These are approved building blocks, not mandatory dependencies. Agents must choose the smallest stack that fits each project, preserve working infrastructure, keep providers behind adapters where practical, keep secrets out of Git, and never enable billable upgrades automatically.

## Candidate mapping

- `retail-platform`: Neon (catalog/orders/users data), Clerk (customer/admin auth), Resend (receipts/auth/alerts), R2 (product images/files), Cloudflare Pages only if frontend architecture fits.
- `RateBridge`: Neon (rates/history/user data), Clerk (accounts), Resend (alerts/auth), R2 only for exports/assets, Pages if frontend architecture fits.
- `astrolab-v6`: Resend is immediately relevant for login/reset/notifications. Neon/Clerk are alternatives only after comparing with the PostgreSQL/auth work already in place. R2 may later hold generated reports/assets.
- `mind-mythos`: R2 is highly relevant for generated media and publishing assets; Neon for production metadata/jobs; Clerk for dashboard auth; Resend for operational notifications; Pages only if compatible with the dashboard.
- `wonder-to-wisdom`: R2 is highly relevant for book/video/media assets; Neon/Clerk/Resend become relevant if a customer/creator web app is added; Pages can host static/public catalog surfaces.

## Guardrails

1. Re-check vendor pricing immediately before production activation because free tiers can change.
2. Configure budget/usage alerts wherever supported.
3. Keep credentials only in deployment secret stores/environment variables.
4. Prefer adapters so Clerk/Resend/R2/Neon can be replaced later.
5. Do not duplicate services already provided reliably by Railway or another existing provider without a migration reason.
