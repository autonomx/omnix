# Query pass at benchmark volumes (WP-7.6), 2026-10-02

Revision `fcd34e774`, Python 3.11.4, Windows-10-10.0.26200-SP0; disposable PostgreSQL
(pgserver) on the same machine. JSON: `query-pass-2026-10-02.json`.

## Data

Seeded with `scripts/seed_benchmark_data.py` (roadmap volumes) into the local owner workspace:
100,000 assets; 100,000 jobs with 300,000 job events; 10,000 chat sessions with 1,000,000 messages;
20 agent runs with 50,000 events; 5 trading strategies with 1,000,000 strategy events. RPG campaigns
were not seeded: RPG is being retired.

## Method

`scripts/benchmark_list_endpoints.py` composes the production app against the seeded database (no
background workers) and requests each list route 30 times after one warm-up request, over an
in-process ASGI transport. Times include routing, the queries, model validation and JSON encoding.

`pg_stat_statements` is not available in this PostgreSQL build, so instead of ranking statements by
total time, each route's queries were checked with `EXPLAIN (ANALYZE, BUFFERS)` where its time grew
with the data.

## Results (ms)

| Route | p50 before | p95 before | p50 after | p95 after |
|---|---|---|---|---|
| `/api/assets?limit=50` | 45.2 | 50.7 | 13.2 | 17.0 |
| `/api/jobs?limit=100` | 6.0 | 7.7 | 6.2 | 9.0 |
| `/api/jobs?limit=100&status=completed` | 5.8 | 6.5 | 7.2 | 9.1 |
| `/api/chat/sessions?limit=100` | 3.6 | 5.6 | 4.0 | 5.2 |
| `/api/chat/sessions/chat:bench-5333` | 3.5 | 3.9 | 3.9 | 5.8 |
| `/api/agent-runs/agent-run:bench-1/events?limit=500` | 4.9 | 5.8 | 5.3 | 7.1 |
| `/api/trading/strategies` | 2.6 | 3.0 | 2.6 | 3.9 |
| `/api/trading/strategies/bench-strategy-1/events` | 4.7 | 6.2 | 5.6 | 6.9 |

Budget: p95 < 100 ms. Every route was already within it at these volumes.

## Finding

The unfiltered asset list (newest first) was the only route whose time grew with volume (19 ms at
1,000 assets, 45 ms at 100,000). The only index on `omnix_assets` with `created_at` leads with
`asset_type`, so a list across all types ran a parallel sequential scan of the workspace's assets
and a top-N sort: 32 ms, 3,327 buffers. Migration `0114_assets_recent_index` adds a partial index on
`(workspace_id, created_at DESC, id DESC) WHERE lifecycle_status <> 'deleted'`: the query became an
index-only scan of 51 entries, 0.15 ms and 40 buffers.

The job, chat, agent-event and trading-event lists were already served by indexes (WP-5.5, WP-5.7,
WP-7.4) and stayed flat between 1% and 100% of the volumes.
