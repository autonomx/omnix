# PostgreSQL Transaction and Schema Evolution Contract

This contract applies to every authoritative PostgreSQL repository, gateway, worker, migration command, and background operation in Omnix.

## Transaction boundary

- The normal isolation level is `READ COMMITTED`.
- Mutable aggregates use revision compare-and-swap or an equivalent guarded update.
- A stale revision is a domain conflict. The caller must reload current authority and recompute deterministic work; it must not blindly repeat only the failed SQL update.
- PostgreSQL lock timeout is bounded by `OMNIX_DATABASE_LOCK_TIMEOUT` and cannot exceed the statement timeout.
- Model calls, network calls, slow BlobStore operations, and other external side effects are prohibited inside authoritative database transactions.
- External effects are initiated after commit from a durable job or outbox record and must use an idempotency key.

## Retry contract

Only operations that are safe to re-execute through an idempotent transaction boundary may use `run_transaction`.

Retryable SQLSTATE classes are limited to:

- serialization failure (`40001`);
- deadlock detected (`40P01`);
- transient connection failures (`08xxx` selected by the runtime policy);
- database restart or temporary unavailability (`57P01`, `57P02`, `57P03`).

Retries are bounded by `OMNIX_DATABASE_TRANSACTION_MAX_ATTEMPTS` with exponential delay based on `OMNIX_DATABASE_TRANSACTION_RETRY_BASE_MS`. Constraint errors, authorization errors, validation errors, and stale aggregate revisions are not generic retryable database failures.

## Migration ownership

- One migrator owns schema changes at a time through a transaction-scoped PostgreSQL advisory lock.
- A crashed migrator releases the lock automatically when its transaction ends.
- Applied migrations are immutable and protected by checksums.
- Unknown applied migrations or checksum drift fail closed.
- Runtime startup applies known pending migrations, then requires an application-compatible schema before serving authority.

## Application/schema compatibility

The current release declares:

```text
minimum schema: 0010_complete_legacy_migration
maximum schema: 0010_complete_legacy_migration
```

An application release must refuse to start when the database schema falls outside its supported range. Future rolling or mixed-version deployments must use expand-and-contract migrations:

1. add backward-compatible schema;
2. deploy readers/writers that support both representations;
3. backfill resumably with checkpoints;
4. switch reads and writes;
5. remove old schema only after all supported application versions no longer require it.

Large index changes must use low-lock PostgreSQL techniques where available. Destructive migrations require a verified coordinated backup generation and an explicit rollback or forward-repair plan.

## Verification

Provider-free CI verifies:

- migration idempotency;
- advisory lock exclusion;
- checksum and unknown-version rejection;
- application/schema compatibility reporting;
- bounded retry classification;
- transaction-context side-effect guards;
- transaction rollback behavior.
