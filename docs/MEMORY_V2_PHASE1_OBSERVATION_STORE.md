# Omnix Memory v2 Phase 1 — Observation Store Contract

Status: **Phase 1 implementation contract**  
Depends on: `docs/MEMORY_V2_ARCHITECTURE.md`, `docs/MEMORY_V2_CONTRACTS.md`

## Authority-sequence allocation invariant

`authority_sequence` allocation is database-enforced, never application-enforced.
Concurrent writers must not read the same prior watermark and independently mint the
same or out-of-order authority sequence.

The indivisible append transaction is:

```text
BEGIN
  lock/advance authority stream
        ↓
  resolve idempotency key if already committed
        ↓
  allocate next authority_sequence in the database
        ↓
  insert observation (or return the committed idempotent observation)
        ↓
  advance observation watermark to the committed sequence
COMMIT
```

Required consequences:

- sequence uniqueness is enforced by database constraints;
- allocation is serialized by the database for one authority stream;
- application retries cannot consume a second durable observation for the same
  idempotency key;
- an idempotent retry returns the originally committed observation and sequence;
- a failed transaction cannot advance the durable observation watermark;
- the durable observation watermark cannot exceed the maximum committed sequence;
- gaps caused by rolled-back provisional sequence allocation are acceptable only if the
  selected database mechanism can prove monotonic ordering and watermark correctness;
  implementations should prefer gap-free per-stream allocation when practical;
- sequence ordering is an authority property and cannot depend on process-local locks,
  in-memory counters, wall-clock time, or UUID ordering.

## Authority stream identity

The initial stream key is the `MemorySpaceKey` (`principal_id`, `owner_type`, `owner_id`).
If a later design introduces a broader global event stream, that is an explicit contract
revision; Phase 1 must not silently change stream semantics.

## Required database constraints

At minimum, persistence must enforce:

```text
UNIQUE(space_key, authority_sequence)
UNIQUE(space_key, idempotency_key)
```

and the stream/watermark row must be updated in the same transaction as observation
insertion.

## Concurrency acceptance gate

The Phase 1 stress suite must test real concurrent writers, not only sequential volume.

Required scenarios include:

1. at least 32 concurrent writers targeting the same memory space;
2. repeated batches large enough to produce at least 10,000 committed observations;
3. duplicate idempotency keys racing concurrently;
4. process/task cancellation or transaction rollback during append;
5. concurrent writers across different memory spaces to confirm streams do not block
   each other unnecessarily;
6. restart/reconnect followed by continued appends;
7. verification that committed sequences are unique and strictly increasing in commit
   authority order for the stream;
8. verification that each idempotency key maps to exactly one durable observation;
9. verification that the observation watermark equals the highest committed sequence;
10. verification that no rollback advances the durable watermark.

The phase does not pass if correctness depends on a Python mutex or one-process execution.

## Phase 1 exit criteria

Phase 1 is complete only when PostgreSQL integration tests demonstrate:

- database-enforced allocation under contention;
- durable idempotency;
- observation/disposition persistence;
- owner/principal isolation;
- visibility filtering;
- digest verification;
- governance revoke/purge semantics;
- monotonic durable watermarks;
- restart safety;
- concurrent writer stress.
