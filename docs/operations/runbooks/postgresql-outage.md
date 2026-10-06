# PostgreSQL outage

PostgreSQL is the authority for sessions, jobs, settings and agent runs. Omnix
does not fall back to another store: without it, processes go unready.

## Symptoms

- `/ready` returns 503 on every process; requests fail with 503.
- `OmnixJobSnapshotFailing` (the gateway cannot read the queue) and
  `OmnixErrorBudgetFastBurn`.
- Logs show classified PostgreSQL errors (error class only, no URL).

## Dashboards and metrics

- `omnix_jobs_snapshot_up` is 0; `omnix_db_pool_request_errors_total` rises;
  `omnix_db_pool_requests_waiting` stays above 0.

## Diagnosis

1. `python -m app.persistence health` from an Omnix host.
2. Check the PostgreSQL server itself: process up, disk space, `max_connections`
   reached (`SELECT count(*) FROM pg_stat_activity`), replication or failover.
3. Connection exhaustion: compare the startup `database_connection_budget`
   log line and `/ready`'s budget with `max_connections`
   ([OPERATIONS: Database connections](../../OPERATIONS.md#database-connections)).
4. Long transactions holding locks or events back:
   `SELECT pid, state, xact_start, query FROM pg_stat_activity WHERE backend_xid IS NOT NULL ORDER BY xact_start LIMIT 5;`

## Remediation

- Restore the database service (restart, free disk, fail over). Do not point
  Omnix at another database to get going: data written there is lost.
- Then restart the Omnix processes so each starts with a fresh execution
  identity ([OPERATIONS: Production worker/API operations](../../OPERATIONS.md#production-workerapi-operations)).
- Connection exhaustion: lower `OMNIX_DATABASE_POOL_MAX` or the process
  count, or raise `max_connections`.

## Verification

- `python -m app.persistence verify` passes (healthy, no migration drift).
- `/ready` returns 200; `omnix_jobs_snapshot_up` is 1; queued jobs drain.
