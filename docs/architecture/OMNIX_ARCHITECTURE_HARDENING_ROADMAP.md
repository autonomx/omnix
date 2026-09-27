# Omnix Architecture Hardening Roadmap

**Status:** Implementation roadmap  
**Target branch:** `refactor`  
**Baseline:** `refactor` at `793b255063c2472a912eb83cc6710f23fc326afb` before this roadmap commit  
**Primary goal:** move the current refactor from a strong transitional architecture to a simpler, explicitly governed, production-proven platform architecture without another broad rewrite.

---

## 1. Executive decision

The current `refactor` branch has already made the most important architectural change: Omnix is no longer organized as one implicit process with many features sharing mutable runtime state.

The new platform direction is sound:

- PostgreSQL is authoritative structured persistence.
- gateway startup is explicit;
- background ownership is explicit;
- jobs use leases, attempts, retries, fencing, and cancellation;
- chat execution has durable ownership;
- API replicas can scale separately from the worker/control process;
- GPU TTS can run behind a service boundary instead of being loaded by every gateway process;
- legacy entry points and duplicate audiobook/runtime implementations are being retired;
- gateway features are decomposed into smaller modules;
- long-running work increasingly uses durable execution contracts instead of inline state.

The next phase must **harden and simplify** this architecture rather than introduce another parallel framework.

The target is to make these guarantees obvious in code:

1. Runtime role and capability ownership are parsed once and are immutable.
2. A process cannot accidentally perform work it does not own.
3. Production dependencies are passed explicitly rather than installed by monkey-patching imported modules.
4. PostgreSQL remains the only production structured-data authority.
5. Feature code depends on stable service/repository interfaces, not persistence migration adapters.
6. Browser code does not need to understand production process topology.
7. Every distributed/runtime invariant has a crash/recovery or multi-process test.
8. Operational health is measurable through one structured diagnostics surface.
9. Transitional compatibility layers have an explicit deletion plan.
10. CI blocks regressions in these invariants.

This roadmap is deliberately incremental. **Do not replace the current gateway, job system, persistence model, or provider system with a new framework.**

---

## 2. Current architecture baseline

The branch currently contains the following important foundations and they should be preserved:

### Production composition

- `src/app/production.py`
- `src/app/gateway/main.py`
- `src/app/gateway/runtime_app.py`
- `src/app/gateway/lifecycle.py`
- `src/app/gateway/runtime_hooks.py`
- `src/app/gateway/feature_registry.py`

Production assembly already separates import-safe ASGI startup from PostgreSQL-authoritative runtime initialization.

### Background execution ownership

- `src/app/gateway/background_runtime.py`
- `src/app/persistence/background_authority.py`

The worker role owns singleton/background execution using PostgreSQL advisory-lock authority. API replicas intentionally do not own background workers.

### Durable chat and job execution

- `src/app/persistence/job_repository.py`
- `src/app/persistence/execution_repositories.py`
- `src/app/persistence/chat_execution.py`
- `src/app/persistence/gateway_runtime.py`
- `src/app/persistence/memory_job_execution.py`
- `src/app/chat/generation_jobs.py`

The branch already has lease ownership, fencing, recovery, cancellation, chat ownership, and transaction-aware memory execution.

### GPU service separation

- `src/app/providers/qwen_http_gateway.py`
- `src/app/gateway/live_voice_runtime_offload.py`
- `src/app/shared.py`

API replicas are now prevented from accidentally instantiating local Qwen TTS when they should use a shared TTS service.

### Gateway scaling and routing

- `scripts/gateway_cluster.py`
- `scripts/deploy_gateway_rollout.py`
- `scripts/validate_gateway_rollout.py`
- `src/apps/web/gateway-routing.ts`

The branch supports one worker/control gateway and additional API replicas.

### Transitional persistence installation

- `src/app/persistence/runtime_install.py`
- `src/app/persistence/*_compat.py`

This is currently the largest architectural debt area. It correctly forces PostgreSQL authority, but does so partly by replacing classes/functions in imported modules.

---

## 3. Target architecture

The desired steady-state architecture is:

```text
                         Browser
                            |
                            v
                   production ingress
                            |
                +-----------+-----------+
                |                       |
                v                       v
        API gateway replicas      worker/control gateway
        request serving only      singleton ownership
                |                       |
                +-----------+-----------+
                            |
                            v
                       PostgreSQL
                 authoritative state
                            |
          +-----------------+------------------+
          |                 |                  |
          v                 v                  v
       job workers      external GPU       provider/model
       leased/fenced      services            services
                         TTS/STT/image
```

