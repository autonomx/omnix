# Omnix framework scaling implementation — 2026-09-26

This completes the five follow-up items from the framework ownership review.
It builds on [the ownership implementation](FRAMEWORK_OWNERSHIP_IMPLEMENTATION_2026-09-26.md)
and [the original framework review](FRAMEWORK_REVIEW_2026-09-26.md).

## Implemented boundaries

| Area | Implementation |
| --- | --- |
| Atomic Chat completion | One PostgreSQL transaction persists the assistant reply, routing/context metadata, completion validation, job status, logs, and terminal event. Owner liveness is checked before writes and again before commit. Validation failure or ownership expiry rolls back the whole completion. |
| Distributed submission and ordering | Chat admission locks the durable session row before checking the browser submission ID and creating the user message/job. Independent processes reuse the existing accepted job. SQL enforces earlier active jobs finishing before later jobs start. Migration `0097_chat_session_coordination.sql` adds the session lookup index. |
| Worker ownership and shutdown | Production processes explicitly choose `worker` or `api`. A dedicated PostgreSQL connection holds a workspace advisory lock for the trading monitor cohort. Only its owner runs startup or manual monitor starts. Connection loss revokes new guarded database operations and triggers supervised shutdown. |
| Modular gateway composition | `feature_registry.py` owns ordered feature registration; core Chat, jobs/events, and assets have separate route modules with injected stores. `lifecycle.py` owns application startup/shutdown. Normal gateway composition preserves the original `FastAPI.__init__`; importing the gateway package no longer installs routes on unrelated apps. |
| Measurements and regression gates | Added actual PostgreSQL concurrency, rollback, ownership-loss, and lifecycle tests; a four-process load/crash harness; and queue saturation measurements. Existing CI now includes the new lifecycle and offload tests, with PostgreSQL integration coverage collected from the persistence directory. |

Explicit transaction sharing is confined to one database adapter and originating
thread. Existing repository helpers join the root transaction using savepoints;
their commits cannot prematurely commit the root. Nested rollback discards its
pending maintenance callbacks. Maintenance runs after the root connection and
transaction scope have been released, and never runs for rolled-back completion.

Admission, cancellation, and completion acquire the session lock before local
job locks. Provider interruption is deferred until the cancellation/admission
transaction commits. A failed new admission therefore cannot interrupt an
otherwise valid previous provider invocation.

Chat dispatchers reject admissions after shutdown, cancel pending/active jobs,
and join workers with a deadline. A separate semaphore bounds actual provider
invocations, including providers that ignore cancellation: they retain capacity
until their invocation returns. Liquidation collectors now cancel their async
tasks and join their threads. Voice persistence rejects checkpoints after stop
and supports explicit restart; startup TTS tasks are canceled and gathered.

Gateway schema and public route response contracts remain unchanged. The
remaining provider/store instrumentation is initialized explicitly; compatibility
exports and opt-in legacy hook entrypoints remain for existing callers.

## Measured baseline

Windows, Python 3.11.12, PostgreSQL 17 in a disposable local Docker container.
These are controlled transaction measurements, excluding external model
providers, HTTP transport, auxiliary assistant-turn work, and post-turn
maintenance. Each load process has its own database pool and gateway owner.
Child initialization is excluded from measured load duration.

| Workload | Result |
| --- | --- |
| Four processes, 40 sessions, 160 submission attempts | Exactly 40 unique jobs; admission p50 **17.31 ms**, p95 **28.19 ms**; **115.64 attempts/s** |
| Four processes, one contended session, 160 attempts | Exactly 40 unique jobs; admission p50 **36.41 ms**, p95 **49.98 ms**; **63.62 attempts/s** |
| Combined load integrity | **80 completed jobs**, **160 persisted messages**; assertions check expected totals |
| Forced child process termination | One job recovered, one terminal event, **2,003 ms** after termination with a **2-second test lease** and **100-ms explicit recovery polling** |
| Recovery scan with 600 abandoned Chat jobs behind 1,000 newer unrelated jobs | All **600** found; p50 **37.69 ms**, p95 **62.24 ms**; old latest-500 query found **zero** |
| Recovery transitions | **600** terminal events; repeat recovery changes **zero** jobs; about **169 jobs/s** in this run |
| Idle scheduling saturation, 10,000 attempts | **128 accepted**, **9,872 rejected**; approximately **191 KiB** retained Python memory |

Raw results:

- [Concurrent load and process loss](measurements/gateway-scaling-2026-09-26.json)
- [Recovery and queue saturation](measurements/chat-recovery-scaling-2026-09-26.json)

