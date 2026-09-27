# Framework implementation: gateway ownership and Chat capacity

Date: 2026-09-26. This continues the first infrastructure package described in
[FRAMEWORK_IMPLEMENTATION_2026-09-26.md](FRAMEWORK_IMPLEMENTATION_2026-09-26.md).

## Implemented

- Production composition creates a gateway process identity using the existing
  PostgreSQL runtime-node ledger. Lifecycle registration precedes startup
  recovery; shutdown marks the node stopped after gateway hooks finish.
- The node has a 30-second lease, a heartbeat every 5 seconds, and periodic
  recovery every 15 seconds. Heartbeat failure disables Chat admission and
  readiness. An expired process identity cannot be registered again.
- Runtime heartbeats check the current PostgreSQL clock, including when a
  transaction began before expiry. They cannot revive an expired lease using
  an earlier transaction timestamp.
- Accepted production Chat jobs receive the trusted gateway identity. Caller
  metadata cannot override it, and later compatibility updates preserve it.
  Starting, completing, and failing owned inline Chat jobs require a matching,
  live gateway identity. Generic worker claims exclude inline Chat jobs.
- Recovery queries only active inline Chat jobs with no live owner, paginates
  in immutable creation order, and rechecks status and liveness in the UPDATE.
  Competing recovery processes produce one terminal transition and event.
  Cancellation intent is preserved. The accepted user message is updated in
  the same transaction as recovery; assistant-turn bookkeeping remains best effort.
- Migration `0096_chat_recovery_index.sql` adds a partial index for the recovery
  scan. No additional permissions or execution capabilities are issued.
- Local Chat scheduling is limited to 128 outstanding jobs, including its four
  workers. Saturation produces an observable failed job with retryable
  `chat_queue_full`; it does not retain another scheduling work item.
- Idle submission and commit locks can be garbage collected. Threads holding
  or waiting for a lock retain its identity.
- PostgreSQL CI includes the new capacity tests and established Chat generation
  tests; the new integration tests are covered by its persistence directory run.

## Measurements

Raw output: [chat-recovery-2026-09-26.json](measurements/chat-recovery-2026-09-26.json).
Repeatable harness: [benchmark_chat_recovery.py](../scripts/benchmark_chat_recovery.py).

Environment: local Windows, Python 3.11.12, disposable PostgreSQL 17 container;
20 scan samples. Unique benchmark workspace removed afterward. No production
database, model providers, trading monitors, or gateway background hooks used.

| Measurement | Result |
| --- | ---: |
| Abandoned Chat jobs / newer unrelated jobs | 600 / 1,000 |
| Previous latest-500 scan: abandoned jobs found | 0 |
| New paginated scan: abandoned jobs found | 600 |
| Paginated scan p50 / p95 | 35.55 / 60.47 ms |
| Full recovery, including per-job transaction and event | 3.29 seconds |
| Recovery throughput | 182.46 jobs/second |
| Terminal events / second recovery transitions | 600 / 0 |
| Synthetic queue submissions / retained work / rejected work | 10,000 / 128 / 9,872 |
| Synthetic idle queue retained / peak Python allocations | 190.6 / 191.2 KiB |

The queue measurement holds consumers idle and measures Python allocations for
scheduling objects only. It excludes payload size, provider memory, database
records, and total process RSS. Recovery latency is a local workload baseline,
not a production capacity guarantee. The old scan comparison measures missed
work on identical data; it does not claim a latency improvement.

## Validation

- 76 focused tests passed: PostgreSQL ownership, racing recovery, tenant scope,
  cancellation, lease expiry during a transaction, generic-worker exclusion,
  execution and runtime coordination; Chat capacity and generation; gateway
  lifecycle, composition, readiness, and foundation.
- Ruff and Python compilation passed for changed Python files.
- Exported gateway OpenAPI is byte-identical to the committed contract
  (SHA256 `61ee02289fb4a157f52c49ff9c39355c25081e1bc891cf3c9f03c43c9b690842`).
- Full repository and hosted CI suites were not run. Existing audioop and
  FastAPI startup-event deprecation warnings remain in the focused suite.

## Deployment and remaining work

This section records the boundaries at the end of that implementation phase.
The five subsequent changes are implemented and measured in
[the scaling implementation report](FRAMEWORK_SCALING_IMPLEMENTATION_2026-09-26.md).

Apply the forward migration through the existing production bootstrap. Stop
older gateway processes before starting this version: legacy inline jobs lack
owner identity and are interpreted as abandoned. A rolling overlap with an
older version cannot establish their liveness.

**Multiple production replicas remain unsupported.** This package establishes
owner-aware Chat recovery and bounded local scheduling; the next changes must
address these remaining boundaries:

1. Final assistant transcript persistence and successful job completion still
   use separate transactions. The new owner check before transcript writes is
   a precheck, not an atomic ownership fence across both writes.
2. Submission idempotency and per-session ordering still use process-local
   coordination. Cross-process admission needs a durable transaction contract.
3. Trading monitors and some feature workers remain local startup hooks.
   They need deterministic ownership and supervised shutdown before replicas.
4. Providers that ignore cancellation may keep their own invocation threads
   alive after scheduling capacity is released. The queue bound does not bound
   those external executions.
5. Router modularization, hook registration cleanup, startup migration leadership,
   operational retention, and broader load testing remain in the review backlog.

Expiry detection is approximately the remaining lease plus the next recovery
interval; database contention and recovery backlog can increase that delay.