Inside a process:

```text
RuntimeConfig
    |
    v
RuntimeCapabilities / Ownership
    |
    v
Production composition
    |
    +--> service interfaces
    |        |
    |        +--> repositories
    |        |       |
    |        |       +--> PostgreSQL
    |        |
    |        +--> external service clients
    |
    +--> gateway feature routers
```

Feature modules should not inspect deployment environment variables, patch imports, or decide persistence authority themselves.

---

# Phase 0 — Freeze invariants and establish a measurable baseline

## Objective

Before simplifying architecture, encode the current runtime invariants so later cleanup cannot silently weaken them.

## Work

### 0.1 Add architecture invariant documentation

Add:

- `docs/architecture/OMNIX_RUNTIME_INVARIANTS.md`

Document at minimum:

- PostgreSQL is production structured-data authority.
- SQLite/in-memory stores are test/import-only unless explicitly selected.
- exactly one worker/control gateway owns singleton background execution per workspace;
- API replicas do not own background workers;
- API replicas do not instantiate local CUDA TTS;
- leased execution must use fencing tokens;
- cancellation must always reach a terminal state;
- chat generation ownership is durable across processes;
- request handlers must not block the event loop on PostgreSQL/provider work;
- production readiness is not equivalent to liveness;
- external GPU service availability is reflected in readiness only when required by deployment policy.

### 0.2 Add an architecture test manifest

Create a compact test manifest in either:

- `docs/testing/ARCHITECTURE_GATES.md`, or
- a structured Python constant consumed by CI.

Map every invariant to one or more tests.

Example:

| Invariant | Test |
|---|---|
| API cannot instantiate local Qwen | `test_api_replica_cannot_construct_local_qwen_tts` |
| canceled expired lease terminates | `test_expired_cancel_requested_job_becomes_terminal_canceled` |
| only worker owns background runtime | gateway scaling lifecycle integration |
| chat owner recovery is fenced | chat execution ownership integration |
| production requires PostgreSQL | gateway runtime baseline |

### 0.3 Capture baseline benchmarks

Use the existing scripts:

- `scripts/benchmark_gateway_baseline.py`
- `scripts/benchmark_gateway_postgresql.py`
- `scripts/benchmark_gateway_scaling.py`
- `scripts/benchmark_chat_recovery.py`
- `scripts/measure_gateway_soak.py`

Commit a small machine-readable baseline under:

- `resources/benchmarks/gateway/refactor-baseline.json`

Do not optimize numbers in this phase. Establish reproducible measurements.

## Acceptance criteria

- Every critical process-ownership rule has a named regression test.
- Benchmark scripts run with documented commands.
- Baseline metrics include p50/p95/p99 where available, error count, active requests, and recovery duration.
- No runtime behavior changes are required in this phase.

---

# Phase 1 — Introduce one immutable RuntimeConfig

## Objective

Stop parsing architecture-defining environment variables throughout unrelated modules.

Environment variables remain the deployment input, but application code should consume a validated immutable configuration object.

## New module

Create:

- `src/app/runtime_config.py`

Suggested model:

```python
class GatewayRole(str, Enum):
    WORKER = "worker"
    API = "api"

@dataclass(frozen=True, slots=True)
class ServiceEndpoint:
    url: str
    required: bool = False

@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    gateway_role: GatewayRole
    tts: ServiceEndpoint | None
    stt: ServiceEndpoint | None
    image: ServiceEndpoint | None
    owns_background_runtime: bool
    allow_local_tts: bool
    api_replica_origins: tuple[str, ...]
```

Exact shape may differ, but configuration must be:

- parsed once;
- validated once;
- immutable;
- easy to construct explicitly in tests;
- independent of FastAPI;
- free from provider/model construction.

## Migrate first

Remove direct deployment-policy reads from:

- `src/app/production.py`
- `src/app/shared.py` for process-role decisions;
- `src/app/gateway/live_voice_runtime_offload.py`;
- `src/app/gateway/background_runtime.py`;
- `scripts/gateway_cluster.py` where practical.

Provider-specific settings may still come from Omnix settings. The point is to centralize **process topology and ownership**, not all application settings.

