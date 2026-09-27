# ADR 0013: Durable execution fencing

Status: accepted.

Keep the existing PostgreSQL job state machine, lease/attempt tokens, owner identities and cancellation contracts. Every finalization validates the current owner and fencing token. A later claim invalidates an earlier worker's completion, including writes made inside the same transcript transaction.

Expired cancel-requested jobs end canceled. Abandoned chat generation is finalized once under durable owner checks, with no duplicate assistant output; it is not silently regenerated. New process identities cannot revive an expired old owner. Tests exercise racing admission, stale attempts, killed processes, cancellation and rollback. No new broker or parallel execution framework is introduced.
