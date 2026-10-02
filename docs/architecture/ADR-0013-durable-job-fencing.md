# ADR 0013: Durable execution fencing

Status: accepted.

Keep the existing PostgreSQL job state machine, lease/attempt tokens, owner identities and cancellation contracts. Every finalization validates the current owner and fencing token. A later claim invalidates an earlier worker's completion, including writes made inside the same transcript transaction.

Expired cancel-requested jobs end canceled. Abandoned chat generation is finalized once under durable owner checks, with no duplicate assistant output; it is not silently regenerated. New process identities cannot revive an expired old owner. Tests exercise racing admission, stale attempts, killed processes, cancellation and rollback. No new broker or parallel execution framework is introduced.

Every worker mutation carries the worker identity and lease token into the mutation SQL itself. Progress, input and stage updates, log appends, heartbeat renewal, completion, failure, and cancel finalization therefore serialize on the job row and reject an expired or superseded attempt. The durable feature worker checks singleton runtime authority before dispatch but does not perform a separate database lease read before each write.

Job logs are append-only rows in `omnix_job_logs`, with per-job sequence ordering and a workspace-qualified foreign key. The expand migration copies existing compatibility logs before removing `compat_contract.logs` from job metadata. The compatibility API exposes the latest 500 rows while retaining the full log history in PostgreSQL. Concurrent cancellation and logging serialize through the fenced job-row update, so both the cancellation request and a still-owned worker log survive.

Handler retry backoff is snapshotted onto a submitted job alongside its existing `max_attempts` value. Both handler failures and expired leases use that schedule, with a minimum one-second delay; an expired final attempt creates a dead letter. Queue claims use `priority + min(100, floor(age_seconds / OMNIX_JOB_PRIORITY_AGING_SECONDS))`; the interval defaults to 60 seconds and is validated between 1 and 86,400 seconds. Moving expired-lease sweeping to the five-second scheduler remains WP-6.3 work.