## Required validation

Fail startup for impossible production configurations, for example:

- API role with a feature configured to require local-only GPU TTS.
- malformed service URLs.
- unknown gateway role.
- duplicate/invalid replica origins.
- contradictory explicit ownership flags.

Do not silently reinterpret invalid production topology.

## Tests

Add:

- unit tests for environment parsing;
- explicit config construction tests;
- invalid topology tests;
- production assembly tests proving modules receive the same config instance/value.

## Acceptance criteria

- Architecture-defining environment variables are parsed by one module.
- Gateway/background/TTS ownership decisions do not independently reinterpret env vars.
- Existing environment variable names remain supported for deployment compatibility.
- No feature behavior changes.

---

# Phase 2 — Formalize runtime capabilities and ownership

## Objective

Generalize the successful authority pattern already present in persistence/trading into a lightweight process capability model.

Do **not** build a generic dependency-injection framework.

## Proposed concept

Create a small runtime capability object, for example:

- `src/app/runtime_capabilities.py`

Potential capabilities:

- `SERVE_API`
- `OWN_BACKGROUND_RUNTIME`
- `RUN_LOCAL_TTS`
- `USE_REMOTE_TTS`
- `RUN_CHAT_DISPATCH`
- `RUN_RECOVERY`
- `RUN_SCHEDULERS`

The final list should stay small and represent real ownership boundaries.

Each process gets capabilities from `RuntimeConfig`.

## Rules

- capability checks happen at composition/startup boundaries;
- do not scatter checks through domain logic;
- request-time checks are only for operations that truly depend on process ownership;
- background service registration should require the owning capability;
- illegal registrations should fail early.

## Refactor targets

- `GatewayBackgroundRuntime`
- chat dispatcher composition in `production.py`
- live voice/TTS startup registration;
- scheduled market/background monitors;
- recovery startup hooks.

## Acceptance criteria

- A reader can determine what a worker or API process owns from one module.
- Adding a new background subsystem requires declaring its ownership.
- API replicas cannot accidentally start worker-only services even if a feature module registers a startup hook.
- Tests cover negative ownership cases.

---

# Phase 3 — Replace runtime monkey-patching with explicit composition

## Objective

Remove the largest remaining transitional architectural debt: production correctness should not depend on replacing classes/functions in already imported modules.

Current `runtime_install.py` is a valid migration mechanism, but it should not be the long-term architecture.

## Important constraint

Do this **incrementally by domain**. Do not delete `runtime_install.py` first.

## Target dependency pattern

Preferred:

```text
route / worker
    |
    v
domain service
    |
    v
repository protocol/interface
    |
    v
PostgreSQL implementation
```

Avoid:

```text
import module
    |
runtime_install monkey-patches class/function
    |
feature unknowingly gets different implementation
```

## 3.1 Define stable repository/service protocols

Prioritize domains currently patched in `runtime_install.py`:

1. Chat
2. Jobs
3. Assets
4. Characters/avatar
5. Memory
6. Assistant settings/tool ledger
7. RPG/session persistence
8. remaining document-style compatibility stores

Protocols should describe behavior, not storage technology.

Do not create interfaces solely to mirror every existing class. Introduce them only where composition needs a stable dependency.

## 3.2 Create a process-owned service container

Expand the existing `GatewayRuntimeServices` concept rather than creating a new DI framework.

Suggested direction:

```python
@dataclass(frozen=True, slots=True)
class RuntimeServices:
    jobs: JobRepository
    chat: ChatRepository
    assets: AssetRepository
    memory: MemoryRepository
    ...
```

Request-scoped transactions should still come from the unit-of-work/database layer.

The container owns factories/repositories, not an open request transaction.

## 3.3 Migrate domain by domain

For each domain:

1. Identify monkey-patched imports in `runtime_install.py`.
2. Add explicit repository/service dependency.
3. Migrate production call sites.
4. Keep compatibility adapter only for untouched legacy call sites.
5. Add an import test proving the migrated domain works without patching.
6. Delete that patch section.
7. Repeat.

## 3.4 Remove global SQLite monkey-patch last

`sqlite3.connect = _retired_sqlite_connect` is useful as a fail-closed migration guard, but global stdlib mutation should eventually disappear.

Replace it with:

- no production code paths that import/use legacy SQLite persistence;
- import-isolation/static tests that reject known SQLite modules from production composition;
- explicit legacy migration/test process entry points when needed.

