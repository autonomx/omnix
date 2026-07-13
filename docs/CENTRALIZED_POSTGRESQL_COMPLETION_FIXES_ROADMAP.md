# Omnix PostgreSQL Completion Fixes Roadmap

**Status:** Final verification in progress  
**Repository:** `autonomx/omnix`  
**Base architecture:** `docs/CENTRALIZED_POSTGRESQL_ARCHITECTURE_ROADMAP.md`  
**Decision record:** `docs/architecture/ADR-0001-centralized-postgresql-authority.md`  
**Execution branch:** `agent/postgresql-completion-c0-c8`  
**Evidence ledger:** `docs/architecture/POSTGRESQL_COMPLETION_EVIDENCE.md`

This document closes the remaining correctness, recovery, security, lifecycle, and roadmap-governance gaps in the centralized PostgreSQL architecture. PostgreSQL remains authoritative for structured domain state, BlobStore remains authoritative for large binary artifacts, SQLite remains retired from normal runtime authority, and Redis remains optional and reconstructible.

## Status model

- `planned` — scope accepted but implementation has not started;
- `in_progress` — implementation is present but exact-head verification is incomplete;
- `verified` — implementation and required exact-head GitHub Actions passed;
- `deferred` — deliberately excluded with a recorded reason.

## Phase status and evidence

| Phase | Status | Depends on | Implemented evidence |
|---|---|---|---|
| C0 — Governance and gate ordering | verified | Existing PostgreSQL roadmap | execution overlay, Gate A/B/C, deterministic roadmap guard |
| C1 — Transaction and schema evolution contract | verified | C0 | advisory migration lock, schema range, retry/side-effect contract |
| C2 — Outbox and side-effect delivery | verified | C1 | versioned envelope, ordering, inbox dedupe, replay, dead letters, side-effect receipts |
| C3 — Tenant integrity and security baseline | verified | C1 | composite tenant constraints, security policy state, adversarial cross-workspace tests |
| C4 — Coordinated PostgreSQL and BlobStore recovery | verified | C1, C3 | backup generation, blob manifest, checksum verification, deletion grace |
| C5 — Current-topology distributed correctness | verified | C1, C2, C4 | gateway/worker registry, leases, draining, stale-node recovery, failure evidence |
| C6 — Cutover and rollback state machine | verified | C4, C5 | guarded authority states, verified-backup activation, write and destructive acknowledgements |
| C7 — Data lifecycle, capacity, and maintenance | verified | C2, C4 | retention policy, bounded cleanup, capacity diagnostics, payload ceiling |
| C8 — Final integration and completion evidence | in_progress | C0–C7 | final exact-head matrix and evidence reconciliation |

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
- cutover state `postgresql_activated_frozen`;
- deterministic smoke checks passed;
- operator acknowledgement that legacy rollback becomes lossy after PostgreSQL accepts new writes.

### Gate C — Centralization complete

Requires:

- PostgreSQL authority stabilized after writes reopen;
- no runtime SQLite or mutable JSON authority paths;
- C7 lifecycle controls active;
- full exact-head provider-free verification green;
- local provider-backed acceptance recorded separately from GitHub Actions;
- this status table and linked evidence reconciled with repository state.

## Corrective phase specifications

### C0 — Roadmap Governance and Gate Reordering

Maintain phase status, dependencies, evidence, Gate A/B/C, linked architecture documents, and a deterministic CI guard. Operational recovery, current-topology correctness, and security are pre-cutover requirements. Future Redis, remote workers, cloud hosting, and multiplayer remain outside this corrective critical path.

### C1 — Transaction and Schema Evolution Contract

One shared policy covers migration advisory locking, application/schema compatibility, expand-and-contract evolution, bounded transaction retries, lock/statement timeouts, stale-revision recomputation, and prohibition of model, network, or slow BlobStore calls inside authoritative transactions.

### C2 — Complete Outbox and Side-Effect Delivery