Production still uses a 30-second gateway lease, 5-second heartbeat, and
15-second recovery interval. The 2-second crash measurement is a deliberately
shortened test configuration, not a production recovery promise.

Reproduce against a migrated **disposable** database named
`omnix_refactor_baseline`, using `OMNIX_BENCHMARK_DATABASE_URL`, or the harness's
`--local-disposable` fixture at port 16432:

```text
python scripts/benchmark_gateway_scaling.py --local-disposable --workers 4 --submissions 40 --output docs/measurements/gateway-scaling-2026-09-26.json
python scripts/benchmark_chat_recovery.py --local-disposable --samples 20 --output docs/measurements/chat-recovery-scaling-2026-09-26.json
```

Run benchmarks and repository tests sequentially when sharing a disposable
database: some existing test fixtures reset database tables. The harness removes
its own workspaces/runtime nodes and terminates only children it created.

## Validation

- **120 focused tests passed** across Chat atomicity/ownership, persistence
  execution/runtime coordination, transaction policy, dispatch capacity,
  generation, live PostgreSQL Chat, gateway lifecycle, voice offload, and Chat/
  gateway API behavior.
- Real database tests terminate the advisory-lock backend and verify a successor
  can acquire ownership while the previous owner fails closed.
- Ruff and Python compilation pass for all changed/new Python paths.
- Compose configuration validates with the optional `replicas` profile enabled.
- Exported OpenAPI remains byte-identical to the committed contract: SHA256
  `61ee02289fb4a157f52c49ff9c39355c25081e1bc891cf3c9f03c43c9b690842`.
- A broader exploratory run exposed nine existing failures reproduced against
  an isolated committed checkout: retired SQLite imports, legacy settings
  expectations, obsolete four-tool registry/dashboard counts, and unavailable
  GitHub runtime adapter. These are outside the changed behavior. A tenth
  vision test inherited local provider settings; its fixture now selects its
  mocked local vision provider explicitly and passes.
- The full repository suite and hosted CI were not run. Existing FastAPI event
  and `audioop` deprecation warnings remain.

## Deployment

Apply forward migrations through the existing migration/bootstrap path. Stop
older gateway processes before first deployment: their inline Chat jobs lack
owner identity and cannot safely participate in owner-aware recovery. Migration
execution already uses PostgreSQL advisory transaction locking.

Run exactly one process with `OMNIX_GATEWAY_BACKGROUND_ROLE=worker` per workspace;
this is the default and is explicit on the normal Compose `omnix` service.
Additional production gateway processes must set the role to `api`. The optional
Compose `omnix-api` service in profile `replicas` shares PostgreSQL and the local
resources volume, disables startup TTS warmup, and exposes port 8000 only on the
container network. A reverse proxy/load balancer is required to serve those
replicas; this change does not deploy one. Use one Uvicorn worker per service.

A second worker-role process fails startup instead of duplicating monitors.
API-role processes continue serving Chat/jobs and other request routes but do
not start the trading monitor cohort. Restart a failed worker service to acquire
released ownership; API replicas do not automatically promote themselves.
Each gateway has its own leased Chat execution identity and readiness checks.

## Practical limits

- The measured workload does not establish end-to-end throughput for external
  providers, voice/GPU workloads, brokerage traffic, or large production data.
  Provider and hardware limits still determine usable replica capacity.
- PostgreSQL locking coordinates the job-based Chat generation path. Direct
  streaming retains its existing request-owned execution model; durable session
  mutations are serialized, but streaming providers do not gain distributed
  scheduling or the bounded job dispatch contract.
- Long sessions now page through the complete transcript rather than silently
  omitting messages after 500. Their materialized history still grows in memory
  and latency with session length; prompt/window policies remain responsible
  for model context selection.
- PostgreSQL ownership prevents duplicate monitor startup and rejects new
  guarded persistence operations after loss. It cannot retract external
  requests already in flight or force-stop a noncooperative provider thread.
  Provider-side execution fencing would require a separate protocol.
- An API replica does not own the background monitor controls. Operational
  monitor start/stop requests should be routed to the worker service.
- Replicas require shared blob/resources storage. The Compose example shares
  storage on one host; multiple hosts need an equivalent shared storage setup.
- Trading execution authority, issued capabilities, approval policy, and
  existing deterministic strategy gates are preserved. Background ownership
  supplies no new trading or agent capability grants.

The disposable database/container used for these measurements was removed after
validation. At this implementation stage, no application deployment or production
data migration had been run. The subsequent test repairs, real-provider checks,
and native worker/API deployment are recorded in
[FRAMEWORK_ROLLOUT_2026-09-26.md](FRAMEWORK_ROLLOUT_2026-09-26.md).