Only remove the global guard after tests prove production no longer reaches SQLite.

## Acceptance criteria

- `runtime_install.py` shrinks phase by phase.
- Production correctness no longer depends on class replacement for migrated domains.
- Domain tests can inject fake repositories without global monkey-patches.
- No dual authority is introduced.
- PostgreSQL remains the only production authority.

---

# Phase 4 — Simplify gateway composition and lifecycle registration

## Objective

Make gateway startup declarative and inspectable.

The branch has already split `gateway/main.py`; now make feature lifecycle ownership easier to reason about.

## Work

### 4.1 Introduce explicit feature descriptors

Evolve `feature_registry.py` toward a small descriptor structure containing:

- router(s);
- required runtime capabilities;
- startup/shutdown hooks;
- readiness contribution if any;
- optional background workers.

Do not allow feature registration to mutate unrelated global state.

### 4.2 Eliminate startup-hook interception where possible

`register_background_monitor()` currently captures hooks added to FastAPI and moves them under worker ownership.

This is clever transitional behavior, but steady-state registration should look closer to:

```python
register_feature(
    name="trading-monitor",
    background_workers=[...],
    requires={OWN_BACKGROUND_RUNTIME},
)
```

rather than adding hooks and then extracting them from `gateway.router.on_startup`.

### 4.3 Use lifespan composition consistently

Prefer FastAPI lifespan/context managers for new lifecycle behavior.

Reduce new use of deprecated-style startup/shutdown event mutation.

### 4.4 Keep `gateway/main.py` small

Target responsibilities:

- create app;
- install middleware;
- register core routes;
- register feature descriptors;
- compose lifespan;
- expose liveness/readiness.

Domain behavior belongs elsewhere.

## Acceptance criteria

- Feature ownership is visible without inspecting hook mutation.
- Worker-only hooks cannot execute on API replicas.
- Startup order has deterministic tests.
- Shutdown order has deterministic tests.
- `gateway/main.py` does not regrow into a platform monolith.

---

# Phase 5 — Move production routing policy out of the Vite layer

## Objective

Keep `gateway-routing.ts` useful for local development/testing, but production topology should be owned by deployment infrastructure.

## Current state

The Vite layer currently knows about:

- worker origin;
- API replica origins;
- route eligibility;
- speech routing.

This is acceptable as a development proxy but should not be the long-term production load balancer.

## Work

### 5.1 Define route classes

Document route categories:

- stateless API-safe;
- worker/control-only;
- sticky/streaming;
- health/readiness;
- GPU-service proxied.

Expose this classification from backend/shared configuration if practical rather than maintaining unrelated copies.

### 5.2 Add production ingress example

Provide one supported deployment example under:

- `deploy/` or `docs/architecture/`

Use a simple reverse proxy/load-balancer configuration appropriate to the existing deployment model.

Requirements:

- API-safe traffic can load-balance across replicas.
- worker/control routes target the worker.
- WebSocket/SSE connection affinity is preserved for the lifetime of a connection.
- no failed write is replayed automatically against a second replica.
- health and readiness can be checked independently.

### 5.3 Retain local Vite routing

Vite routing remains for:

- local cluster development;
- tests;
- developer convenience.

Mark it explicitly as local/development topology.

## Acceptance criteria

- Production deployment does not require the browser/Vite process to decide backend topology.
- Local development still supports multiple gateway replicas.
- Routing contract tests are shared or mirrored with one authoritative documented policy.

---

# Phase 6 — Make observability a first-class platform capability

## Objective

The architecture now has leases, owners, queues and replicas. Those mechanisms need structured operational visibility.

## Add one platform diagnostics model

Create a structured runtime diagnostics payload that can be served through an existing platform diagnostics route.

Include:

### Process

- runtime/process ID;
- gateway role;
- uptime;
- build/commit identifier when available;
- configured capabilities.

### PostgreSQL

- pool used/available;
- query timeout configuration;
- migration state;
- authority state;
- connectivity/readiness.

### Background ownership

- role;
- advisory lock ownership;
- lock health;
- registered workers;
- worker startup/shutdown state.

### Jobs

- queued by resource class;
- leased;
- running;
- retrying;
- cancel_requested;
- oldest queued age;
- expired lease count;
- dead-letter count;
- claim/failure/retry rates.

### Chat

