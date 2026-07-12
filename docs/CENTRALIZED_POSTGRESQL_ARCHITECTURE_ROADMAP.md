# Omnix Centralized PostgreSQL Architecture Roadmap

**Status:** Approved architectural direction  
**Repository:** `autonomx/omnix`  
**Initial deployment:** Fully local and offline-capable  
**Target persistence model:** PostgreSQL as the sole authoritative structured-data database  
**Future acceleration:** Redis as optional, non-authoritative infrastructure

## 1. Architecture Decision

Omnix will move from fragmented SQLite, JSON, JSONL, and manifest-backed persistence to one centralized PostgreSQL data architecture.

“Centralized” describes the source of truth, not its physical location. Initially, PostgreSQL will run on the same local workstation as Omnix, its local model services, and its workers. Internet access or cloud infrastructure will not be required.

The target local runtime is:

```text
Local Omnix installation
├── Web client
├── FastAPI gateway
├── PostgreSQL
│   └── All authoritative structured domain data
├── Local BlobStore
│   └── Images, audio, video, models, exports, and large reports
├── Background workers
├── Local model services
│   ├── LLM
│   ├── TTS
│   ├── STT
│   └── Image generation
└── Redis, introduced later
    └── Reconstructible caches and real-time coordination
```

### Permanent authority rules

- PostgreSQL is authoritative for structured application and domain state.
- Blob storage is authoritative for large binary artifacts.
- PostgreSQL stores blob metadata, ownership, hashes, and storage references.
- Redis never stores irreplaceable information.
- JSON is used for export, import, fixtures, reports, and debugging, not live state authority.
- SQLite is removed from the runtime architecture.
- Local model execution and offline operation remain fully supported.
- Cloud hosting is a deployment option, not an architectural requirement.

## 2. Architectural Invariants

Every implementation phase must preserve these rules.

### Transactions

Related writes that form one domain operation must commit in one PostgreSQL transaction.

An RPG turn, for example, must atomically:

1. validate the expected campaign revision;
2. reserve or resolve the submission ID;
3. insert the turn-ledger record;
4. update authoritative campaign state;
5. store canonical effects;
6. update the related job;
7. insert outbox events;
8. commit.

A partially committed authoritative turn is not acceptable.

### Concurrency

Mutable aggregates use optimistic concurrency.

```sql
UPDATE rpg_campaigns
SET state_jsonb = :state,
    state_hash = :state_hash,
    revision = revision + 1
WHERE id = :campaign_id
  AND revision = :expected_revision;
```

A zero-row update is a conflict. The application must not overwrite the newer revision.

### Idempotency

Submission IDs and equivalent operation keys receive database-level unique constraints.

Repeated delivery returns the previously committed result instead of executing the operation again.

### Tenancy

Every user-owned or workspace-owned aggregate must have an explicit ownership boundary.

Tenant isolation must be enforced through:

- a trusted `TenantContext`;
- tenant-scoped repository methods;
- service-level authorization;
- workspace-scoped constraints;
- audit records;
- adversarial cross-workspace tests;
- optional PostgreSQL row-level security as defense in depth.

### Events

Domain writes and their outbox events are committed in the same transaction. Publishing happens after commit and supports at-least-once delivery.

Consumers must therefore be idempotent.

### Secrets

API keys, OAuth tokens, and other credentials must not be stored as ordinary plaintext domain columns.

PostgreSQL stores secret references and metadata. Secret material is held through an encrypted local secret store, operating-system credential store, or equivalent secrets provider.

### Redis

Redis may make Omnix faster or more responsive, but losing or flushing Redis must never:

- lose durable data;
- change an authoritative outcome;
- duplicate a committed turn;
- invalidate ownership rules;
- make recovery impossible.

## 3. Explicit Non-Goals

The initial PostgreSQL migration will not:

