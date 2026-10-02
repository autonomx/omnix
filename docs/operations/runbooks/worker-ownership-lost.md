# Worker ownership lost

A worker or scheduler process lost its PostgreSQL advisory lock or its
execution lease, so background work (schedulers, recovery, outbox delivery)
stopped on it.

## Symptoms

- `/ready` on the worker gateway returns 503; `/api/diagnostics` shows
  `background.owns_lock: false` or an unhealthy execution owner.
- `OmnixOutboxLagging` or `OmnixScheduledTaskFailing` fires: nothing is
  running the outbox relay or scheduled tasks.
- Chat turns owned by the lost process end with one recovery event.

## Dashboards and metrics

- Omnix overview: *Outbox lag*, *Scheduled task failures*.
- `omnix_outbox_oldest_unpublished_age_seconds` keeps growing;
  `omnix_scheduler_task_runs_total` stops increasing everywhere.

## Diagnosis

1. On each worker gateway, read `/api/diagnostics`: `background`,
   `chat.execution_owner_healthy`, `postgresql.connectivity`.
2. Check the logs for transition lines from the owner and scheduler
   (component, role, transition, error class) around the loss.
3. Confirm PostgreSQL is reachable from the host (`python -m app.persistence health`).
   A database outage causes this too: follow [PostgreSQL outage](postgresql-outage.md).

## Remediation

- A revoked lock or expired owner is never revived in place. Restart the
  affected worker process; it starts with a fresh identity and takes the lock
  if no other worker holds it ([OPERATIONS: Rolling restarts](../../OPERATIONS.md#rolling-restarts-and-draining)).
- If another worker already took ownership, no action is needed beyond
  restarting the old one to clear its unready state.

## Verification

- `/ready` returns 200 on the restarted worker; exactly one process reports
  `background.owns_lock: true`.
- `omnix_outbox_oldest_unpublished_age_seconds` falls below 1 s and scheduled
  task runs increase again.