- active dispatch slots;
- queued dispatches;
- active session ownership;
- recovery count;
- abandoned-job recovery duration;
- admission rejection count.

### TTS / GPU services

- local vs remote;
- endpoint health;
- active streams;
- provider refresh health;
- queue/saturation signals;
- last successful request.

### API replicas

- known origins or deployment identity;
- readiness;
- request counts where available.

## Metrics naming

Use stable names suitable for logs and future Prometheus/OpenTelemetry export. Avoid a second bespoke metrics system if existing Omnix metric infrastructure can represent them.

## Logging

Every lifecycle/ownership transition should include:

- component;
- process role;
- owner ID/token where safe;
- job/session ID where applicable;
- transition;
- duration;
- error class, never credentials.

## Acceptance criteria

- A single diagnostics request can answer “who owns background execution?”
- It can answer “why is work not progressing?”
- It can distinguish queue saturation from provider failure.
- It can identify repeated lease expiry/recovery.
- Secrets/URLs with credentials are redacted.

---

# Phase 7 — Add crash, failover, concurrency, and soak certification

## Objective

Prove the distributed-runtime assumptions instead of validating only happy-path unit behavior.

## Required scenario tests

### 7.1 Background owner loss

1. Start worker A and API replica.
2. Worker A acquires background lock.
3. Kill/lose its PostgreSQL ownership connection.
4. Verify its background workers stop.
5. Start worker B.
6. Verify B can acquire ownership and resume without duplicate singleton execution.

### 7.2 Chat owner crash

1. Start a chat generation.
2. Terminate owning process after durable claim.
3. Allow ownership/heartbeat to expire.
4. Start/reuse another worker.
5. Verify recovery occurs once.
6. Verify no duplicate assistant message is committed.

### 7.3 Job lease fencing

1. Worker A claims a job.
2. Lease expires.
3. Worker B claims a later attempt.
4. Worker A attempts completion.
5. Verify stale attempt is rejected.
6. Verify only B can finalize.

### 7.4 Cancellation during worker loss

Maintain the regression now added:

`running -> cancel_requested -> worker dies -> lease expiry -> canceled`

Never allow this path to become permanently `retrying`.

### 7.5 TTS replica isolation

With N API replicas:

- no API process loads the local CUDA provider;
- all use the configured remote TTS endpoint;
- without a remote endpoint, speech remains worker-routed or startup/readiness fails according to configured policy.

### 7.6 PostgreSQL restart/reconnect

Test transient database loss:

- readiness drops;
- liveness remains available where appropriate;
- background ownership is considered lost;
- no unsafe work continues under stale authority;
- clean recovery occurs after reconnection/restart.

### 7.7 Soak test

Use `scripts/measure_gateway_soak.py`.

Minimum certification profile:

- worker + at least 2 API replicas;
- mixed chat reads/writes;
- SSE;
- WebSocket TTS traffic using mocked/lightweight provider if GPU is unavailable;
- job events;
- controlled failures/restarts.

Track:

- memory growth;
- open threads/tasks;
- DB connections;
- p95/p99 latency;
- error rate;
- recovery count;
- leaked leases;
- duplicate outputs.

## Acceptance criteria

No architecture-hardening phase is complete until its ownership/recovery behavior has an automated failure test.

---

# Phase 8 — Strengthen CI into architecture release gates

## Objective

Turn the architectural guarantees into mandatory merge gates.

## CI groups

Create or refine independent jobs for:

### Fast unit gate

- import isolation;
- runtime config;
- gateway composition;
- route classification;
- provider isolation;
- job state machine.

### PostgreSQL integration gate

- migrations;
- job leasing/fencing;
- chat ownership;
- memory transaction behavior;
- recovery;
- readiness.

### Web contract gate

- typecheck;
- generated API contract check;
- gateway routing tests;
- core workspace tests affected by architecture.

### Multi-process runtime gate

Use spawned local processes with test configuration for:

- worker/API ownership;
- recovery;
- routing;
- shutdown.

### Optional scheduled soak gate

Nightly or manual:

- longer gateway soak;
- benchmark comparison;
- resource leak detection.

## Performance regression policy

Do not fail CI on tiny noisy benchmark changes.

Use generous regression thresholds for stable metrics, for example:

- large p95/p99 latency regressions;
- material throughput collapse;
- leaked workers/connections;
- nonzero duplicate execution;
- unbounded memory growth.