- require cloud hosting;
- require internet access;
- require Redis;
- normalize every RPG state field into a separate relational table;
- require full replay-from-genesis event sourcing;
- store large media or model files in PostgreSQL;
- maintain SQLite and PostgreSQL as permanent parallel production backends;
- introduce live provider-backed tests into GitHub Actions.

The initial RPG persistence model will use revisioned JSONB state plus an append-only turn ledger. Full authoritative event sourcing may be considered later if its debugging, rollback, or analytics value justifies the engine complexity.

---

# Phase 0 — Architecture Contract and Persistence Inventory

## Goal

Establish the new source-of-truth rules before changing storage implementations.

## Deliverables

1. Add a central architecture decision record covering:
   - PostgreSQL authority;
   - local and offline deployment;
   - BlobStore authority;
   - Redis boundaries;
   - SQLite retirement;
   - transaction and idempotency rules.
2. Update `SPEC.md` so that local operation no longer implies SQLite-backed authority.
3. Produce a complete persistence inventory covering:
   - SQLite databases;
   - JSON manifests;
   - RPG save files;
   - JSONL event logs;
   - settings files;
   - prompt stores;
   - provider configuration;
   - asset manifests;
   - generated artifacts;
   - caches;
   - temporary and disposable data.
4. Classify each persisted item as:
   - authoritative;
   - derived;
   - cacheable;
   - disposable;
   - binary artifact;
   - secret.
5. Record current data volumes, row counts, file sizes, and foreground latency measurements.
6. Add a source guard preventing new runtime `sqlite3` usage or new authoritative JSON stores.

## Exit criteria

- Every persistent store has an assigned target.
- Every authoritative write path has an identified owning service.
- The new architecture is documented as source of truth.
- No new SQLite-backed runtime subsystem can be introduced.

---

# Phase 1 — Local PostgreSQL Platform

## Goal

Make PostgreSQL a reliable part of the normal local Omnix development and runtime environment.

## Deliverables

### Local infrastructure

Add a PostgreSQL service to the supported local deployment configuration with:

- a persistent volume;
- localhost-only defaults;
- database and application user creation;
- health checks;
- controlled startup and shutdown;
- explicit encoding and timezone settings;
- safe local credentials;
- a documented reset procedure.

Redis is not included in this phase.

### Application configuration

Introduce standard configuration such as:

```text
OMNIX_DATABASE_URL
OMNIX_DATABASE_POOL_MIN
OMNIX_DATABASE_POOL_MAX
OMNIX_DATABASE_CONNECT_TIMEOUT
OMNIX_DATABASE_STATEMENT_TIMEOUT
```

Configuration parsing must validate unsafe or incomplete values before application startup.

### Database package

Create a dedicated package responsible for:

- connection and engine creation;
- connection-pool lifecycle;
- transaction helpers;
- migration status;
- health reporting;
- bounded retries for transient connection failures;
- structured database timing;
- clean process shutdown.

Routes and domain services must not construct their own database connections.

### Migration framework

Introduce one migration system with:

- ordered schema revisions;
- startup compatibility checks;
- explicit upgrade commands;
- schema drift detection;
- migration tests against a real PostgreSQL instance;
- rollback procedures for destructive changes.

### Local operations

Add supported commands for:

- starting PostgreSQL;
- checking health;
- applying migrations;
- creating a backup;
- restoring a backup;
- verifying database integrity;
- inspecting migration status.

### CI

Provider-free CI uses an ephemeral PostgreSQL service for integration tests.

SQLite must not be used as a substitute for PostgreSQL integration behavior.

## Exit criteria

A clean workstation can:

1. provision PostgreSQL;
2. start Omnix;
3. apply migrations;
4. execute a database health check;
5. back up the database;
6. restore it into an empty instance;
7. run PostgreSQL integration tests.

---

# Phase 2 — Persistence Kernel, Unit of Work, and Tenancy

## Goal

Create the shared persistence foundation that all modules will use.

## Deliverables

### Tenant context

Introduce a trusted server-side context:

```python
class TenantContext:
    user_id: str
    workspace_id: str
    membership_id: str
    roles: frozenset[str]
```

