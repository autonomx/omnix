# Rolling upgrade and rollback

## Upgrade

1. Back up the database: `python -m app.persistence backup <file>`.
2. Apply expand migrations: `python -m app.persistence migrate`; check
   `python -m app.persistence status`.
3. One replica at a time: stop it (it drains: `/ready` 503 `draining`, new
   requests 503 with `Retry-After`, in-flight work gets `OMNIX_DRAIN_SECONDS`),
   start it on the new revision, and wait until `/ready` reports the new
   `build_revision`.
4. Then each job worker (they stop claiming and finish or release their jobs).
5. Contract migrations run only after every process runs the new revision
   ([OPERATIONS: Rolling restarts and draining](../../OPERATIONS.md#rolling-restarts-and-draining)).

Watch during the rollout: `OmnixErrorBudgetFastBurn`, *5xx ratio*, *Chat
admission p95* and *Oldest waiting job* on the overview dashboard.

## Rollback

1. Before contract migrations: roll replicas back the same way, one at a time,
   to the previous revision. Expand migrations stay; older code ignores the
   new columns and indexes.
2. After a contract migration: older code may not run against the new schema.
   Restore the backup taken in step 1 into a new database ([Restore](restore.md))
   rather than editing the schema by hand.

## Verification

- Every `/ready` reports the intended `build_revision`; the 5xx ratio and
  latencies are back to their pre-upgrade values.
