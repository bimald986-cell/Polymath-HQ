# Elevate Edge — Career Service App

Local web application for the **Elevate Edge** venture inside Polymath-HQ.

## Features

| Area | What it does |
|------|----------------|
| **Home** | Brand pitch + navigation |
| **Packages** | Edge Start / Pro / Career pricing board + intake fields |
| **CV Builder** | Structured form, Modern/Classic preview, save in browser **or to your account**, print to PDF |
| **Role Guide** | 8 starter roles with skills + sample bullets |
| **Interview** | STAR answer helper (AI when a provider is configured) |
| **Accounts** | Email + password signup/login, your CV stored on the server, delete your account |
| **Free tier** | 3 AI drafts per 30 days, then HTTP 402 with the upgrade path — the provider is never called |

## Run

```bat
cd elevate-edge
python -m pip install -r requirements.txt
set ELEVATE_DEV=1
python app.py
```

Open **http://127.0.0.1:8088**

### Port note

Do **not** use port **5060** — Chrome blocks it (`ERR_UNSAFE_PORT`, SIP). Default is **8088**.

## Configuration

| Variable | Meaning |
|---|---|
| `ELEVATE_SECRET_KEY` | **Required outside dev.** Signs the session cookie. The app refuses to start without it. |
| `ELEVATE_DEV` | `1` = local development: an ephemeral session key is generated with one loud warning, and the cookie is not marked `Secure`. Never for anything real. |
| `ELEVATE_DB_PATH` | SQLite file. Default `elevate-edge/data/elevate.db` (git-ignored, created on first run). |
| `ELEVATE_HOST` / `ELEVATE_PORT` | Bind address, default `127.0.0.1:8088`. |
| `AGENCY_LLM`, `AGENCY_LLM_BASE_URL`, `AGENCY_LLM_API_KEY`, `AGENCY_LLM_MODEL` | The model provider. With none set the AI endpoints answer 503 and say so. |

Local Ollama example:

```bat
set AGENCY_LLM=openai
set AGENCY_LLM_BASE_URL=http://127.0.0.1:11434/v1
set AGENCY_LLM_API_KEY=ollama
set AGENCY_LLM_MODEL=gemma2:2b
```

## Accounts and the free tier

- `POST /signup` — email + password (at least 10 characters). A duplicate email is a **409**
  ("already registered"); a weak password is a **400** naming the rule. Emails are lowercased
  and trimmed, so `A@B.com ` and `a@b.com` are the same account.
- `POST /login` — the session is regenerated on success. **5 failures per email per 10 minutes**
  and the next attempt is a **429**.
- `POST /logout` — clears the session.
- `GET /account` — email, plan, AI drafts used and remaining.
- `POST /api/account/delete` — needs the password again; deletes the account and its CVs.
- `GET/PUT /api/cv` — requires a session. A CV is stored per user, and every query carries
  `user_id` in its `WHERE`, so one account can never read or overwrite another's CV.

The gate: **free = 3** successful AI calls (`/api/bullets` and `/api/star` share one counter),
**pro = 200 per 30-day period**. The counter only moves on success — a failed provider call
costs nothing. At the limit the endpoint answers **402** with the limit and the upgrade path,
and the provider is not called at all. Anonymous visitors get 3 calls counted in the signed
session cookie (clearing cookies resets it; anonymous CVs are never stored server-side).

## Upgrading an account (no payment provider yet)

There is **no checkout**. Entitlement is granted by the operator:

```bash
python admin.py grant  someone@example.com pro    # 200 AI drafts per 30 days
python admin.py grant  someone@example.com free
python admin.py revoke someone@example.com        # same as grant ... free
python admin.py show   someone@example.com        # plan and usage
```

`admin.py` uses the same database as the app (`ELEVATE_DB_PATH`). Nothing here takes money,
and no page pretends to. When a checkout provider is chosen, its webhook calls
`store.grant_plan(email, plan)` — the one seam — and nothing else in the gate changes.

## Without AI

App still runs; CV Builder and Role Guide work offline.

The AI buttons are **honest about it**: with no provider configured the endpoints
answer **503** with `analysis_mode: simulation` and a message saying no AI text was
produced. There is no hidden mock that returns 200 with canned text. `GET /api/health`
reports the backend that actually answers (`live` / `simulation` / `unavailable`),
not the `AGENCY_LLM` env var — so it cannot claim "openai" while a mock replies.

## Tests

```bash
cd elevate-edge
pip install -r requirements.txt pytest
pytest -q
```

## Not built, on purpose

Payments, email verification, password reset by email (this business cannot send email),
OAuth, multi-CV tiers. Nothing here can take money today.
