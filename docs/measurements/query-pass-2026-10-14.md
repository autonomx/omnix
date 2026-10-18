# Query pass with RPG campaigns (WP-7.6), 2026-10-14

Revision `b94776302` plus the change below, Python 3.11.12, Windows-10-10.0.26200-SP0;
disposable PostgreSQL 17.10 (Docker) on the same machine. JSON: `query-pass-2026-10-14.json`
(after the change). It completes the [2026-10-02 pass](query-pass-2026-10-02.md), which left
RPG campaigns out.

## Data

`scripts/seed_benchmark_data.py` at the roadmap volumes, now including 1,000 RPG campaigns
(900 active, 100 archived). Each campaign's state is a saved-game document of about 100 KB
(manifest, world and scene environment, 20 regions, a transcript); PostgreSQL stores it
compressed in the row (about 1.9 KB). The other volumes are those of the 2026-10-02 pass.

## Method

As in the 2026-10-02 pass: `scripts/benchmark_list_endpoints.py` composes the production app
(sign-in off: `OMNIX_AUTH_MODE=disabled`) and requests each route 30 times after a warm-up,
over an in-process ASGI transport. The RPG routes are the session list the RPG workspace opens
with (`GET /api/rpg/sessions`, default limit 100) and one session.

## Results (ms)

| Route | p50 before | p95 before | p50 after | p95 after |
|---|---|---|---|---|
| `/api/assets?limit=50` | 15.9 | 17.6 | 12.6 | 14.5 |
| `/api/jobs?limit=100` | 9.4 | 10.4 | 8.4 | 10.4 |
| `/api/jobs?limit=100&status=completed` | 9.0 | 9.7 | 8.5 | 9.9 |
| `/api/chat/sessions?limit=100` | 5.5 | 6.0 | 5.1 | 5.7 |
| `/api/chat/sessions/chat:bench-5333` | 6.4 | 7.1 | 5.8 | 6.7 |
| `/api/agent-runs/agent-run:bench-10/events?limit=500` | 7.6 | 8.3 | 6.3 | 8.0 |
| `/api/trading/strategies` | 4.1 | 4.9 | 4.2 | 4.5 |
| `/api/trading/strategies/bench-strategy-1/events` | 8.2 | 9.4 | 7.5 | 8.4 |
| `/api/rpg/sessions?limit=100` | **660.1** | **850.8** | 49.8 | 53.8 |
| `/api/rpg/sessions/rpg:bench-1` | 9.1 | 10.6 | 9.7 | 10.6 |

Budget: p95 < 100 ms. Only the RPG session list exceeded it; every route is within it after.

## Finding

The session list read every campaign, active and archived, with its whole state, projected each
one to a list row in Python and only then applied the limit: 1,000 states of 100 KB fetched,
transferred and parsed for a page of 100.

`PostgresRpgRepository.list_campaign_summary_sources` now reads one page (active first, then
archived, each newest first, by the existing `(workspace_id, status, updated_at)` index) and
builds in SQL only what a list row uses: the manifest, the world and region environments, the
scene's environment context and the opening location keys. Python projects that document with the
same `session_list_summary` as before; a PostgreSQL test checks that the rows equal those the full
states give, for saved games and for malformed states.

A first version applied a JSON path operator to the stored column for each field; that took
100 ms for the page, slower than reading the full rows (62 ms), because every operator
decompressed the whole document again. Decompressing each document once, inside the limited
subquery (`state_jsonb || '{}'` returns it in memory), brought the query to 31 ms.

`POST /api/rpg/session/list` (the compatibility route) still returns full sessions; the web client
calls it only when `GET /api/rpg/sessions` answers 404.
