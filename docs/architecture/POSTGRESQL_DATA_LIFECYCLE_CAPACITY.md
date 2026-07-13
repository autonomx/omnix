# PostgreSQL Data Lifecycle and Capacity Controls

Centralized authority must not create unbounded append-only growth. Omnix stores retention policy in PostgreSQL and performs bounded, auditable cleanup runs.

## Default policy

- published outbox events: 30 days after publication;
- terminal consumer inbox records: 30 days;
- resolved dead letters: 90 days;
- job events: 90 days, subject to job audit requirements;
- audit events: 365 days;
- runtime failure evidence: 30 days.

Cleanup is terminal-state aware. Pending, claimed, retrying, active, unresolved, or otherwise recovery-relevant rows are not removed. Published outbox events remain protected while consumer inbox references exist. Cleanup runs are batch bounded and record before/after capacity, deleted counts, status, and bounded errors.

## Capacity policy

The initial database policy limits outbox payloads to 1 MiB, records an 8 MiB general JSONB target, warns at 80 percent disk use, hard-stops unsafe growth at 95 percent, and defaults cleanup to batches of 1,000 rows. The database enforces the outbox payload ceiling directly.

Capacity diagnostics include database bytes, counts for append-heavy tables, largest observed outbox payload, and current policy. Vacuum, analyze, index-bloat review, and partitioning are operational decisions based on measured growth; partitioning is not introduced solely for architectural symmetry.

Backup retention, idempotency windows, deterministic replay requirements, and audit obligations take precedence over deletion. Any policy reduction must prove that required recovery and deduplication records remain available.