Commit benchmark artifacts for inspection when failures occur.

## Branch policy

Once stable, the PR into `main` should require the architecture gates. Direct pushes to development branches may remain lighter.

## Acceptance criteria

A merge cannot silently break:

- PostgreSQL authority;
- worker/API ownership;
- TTS isolation;
- job fencing;
- chat recovery;
- route topology contracts.

---

# Phase 9 — Retire compatibility layers deliberately

## Objective

Prevent migration infrastructure from becoming permanent architecture.

## Inventory

Create:

- `docs/architecture/OMNIX_COMPATIBILITY_RETIREMENT.md`

For every file matching patterns such as:

- `*_compat.py`
- legacy adapters;
- compatibility callbacks;
- retired persistence bridges;

record:

- why it still exists;
- production call sites;
- tests using it;
- target replacement;
- deletion prerequisite.

## Classification

Use three categories:

### A. Required stable adapter

A legitimate interface adapter that remains useful long-term.

Keep it, but rename it away from `compat` when appropriate.

### B. Migration shim

Exists only because callers still use an old API.

Give it a deletion phase.

### C. Dead compatibility code

No production callers.

Delete after import/search/test verification.

## Guard

Add a test or lint script that prevents **new** `*_compat.py` files unless explicitly allowlisted.

The goal is not zero adapters. The goal is no uncontrolled compatibility growth.

## Acceptance criteria

- Every compatibility module has a disposition.
- `runtime_install.py` is substantially reduced or removed.
- New feature development no longer requires adding monkey-patches.
- Dead compatibility code is deleted rather than preserved “just in case”.

---

# Phase 10 — Consolidate operational documentation and ADRs

## Objective

Ensure architecture is understandable without reverse-engineering implementation.

## Update

- `docs/ARCHITECTURE.md`
- `docs/OPERATIONS.md`
- `docs/SETUP.md`

Document:

- worker vs API process;
- PostgreSQL authority;
- runtime capability ownership;
- TTS service topology;
- gateway cluster startup;
- production ingress;
- readiness/liveness semantics;
- recovery behavior;
- diagnostics;
- required CI gates.

## Add ADRs

At minimum:

### ADR — PostgreSQL as production authority

Record why production does not permit fallback authority.

### ADR — Worker/API gateway split

Record singleton/background ownership and API replica responsibilities.

### ADR — External GPU service boundary

Record why API replicas must not instantiate local CUDA services.

### ADR — Durable job fencing

Record lease/attempt/fencing semantics and stale-worker behavior.

### ADR — Runtime dependency composition

Record the decision to migrate away from runtime monkey-patching.

## Acceptance criteria

A new contributor should be able to answer these questions from docs:

- Which process owns schedulers?
- Can an API replica run TTS locally?
- What happens if a job worker dies?
- What happens if the gateway worker dies?
- What state is authoritative?
- How is a process declared ready?
- Where should a new background subsystem register itself?
- How should a new domain obtain persistence?

---

# 11. Recommended implementation sequence

Codex should execute the roadmap in this order:

1. **Phase 0** — invariant docs + baseline.
2. **Phase 1** — immutable `RuntimeConfig`.
3. **Phase 2** — process capability/ownership model.
4. **Phase 4** — explicit gateway lifecycle registration.
5. **Phase 6** — diagnostics/observability.
6. **Phase 7** — crash/failover/multi-process tests.
7. **Phase 8** — mandatory CI gates.
8. **Phase 3** — migrate compatibility monkey-patches domain by domain.
9. **Phase 9** — delete/rename compatibility layers as migrations complete.
10. **Phase 5** — production ingress ownership of routing topology.
11. **Phase 10** — final architecture/operations docs and ADR refresh.

Why Phase 3 is not first: the compatibility layer is ugly but currently functional. Runtime configuration, ownership tests, diagnostics, and crash certification should be stronger before removing the migration scaffolding.

---

# 12. Commit strategy

Do not implement this roadmap as one giant commit.

Recommended commit/PR slices:

