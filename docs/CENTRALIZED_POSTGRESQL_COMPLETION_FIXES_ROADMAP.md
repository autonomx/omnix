# Omnix PostgreSQL Completion Fixes Roadmap

**Status:** Active execution overlay  
**Repository:** `autonomx/omnix`  
**Base architecture:** `docs/CENTRALIZED_POSTGRESQL_ARCHITECTURE_ROADMAP.md`  
**Decision record:** `docs/architecture/ADR-0001-centralized-postgresql-authority.md`  
**Execution branch:** `agent/postgresql-completion-c0-c8`

This document closes the remaining correctness, recovery, security, lifecycle, and roadmap-governance gaps in the centralized PostgreSQL architecture. It does not reopen the approved authority model: PostgreSQL remains authoritative for structured domain state, BlobStore remains authoritative for large binary artifacts, SQLite remains retired from normal runtime authority, and Redis remains optional and reconstructible.

## Status model

Each corrective phase uses one of these states:

- `planned` — scope accepted but implementation has not started;
- `in_progress` — implementation is present on the execution branch but exact-head verification is incomplete;
- `verified` — implementation and required exact-head GitHub Actions passed;
- `deferred` — deliberately excluded from the current completion program with a recorded reason.

## Phase status and evidence

| Phase | Status | Depends on | Required evidence |
|---|---|---|---|
| C0 — Governance and gate ordering | in_progress | Existing PostgreSQL roadmap | roadmap overlay, release gates, CI documentation guard |
| C1 — Transaction and schema evolution contract | planned | C0 | migration lock, compatibility policy, retry tests |
| C2 — Outbox and side-effect delivery | planned | C1 | versioned envelope, inbox dedupe, replay/failure tests |
| C3 — Tenant integrity and security baseline | planned | C1 | composite tenant constraints, least-privilege policy, adversarial tests |
| C4 — Coordinated PostgreSQL and BlobStore recovery | planned | C1, C3 | backup generation, blob manifest, clean restore verification |
| C5 — Current-topology distributed correctness | planned | C1, C2, C4 | multi-gateway/worker crash and duplicate-delivery suite |
| C6 — Cutover and rollback state machine | planned | C4, C5 | guarded transitions, rollback boundary, operator runbook |
| C7 — Data lifecycle, capacity, and maintenance | planned | C2, C4 | retention rules, capacity thresholds, safe cleanup tests |
| C8 — Final integration and completion evidence | planned | C0–C7 | exact-head matrix, evidence reconciliation, final status |

A phase is not `verified` merely because code or documentation exists. The exact branch head containing the phase must have its required GitHub Actions completed successfully.

## Release gates

### Gate A — Ready to activate PostgreSQL authority

Requires:

- C1 transaction and schema compatibility verified;
- C2 durable event delivery verified;
- C3 tenant and privilege protections verified;
- C4 coordinated PostgreSQL-plus-BlobStore restore rehearsal passed;
- C5 current-topology crash and concurrency suite passed;
- migration preflight clean and no unresolved integrity mismatches.

### Gate B — Ready to reopen writes

Requires:

- verified legacy import or verified fresh-install activation;
- coordinated post-import backup generation completed;
- clean restore verification of that generation;
- cutover state is `postgresql_activated_frozen`;
- deterministic smoke checks passed;
- operator-visible acknowledgement that legacy rollback becomes lossy after PostgreSQL accepts new writes.

### Gate C — Centralization complete

Requires:

- PostgreSQL authority stabilized after writes reopen;
- no runtime SQLite or mutable JSON authority paths;
- C7 lifecycle controls active;
- full exact-head provider-free verification green;
- local provider-backed acceptance recorded separately from GitHub Actions;
- this status table and linked evidence reconciled with the implemented repository state.

## Corrective phase specifications

### C0 — Roadmap Governance and Gate Reordering

Deliverables:

1. Maintain this phase-status table with dependencies and evidence.
2. Define Gate A, Gate B, and Gate C before further implementation.
3. Treat operational recovery, current-topology correctness, and security as pre-cutover requirements where applicable.
4. Keep future scale-out, Redis, remote workers, cloud hosting, and multiplayer outside the corrective critical path.
5. Link the architecture roadmap, ADR, persistence inventory, operations guide, runtime-retirement document, and cutover runbook.
6. Add a deterministic CI guard that verifies this execution overlay retains C0 through C8 and all three release gates.

Exit criteria:

- every corrective phase has an explicit status, dependency, and evidence requirement;
- completion claims require exact-head evidence;
- the release gates cannot be removed without failing deterministic CI.

### C1 — Transaction and Schema Evolution Contract

Implement one shared database execution policy covering:

