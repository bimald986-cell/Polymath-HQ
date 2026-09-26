# Polymath HQ President Console

The dashboard is a local control surface for the human President. It shows Horizon queue state, heartbeat, recent work and memory, and lets the President submit commands directly into the durable Runtime v2 queue.

## Windows quick start
1. Clone or pull `Polymath-HQ` to the computer.
2. Open `Polymath-HQ/intelligent-agency`.
3. Double-click `start_hq_dashboard.bat`.
4. Browser opens `http://127.0.0.1:8765`.

The default bind address is loopback only. This is intentional: the console has no login layer in v1 and must not be exposed to the public internet.

## Command path
`President Console -> SQLite durable queue -> Horizon worker -> candidate memory / review work -> President-Brief PR -> human merge decision`

The dashboard does not bypass Horizon's existing GitHub guard and does not grant merge authority.

## Important: dashboard versus worker
The dashboard submits commands even when the worker is offline. They remain queued in `.horizon/horizon.db`. To process commands automatically, an active Horizon worker must use the same database path. The always-on deployment should mount this database on persistent storage or use a future shared database service.

## Configuration
- `HQ_DASHBOARD_HOST` default `127.0.0.1`
- `HQ_DASHBOARD_PORT` default `8765`
- `HORIZON_DB_PATH` default `intelligent-agency/.horizon/horizon.db`

## Security before remote access
Before binding to `0.0.0.0` or putting this console on Railway/the internet, add authentication, CSRF protection, HTTPS/reverse proxy controls, session expiry, command authorization and rate limits. Until then, keep it local-only.