1. `architecture: document runtime invariants and baseline`
2. `runtime: centralize immutable process configuration`
3. `runtime: formalize gateway capability ownership`
4. `gateway: make lifecycle registration explicit`
5. `observability: expose runtime ownership and queue diagnostics`
6. `test: certify worker and chat crash recovery`
7. `ci: enforce architecture runtime gates`
8. `persistence: explicitly compose chat repositories`
9. `persistence: explicitly compose jobs and assets`
10. `persistence: migrate memory and character repositories`
11. `persistence: retire remaining runtime patches`
12. `deploy: move production routing policy to ingress`
13. `docs: finalize architecture ADRs and compatibility retirement`

Each commit should leave the branch runnable.

---

# 13. Coding constraints for Codex

Codex must follow these rules while implementing:

1. Work on `refactor` unless explicitly instructed otherwise.
2. Read the current implementation before changing architecture. The roadmap names targets, not exact required class names.
3. Preserve PostgreSQL as the production authority.
4. Do not introduce a new database, queue broker, service mesh, dependency-injection framework, or orchestration framework.
5. Do not replace the existing job model.
6. Do not create a second gateway.
7. Do not move domain business logic into FastAPI route modules.
8. Do not make browser state authoritative.
9. Do not allow API replicas to acquire singleton/background ownership.
10. Do not allow API replicas to instantiate local Qwen/CUDA TTS.
11. Do not remove a compatibility shim until all production callers are migrated and tests prove it.
12. Do not weaken fencing, lease-token, transaction, or idempotency checks to make tests pass.
13. Prefer explicit dependencies over module globals for new code.
14. Keep request database operations transaction-scoped.
15. Keep slow/blocking database/provider work off the asyncio event loop.
16. Preserve liveness/readiness separation.
17. Redact credentials from logs and diagnostics.
18. Update generated API types/contracts whenever backend contracts change.
19. Add tests for every new ownership or recovery rule.
20. Run focused tests after each phase and the full architecture gates before declaring the roadmap complete.

---

# 14. Required test matrix

At minimum, the final implementation must pass:

## Python unit/runtime

- gateway production bootstrap tests;
- gateway scaling lifecycle tests;
- live voice runtime offload tests;
- Qwen HTTP gateway tests;
- chat execution capacity tests;
- import isolation tests;
- runtime config/capability tests added by this roadmap.

## PostgreSQL integration

- execution integration;
- chat atomic scaling;
- chat execution ownership;
- memory job execution;
- gateway readiness;
- asset streaming where affected.

## Web

- typecheck;
- API generated contract check;
- `src/test/gateway-routing.test.ts`;
- affected Chat/Audiobook/Trading workspace tests.

## Multi-process

Add a dedicated suite or script proving:

- exactly one worker background owner;
- N API replicas start without worker-only services;
- stale job owners are fenced;
- chat recovery does not duplicate output;
- shared TTS remains remote from API replicas;
- graceful shutdown releases authority.

---

# 15. Definition of done

This roadmap is complete when all of the following are true:

- production topology is represented by one validated immutable runtime configuration;
- process ownership is explicit and capability-driven;
- API replicas cannot accidentally execute worker-only/background/GPU-local responsibilities;
- production domains receive dependencies explicitly rather than relying on runtime monkey-patching;
- `runtime_install.py` is either removed or reduced to narrowly documented migration-only behavior;
- every remaining `*_compat.py` has a justified long-term role or a deletion plan;
- production routing topology is owned by deployment infrastructure, with Vite routing retained for local development;
- runtime diagnostics expose ownership, queue, lease, recovery, replica and provider health;
- worker loss, DB authority loss, stale lease, cancellation, and chat-owner crash scenarios are automatically tested;
- architecture gates run in CI for PRs to `main`;
- benchmark/soak tooling demonstrates no material regression or resource leak;
- `ARCHITECTURE.md`, `OPERATIONS.md`, `SETUP.md`, and ADRs describe the actual implementation;
- no duplicate architecture/framework was introduced.

---

# 16. Expected outcome

The architecture after this roadmap should become simpler than the current refactor, not merely more abstract.

The steady-state mental model should be:

```text
configuration
    -> capabilities / ownership
        -> explicit production composition
            -> domain services
                -> repositories / durable jobs
                    -> PostgreSQL

external compute
    -> TTS / STT / image / model services

HTTP
    -> stateless API replicas

singleton execution
    -> worker/control gateway
```

The current branch already contains the hard parts: PostgreSQL authority, durable execution, gateway decomposition, process roles, TTS service separation, and recovery primitives.

This roadmap finishes the transition by making those boundaries **explicit, measurable, testable, and simpler to maintain**.