- migration advisory locking;
- supported application/schema version range;
- startup rejection of incompatible schemas;
- expand-and-contract migration rules;
- resumable data backfills and low-lock index changes;
- transaction isolation, lock timeout, and statement timeout policy;
- bounded retry classification for serialization, deadlock, and transient connection failures;
- prohibition on model, network, or slow BlobStore calls inside transactions;
- deterministic RPG recomputation after stale revision conflicts;
- durable idempotency keys for external side effects.

### C2 — Complete Outbox and Side-Effect Delivery

Implement:

- globally unique event IDs;
- event schema versions;
- correlation and causation IDs;
- occurrence, availability, and publication timestamps;
- aggregate ordering sequence;
- durable consumer inbox or checkpoints;
- duplicate-event rejection;
- retry scheduling and poison-event quarantine;
- replay from a checkpoint;
- durable idempotency for externally visible side effects.

### C3 — Tenant Integrity and Security Baseline

Implement:

- workspace-scoped composite foreign keys for tenant-owned relationships;
- tenant-scoped repository access and adversarial tests;
- separate runtime, migration, backup/restore, and diagnostic role policy;
- removal of schema-altering privileges from normal runtime operation;
- documented RLS decision for local-only deployment;
- mandatory RLS reassessment before authenticated remote or shared-host operation;
- telemetry and export controls that exclude secret or sensitive payloads.

### C4 — Coordinated PostgreSQL and BlobStore Recovery

Implement:

- durable backup-generation IDs;
- an authoritative manifest of live blob references, checksums, sizes, and lifecycle states;
- blob deletion grace periods covering supported backup generations;
- coordinated PostgreSQL and BlobStore backup workflow;
- clean-database and clean-BlobStore restore verification;
- missing and orphaned blob reporting;
- documented retention, encryption, RPO, and RTO policy.

### C5 — Pre-Cutover Current-Topology Correctness

Verify the currently supported topology before authority activation:

- two gateway processes;
- multiple local workers;
- foreground RPG execution;
- event delivery;
- local BlobStore;
- PostgreSQL;
- local model services represented by deterministic fakes in CI.

The failure matrix covers gateway crashes before and after commit, worker lease failures, duplicate requests, duplicate outbox delivery, stale campaign writers, database restart, BlobStore failure, graceful shutdown, and recovery of unpublished events.

### C6 — Cutover and Rollback State Machine

Persist and guard these states:

```text
legacy_preflight
imported_unverified
imported_verified
postgresql_activated_frozen
postgresql_open_for_writes
postgresql_stabilized
rollback_recorded
```

Before writes reopen, a matching legacy backup may remain a lossless rollback target. After PostgreSQL accepts new writes, normal recovery is forward repair or coordinated PostgreSQL-plus-BlobStore restore. Returning to legacy authority requires explicit destructive acknowledgement and must never happen automatically.

### C7 — Data Lifecycle, Capacity, and Maintenance

Define and enforce lifecycle policy for:

- outbox and consumer inbox records;
- job attempts, job events, and dead letters;
- audit events;
- RPG turns, interactions, and snapshots;
- reports, exports, soft-deleted rows, and expired sessions.

Add bounded payload sizes, disk warning and hard-stop thresholds, safe cleanup rules, vacuum/analyze guidance, bloat inspection, and measured partitioning thresholds.

### C8 — Final Integration and Completion Evidence

Run the full exact-head provider-free matrix, including:

- PostgreSQL persistence and migrations;
- schema compatibility and migration locking;
- tenant isolation;
- backup and coordinated restore;
- outbox replay and deduplication;
- duplicate requests and stale revisions;
- job claims and leases;
- current-topology crash testing;
- SQLite and mutable-authority retirement guards;
- deterministic RPG regressions and endurance gates.

Local provider-backed quality and latency acceptance remains explicit operator evidence and is not added to GitHub Actions.

## Linked operational documents

- `docs/CENTRALIZED_POSTGRESQL_ARCHITECTURE_ROADMAP.md`
- `docs/architecture/ADR-0001-centralized-postgresql-authority.md`
- `docs/architecture/PERSISTENCE_INVENTORY.md`
- `docs/architecture/LOCAL_POSTGRESQL_OPERATIONS.md`
- `docs/architecture/POSTGRESQL_CUTOVER_RUNBOOK.md`
- `docs/architecture/POSTGRESQL_RUNTIME_RETIREMENT.md`

## Pull request discipline

Each corrective phase is committed as a narrow, auditable slice on the execution branch. After each phase head is pushed, required GitHub Actions must complete. Failures are patched on the same branch before the next phase starts. Live model providers, API keys, and local model servers remain outside GitHub Actions.