Outbox events have unique identities, schema versions, correlation/causation, ordering sequence, durable leases, consumer inbox deduplication, explicit replay, poison-event quarantine, and durable side-effect idempotency receipts.

### C3 — Tenant Integrity and Security Baseline

Workspace-scoped composite foreign keys prevent cross-tenant references. PostgreSQL stores a least-privilege role policy and an explicit local-only RLS deferral that must be revisited before authenticated remote or shared-host deployment.

### C4 — Coordinated PostgreSQL and BlobStore Recovery

Backup generations capture software/schema revision, active blob authority, checksums, sizes, retention, encryption requirement, RPO, and RTO. Verification fails on missing or changed files and protects manifested assets from premature deletion.

### C5 — Pre-Cutover Current-Topology Correctness

PostgreSQL coordinates multiple gateways, workers, and event consumers using durable node identity, heartbeat, leases, draining, and stale-node reclamation. Existing duplicate request, job lease, RPG revision, outbox, side-effect, BlobStore, and restart tests cover authoritative effects without Redis.

### C6 — Cutover and Rollback State Machine

```text
legacy_preflight
imported_unverified
imported_verified
postgresql_activated_frozen
postgresql_open_for_writes
postgresql_stabilized
rollback_recorded
```

Before writes reopen, matching legacy backup may remain a lossless rollback target. After PostgreSQL accepts writes, normal recovery is forward repair or coordinated PostgreSQL-plus-BlobStore restore. Returning to legacy authority requires explicit destructive acknowledgement and never happens automatically.

### C7 — Data Lifecycle, Capacity, and Maintenance

Retention covers terminal outbox/inbox records, resolved dead letters, job and audit history, runtime evidence, RPG ledgers, snapshots, reports, exports, soft deletion, and sessions. Cleanup is bounded and audited. Capacity policy includes payload ceilings, disk warning/hard-stop thresholds, and measured maintenance/partitioning decisions.

### C8 — Final Integration and Completion Evidence

The final exact-head provider-free matrix covers PostgreSQL persistence and migrations, schema compatibility and locking, tenant isolation, coordinated recovery, outbox replay/deduplication, duplicate requests, stale revisions, jobs and leases, current-topology recovery, lifecycle cleanup, SQLite/mutable-authority retirement, deterministic RPG regression, web checks, and continuous 1,000-turn endurance.

Local provider-backed quality and latency acceptance remains explicit operator evidence and is not added to GitHub Actions.

## Linked operational documents

- `docs/CENTRALIZED_POSTGRESQL_ARCHITECTURE_ROADMAP.md`
- `docs/architecture/ADR-0001-centralized-postgresql-authority.md`
- `docs/architecture/PERSISTENCE_INVENTORY.md`
- `docs/architecture/LOCAL_POSTGRESQL_OPERATIONS.md`
- `docs/architecture/POSTGRESQL_CUTOVER_RUNBOOK.md`
- `docs/architecture/POSTGRESQL_RUNTIME_RETIREMENT.md`
- `docs/architecture/POSTGRESQL_TRANSACTION_SCHEMA_CONTRACT.md`
- `docs/architecture/POSTGRESQL_OUTBOX_DELIVERY_CONTRACT.md`
- `docs/architecture/POSTGRESQL_COORDINATED_RECOVERY.md`
- `docs/architecture/POSTGRESQL_CURRENT_TOPOLOGY_CORRECTNESS.md`
- `docs/architecture/POSTGRESQL_CUTOVER_STATE_MACHINE.md`
- `docs/architecture/POSTGRESQL_DATA_LIFECYCLE_CAPACITY.md`
- `docs/architecture/POSTGRESQL_COMPLETION_EVIDENCE.md`

## Pull request discipline

Each corrective phase is committed as a narrow, auditable slice on the execution branch. After each phase head is pushed, required GitHub Actions must complete. Failures are patched on the same branch before the next phase starts. Live model providers, API keys, and local model servers remain outside GitHub Actions.