Client requests may select resources, but they must not manufacture trusted ownership fields.

### Identity schema

Create initial tables for:

- users;
- workspaces;
- workspace memberships;
- roles and permissions;
- local installation identity;
- API or device sessions;
- audit events.

A local installation receives a real default user and workspace rather than bypassing tenant rules.

### Repository contracts

Define semantic interfaces rather than technology-specific stores:

```text
ChatRepository
CharacterRepository
MemoryRepository
AssetRepository
JobRepository
CampaignRepository
TurnRepository
OutboxRepository
AuditRepository
BlobStore
SecretStore
```

Repository methods must be granular. Avoid contracts such as “load everything” and “save everything.”

### Unit of Work

Introduce a shared transaction boundary:

```python
class UnitOfWork:
    chats: ChatRepository
    characters: CharacterRepository
    memories: MemoryRepository
    jobs: JobRepository
    campaigns: CampaignRepository
    turns: TurnRepository
    assets: AssetRepository
    outbox: OutboxRepository

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

Repositories used by one Unit of Work must share the same PostgreSQL transaction.

### Shared behavior

Standardize:

- IDs;
- UTC timestamps;
- optimistic revisions;
- pagination;
- filtering;
- unique operation keys;
- soft deletion and archival;
- audit metadata;
- error mapping;
- transaction retry policy.

### Contract tests

Create backend contract suites that verify repository semantics independently of route behavior.

Use in-memory fakes for pure unit tests and real PostgreSQL for persistence integration tests.

## Exit criteria

- A complete vertical slice executes through `TenantContext`, Unit of Work, and PostgreSQL.
- No service in that slice depends on a concrete database implementation.
- Cross-workspace access tests fail safely.
- Revision conflicts and duplicate requests have deterministic outcomes.

---

# Phase 3 — Asset Metadata, Blob Storage, and Configuration

## Goal

Move shared metadata away from JSON manifests and establish a durable artifact model.

## Deliverables

### Asset schema

Create tables for:

- assets;
- asset versions;
- blob references;
- ownership;
- MIME type;
- size;
- checksum;
- storage provider;
- storage key;
- generation job;
- lifecycle state;
- creation and deletion audit information.

### BlobStore

Introduce a provider-neutral `BlobStore`.

The first implementation uses the local filesystem. A later hosted deployment may use an S3-compatible implementation without changing domain services.

Blob writes should use:

1. temporary upload or generation;
2. checksum calculation;
3. atomic finalize;
4. PostgreSQL metadata commit;
5. orphan cleanup on failed transactions.

### Configuration and secrets

Move structured non-secret application configuration into PostgreSQL where appropriate.

Credentials remain behind `SecretStore`; PostgreSQL stores references rather than plaintext secret values.

### Importer

Build an idempotent importer for:

- shared asset manifests;
- image manifests;
- generated audio;
- voice-clone metadata;
- reports and exports that need library visibility.

## Exit criteria

- PostgreSQL is authoritative for asset metadata.
- Files remain accessible through BlobStore references.
- Reimporting existing assets creates no duplicates.
- Missing, changed, and orphaned files are reported.
- Deleting an asset follows a controlled metadata and blob lifecycle.

---

# Phase 4 — Characters, Memory, and Chat

These domains should move together because chat sessions reference character versions and memory snapshots.

## Phase 4A — Characters

Create PostgreSQL tables for:

- character profiles;
- immutable character profile versions;
- ownership and visibility;
- publication and import provenance;
- conversation segments;
- character voice references;
- character policies.

Preserve optimistic version updates.

Every profile must be one of:

- private to a user;
- owned by a workspace;
- system-provided and read-only;
- explicitly published or shared.

## Phase 4B — Assistant and Character Memory

Migrate:

- memory records;
- memory candidates;
- memory snapshots;
- snapshot items;
- memory events;
- owner bindings;
- provenance;
- trust and sensitivity metadata;
- revision checks.

Memory queries must always include a trusted owner or workspace scope.

## Phase 4C — Chat

Replace the bulk repository contract with granular operations:

```text
create_session(...)
get_session(...)
list_sessions(...)
update_session(...)
delete_session(...)
append_message(...)
get_message(...)
list_messages(...)
update_delivery_state(...)
create_segment(...)
```

Messages should be appended incrementally, not deleted and reinserted when a session changes.

Introduce:

- cursor pagination;
- workspace-scoped indexing;
- unique message and turn IDs;
- transcript retention policy;
- revisioned session settings;
- interrupted-delivery metadata;
- efficient recent-context queries.

## Migration

Create idempotent importers from the existing character, memory, and chat SQLite databases.

The importer must verify:

- source and target counts;
- stable IDs;
- version history;
- message order;
- ownership;
- snapshots;
- foreign keys;
- content hashes where applicable.

## Exit criteria

- Character, memory, and chat production reads and writes use PostgreSQL.
- Chat no longer performs whole-collection save operations.
- Character version conflicts remain enforced.
- Memory candidates and snapshots retain their lifecycle semantics.
- Cross-tenant isolation tests pass.
- Legacy databases are read-only migration inputs.

---

# Phase 5 — Jobs, Leases, and Transactional Outbox

## Goal

Replace the concrete SQLite job system with a PostgreSQL-backed durable execution ledger.

## Deliverables

### Job schema

Create tables for:

- jobs;
- job stages;
- job events;
- leases;
- attempts;
- progress projections;
- cancellation requests;
- output references;
- errors;
- dead-letter records;
- worker ownership.

### Claiming

Use PostgreSQL transactions and `FOR UPDATE SKIP LOCKED`, or an equivalent safe claim mechanism.

Job claims must support:

- resource classes;
- priorities;
- worker capabilities;
- lease expiry;
- lease renewal;
- attempt counts;
- cancellation;
- retry scheduling;
- graceful worker shutdown;
- stale claim recovery.

### Repository abstraction

Remove service and adapter typing against concrete SQLite job classes.

All job-producing modules use the `JobRepository` contract.

### Transactional outbox

Create `outbox_events` with:

- aggregate type;
- aggregate ID;
- event type;
- payload;
- ordering key;
- creation time;
- publication status;
- attempt count;
- last error.

Outbox insertion occurs in the same transaction as the domain change.

### Foreground RPG submission ownership

Move foreground submission claims into PostgreSQL with:

```text
UNIQUE(session_id, submission_id)
```

Preserve:

- claim tokens;
- leases;
- result reuse;
- guarded finalization;
- abandoned pre-execution claim recovery;
- bounded replay records.

## Exit criteria

- Multiple worker processes cannot claim the same attempt concurrently.
- Expired leases are reclaimed safely.
- Completed jobs are never executed again.
- Foreground duplicate submissions reuse the committed interaction.
- Domain state and outbox events commit atomically.
- No runtime job path uses SQLite.

---

# Phase 6 — RPG Transactional Persistence

## Goal

Make PostgreSQL the sole authority for RPG campaigns, turns, and session progression.

## Initial schema

### `rpg_campaigns`

```text
id
workspace_id
owner_id
revision
state_jsonb
state_hash
engine_version
schema_version
seed
status
created_at
updated_at
```

### `rpg_turns`

```text
campaign_id
sequence
submission_id
expected_revision
resulting_revision
command_jsonb
canonical_effects_jsonb
state_hash_before
state_hash_after
engine_version
interaction_id
created_at
```

Required constraints:

```text
UNIQUE(campaign_id, sequence)
UNIQUE(campaign_id, submission_id)
UNIQUE(campaign_id, interaction_id)
```

### `rpg_snapshots`

```text
campaign_id
revision
snapshot_jsonb or blob_reference
state_hash
engine_version
schema_version
created_at
```

### Supporting records

Add tables for:

- interaction timeline records;
- foreground submission ownership;
- campaign participants;
- campaign permissions;
- compaction checkpoints;
- migration history;
- replay and validation metadata.

## Turn transaction

A foreground turn follows this transaction:

1. resolve tenant and campaign authorization;
2. resolve the submission ID;
3. return the existing result when already committed;
4. read the campaign and expected revision;
5. execute deterministic simulation;
6. begin or continue the Unit of Work transaction;
7. insert the turn ledger row;
8. update the campaign using revision compare-and-swap;
9. insert interaction records;
10. update the job record;
11. insert outbox records;
12. commit;
13. return the compact V2 response.

Redis is not involved.

## State model

Use JSONB for the complete normalized authoritative state initially.

Relational tables should be added only for data that needs:

- independent ownership;
- frequent cross-campaign querying;
- strong relational constraints;
- targeted updates;
- reporting or analytics at scale.

Do not prematurely normalize every NPC, inventory item, or world variable.

## Hashing and auditing

Each turn stores:

- state hash before;
- state hash after;
- engine version;
- schema version;
- command;
- canonical effects;
- resulting revision.

Narration and presentation output are not required to reconstruct simulation truth.

## Snapshots

Create snapshots:

- periodically;
- before destructive migrations;
- before major engine-version changes;
- on explicit export;
- when ledger size or replay cost reaches a measured threshold.

## Exit criteria

- A repeated submission cannot produce a second authoritative turn.
- A stale revision cannot overwrite a newer campaign.
- Campaign state, turn ledger, interaction record, and outbox commit together.
- Restarting gateways or workers does not lose committed state.
- Existing deterministic and local-provider acceptance tests continue to pass.
- JSON files are no longer authoritative RPG saves.

---

# Phase 7 — Remaining Persistence Consolidation

## Goal

Eliminate every remaining runtime SQLite database and authoritative JSON store.

The Phase 0 inventory determines the exact list, but known areas include:

- research cache or research records;
- avatar generation;
- avatar and viseme metadata;
- provider cache status;
- narrative persistence;
- prompt stores;
- feature-specific settings;
- compatibility manifests;
- report metadata;
- any remaining module-specific SQLite databases.

For each store, decide whether it is:

- durable domain data → PostgreSQL;
- artifact metadata → PostgreSQL plus BlobStore;
- cache → PostgreSQL-derived or in-memory;
- disposable temporary data → bounded temporary filesystem storage;
- secret → SecretStore.

Do not migrate disposable caches merely to preserve their current format.

## Exit criteria

Repository source guards show:

- no runtime `sqlite3.connect`;
- no new `.sqlite` or `.sqlite3` database files;
- no authoritative manifest-backed mutable state;
- no domain service writing directly to feature-specific JSON files.

---

# Phase 8 — Data Migration and Cutover

## Goal

Move existing local data safely while avoiding a permanent dual-database architecture.

## Migration strategy

Because the first deployment is local, prefer a controlled maintenance-window migration over long-running dual writes.

### Preflight

1. Stop mutating services.
2. Verify a clean PostgreSQL schema.
3. Enumerate all legacy sources.
4. Create file and database backups.
5. Calculate source counts and hashes.
6. Detect corrupt or unsupported records.
7. Produce a dry-run migration report.

### Import

Run importers in dependency order:

1. local user and workspace;
2. assets and blob metadata;
3. characters and versions;
4. memory records and snapshots;
5. chat sessions and messages;
6. jobs and job events;
7. RPG campaigns, turns, and interactions;
8. remaining subsystem data.

### Verification

Verify:

- row counts;
- stable IDs;
- foreign keys;
- ownership;
- ordering;
- revisions;
- checksums;
- campaign state hashes;
- file references;
- latest active records;
- sampled API responses.

### Cutover

1. Record the exact migration version.
2. Switch repository factories to PostgreSQL.
3. Disable legacy writes.
4. Restart Omnix.
5. Run smoke tests.
6. Run backup and restore validation.
7. Archive the legacy data in a clearly marked backup directory.

### Rollback

Before declaring success, prove that the pre-migration backup can restore the previous local installation.

Do not implement silent fallback to SQLite after PostgreSQL cutover. A PostgreSQL failure should be visible and recoverable, not hidden by switching authority.

## Exit criteria

- PostgreSQL is the only live structured-data authority.
- Existing user data is accessible and verified.
- Legacy files are immutable backups only.
- Rollback has been rehearsed.
- The migration report records all skipped or transformed records.

---

# Phase 9 — SQLite Retirement

## Goal

Remove SQLite from the supported runtime and development architecture.

## Deliverables

- Delete SQLite repository implementations.
- Delete SQLite schema initialization code.
- Remove SQLite-specific environment variables.
- Remove runtime SQLite dependencies and imports.
- Replace SQLite integration tests with PostgreSQL tests.
- Replace pure repository unit tests with in-memory fakes where appropriate.
- Remove code paths that select a SQLite backend.
- Update setup documentation.
- Update diagnostics to report PostgreSQL health and migration status.
- Update backup documentation.
- Retain one-shot legacy import tooling only for a defined transition window.
- Delete or archive the importer after the supported migration window ends.

## Definition of completion

A repository-wide source inspection should find no active runtime dependency on SQLite.

SQLite files may exist only as user-created legacy backups, not as files Omnix opens during normal operation.

---

# Phase 10 — Operational and Security Hardening

## Goal

Make the centralized local database dependable before scaling processes or adding Redis.

## Deliverables

### Reliability

- automated backups;
- restore rehearsals;
- migration rollback procedures;
- database health and readiness probes;
- clean shutdown;
- bounded retry behavior;
- disk-space monitoring;
- corruption and failed-migration reporting.

### Security

- least-privilege database roles;
- credentials outside source control;
- encrypted secret handling;
- tenant authorization tests;
- audit trails;
- secure exports;
- controlled diagnostic payloads;
- optional row-level security;
- retention and deletion workflows.

### Observability

Instrument:

```text
database.pool_wait
database.transaction
database.query
database.commit
database.rollback
repository.operation
outbox.publish
job.claim
job.lease_renew
session.load
session.persist
rpg.turn_commit
blob.read
blob.write
```

Record counts and duration without leaking prompts, memories, secrets, or full campaign state.

## Exit criteria

- Backup and full restore pass.
- A failed migration cannot silently start the application.
- Tenant-leakage tests pass.
- Database and storage health are visible through diagnostics.
- Sensitive content is absent from routine telemetry.

---

# Phase 11 — Distributed Runtime Correctness

## Goal

Prove that PostgreSQL alone can coordinate multiple processes before introducing Redis.

## Deliverables

### Stateless gateways

Gateway instances keep no authoritative process-local session state.

Any gateway can serve the next request using PostgreSQL and BlobStore.

### Worker registry

Create worker records for:

- worker identity;
- authenticated connection;
- capabilities;
- available models;
- GPU and CPU resources;
- current leases;
- heartbeat;
- software version;
- draining state.

### Distributed execution

Support:

- multiple local workers;
- remote workers later;
- capability-aware scheduling;
- retry after worker failure;
- graceful draining;
- stale-worker detection;
- duplicated event delivery;
- job cancellation;
- bounded dead-letter behavior.

### Event delivery

Consume the transactional outbox to provide:

- SSE events;
- WebSocket updates;
- job progress;
- narration availability;
- asset completion;
- provider and worker status.

The durable outbox remains the recovery source.

### Failure testing

Test:

- gateway crash before response;
- gateway crash after commit;
- worker crash before lease expiry;
- worker crash after external execution;
- duplicate HTTP request;
- duplicate outbox delivery;
- delayed consumer;
- stale campaign writer;
- database restart;
- BlobStore temporary failure.

## Exit criteria

At least two gateway processes and multiple workers can operate concurrently without:

- duplicate authoritative turns;
- lost updates;
- duplicate completed jobs;
- tenant leakage;
- unrecoverable event loss.

---

# Phase 12 — PostgreSQL Performance Optimization

## Goal

Optimize the centralized architecture using measurements before adding Redis.

## Deliverables

### Query discipline

- cursor pagination;
- bounded result sizes;
- no unbounded collection loads;
- no message delete and reinsert patterns;
- no N+1 repository access;
- query-count budgets for major endpoints;
- slow-query recording;
- execution-plan review for hot queries.

### Indexing

Add measured indexes for:

- workspace ownership;
- session ordering;
- chat message pagination;
- memory scopes and revisions;
- character versions;
- job status, priority, and availability;
- lease expiry;
- outbox publication status;
- campaign revision;
- turn sequence and submission ID;
- asset ownership and type.

### RPG projections

Keep the authoritative JSONB state, but add derived relational or materialized projections for genuinely hot reads such as:

- campaign summaries;
- active participants;
- recent interactions;
- current location;
- lightweight UI status;
- searchable journal entries.

Derived projections must be rebuildable from PostgreSQL authority.

### Pool and transaction tuning

Measure:

- connection-pool wait;
- transaction duration;
- lock wait;
- rows scanned versus returned;
- serialization cost;
- JSONB payload sizes;
- commit latency;
- checkpoint and vacuum behavior.

### Performance gates

Compare against pre-migration baselines.

The migration should not be declared complete while major foreground workflows show unexplained regressions.

## Exit criteria

- Hot paths have measured query plans.
- Query counts are bounded.
- Foreground turn persistence is no longer an unknown latency component.
- Remaining bottlenecks are identified with evidence.
- Redis candidates have measurable expected benefit.

---

# Phase 13 — Redis Acceleration and Real-Time Coordination

## Goal

Introduce Redis only for workloads where PostgreSQL-backed correctness is already proven and profiling shows value.

## Phase 13A — Low-risk ephemeral capabilities

Start with:

- rate limiting;
- presence;
- WebSocket fan-out;
- transient UI activity;
- worker heartbeat projections;
- short-lived reservations;
- short-lived authentication or OAuth state where appropriate.

## Phase 13B — Revision-addressed caching

Use immutable or revision-keyed entries:

```text
character:<character-id>:v<version>
memory:<owner-id>:r<revision>
chat-context:<session-id>:r<revision>
campaign-projection:<campaign-id>:r<revision>
provider-capabilities:<provider-id>:v<version>
```

Avoid loosely invalidated mutable `:current` keys where practical.

Cache entries must contain enough revision information to reject stale data.

### Commit order

Always:

1. commit PostgreSQL;
2. then invalidate or update Redis;
3. fall back to PostgreSQL on cache miss or Redis failure.

Never update Redis before the authoritative commit.

## Phase 13C — Job delivery acceleration

Introduce Redis Streams only if PostgreSQL job polling or outbox distribution becomes a measured bottleneck.

PostgreSQL remains:

- the job ledger;
- the lease authority;
- the completion authority;
- the source for recovery.

Redis delivery is at-least-once, and workers remain idempotent.

## Phase 13D — Distributed locks

Redis locks come last.

Any Redis-assisted lock must use:

- fencing tokens;
- PostgreSQL revision checks;
- bounded lease duration;
- guarded renewal;
- idempotency keys;
- safe behavior after lock expiry.

Redis must never be the sole correctness boundary.

## Redis acceptance test

Stop or flush Redis during active workloads.

Omnix may temporarily become slower or lose ephemeral presence information, but it must not:

- lose durable jobs;
- corrupt campaigns;
- duplicate authoritative turns;
- expose cross-tenant data;
- lose assets;
- require manual reconstruction.

---

# Phase 14 — Capabilities Enabled by Centralization

Once PostgreSQL, distributed correctness, and optional Redis acceleration are stable, implement:

- multi-device synchronization;
- authenticated remote access;
- remote model workers;
- cloud or NAS backups;
- shared characters;
- governed character publication;
- shared memory policies;
- shared RPG campaigns;
- spectators;
- multiplayer roles;
- deterministic participant action ordering;
- reconnect and resume;
- workspace administration;
- quotas;
- usage accounting;
- audit review;
- data export and account deletion.

Multiplayer requires its own roadmap covering simultaneous command policy, hidden information, host authority, participant permissions, and deterministic ordering.

---

# Delivery and Pull Request Strategy

Use narrow, auditable slices.

Each slice should contain:

- one clear persistence capability;
- its schema migration;
- repository implementation;
- service integration;
- PostgreSQL integration tests;
- tenant and concurrency tests where relevant;
- documentation;
- operational notes;
- no unrelated cleanup.

Recommended opening sequence:

1. **Phase 0.1:** architecture decision and persistence inventory.
2. **Phase 1.1:** local PostgreSQL service and health check.
3. **Phase 1.2:** database package and migration runner.
4. **Phase 1.3:** PostgreSQL CI service and integration-test fixture.
5. **Phase 2.1:** users, workspaces, and memberships.
6. **Phase 2.2:** trusted `TenantContext`.
7. **Phase 2.3:** Unit of Work and transaction contract.
8. **Phase 2.4:** repository contract-test framework.
9. **Phase 3.1:** PostgreSQL asset metadata.
10. **Phase 3.2:** local BlobStore abstraction.
11. **Phase 4.1:** character profiles and versions.
12. **Phase 4.2:** memory records and snapshots.
13. **Phase 4.3:** granular chat sessions.
14. **Phase 4.4:** append-only chat messages.
15. **Phase 5.1:** PostgreSQL job ledger.
16. **Phase 5.2:** transactional claims and leases.
17. **Phase 5.3:** transactional outbox.
18. **Phase 5.4:** foreground RPG submission ownership.
19. **Phase 6.1:** RPG campaign and turn schema.
20. **Phase 6.2:** transactional campaign persistence.
21. **Phase 6.3:** snapshots, hashes, and migration importer.
22. **Phase 7.x:** remaining store consolidation.
23. **Phase 8.x:** full migration and cutover.
24. **Phase 9.x:** SQLite removal.

Do not combine the entire migration into one pull request.

---

# Global Verification Requirements

Every phase must maintain:

- provider-free GitHub Actions;
- no live LLM calls in CI;
- deterministic unit and integration tests;
- exact-head CI verification;
- migration tests against PostgreSQL;
- clean-install tests;
- backup and restore tests;
- tenant-isolation tests;
- duplicate-request tests;
- stale-revision tests;
- bounded response and record sizes;
- local provider-backed acceptance only through explicit local operator runs.

---

# Final Definition of Done

The centralized persistence initiative is complete when:

1. PostgreSQL is the sole live authoritative structured-data database.
2. No runtime path opens or writes SQLite.
3. RPG JSON saves are no longer authoritative.
4. Asset JSON manifests are no longer authoritative.
5. All domain writes use repository and Unit-of-Work boundaries.
6. Tenant ownership is enforced for every user-owned aggregate.
7. Duplicate requests cannot create duplicate authoritative effects.
8. Stale revisions cannot overwrite current state.
9. Jobs survive worker and gateway crashes.
10. Domain writes and outbox events commit atomically.
11. Existing local data has been imported and verified.
12. Backup and full restore have been rehearsed.
13. Omnix runs fully offline with local PostgreSQL.
14. Redis is optional and removable without correctness loss.
15. SQLite runtime code, tests, and configuration have been retired.
16. Current RPG latency, quality, and determinism acceptance criteria remain satisfied.

## Final target statement

> **Omnix will use a centralized PostgreSQL architecture that can run entirely on the local machine. PostgreSQL will be the sole authoritative database for structured domain state, while a provider-neutral BlobStore will hold large artifacts. Local execution, offline operation, and self-hosting remain first-class capabilities. SQLite will be retired from the runtime. Redis will be introduced later as an optional, reconstructible acceleration and real-time coordination layer after PostgreSQL-backed correctness and performance have been established.**
