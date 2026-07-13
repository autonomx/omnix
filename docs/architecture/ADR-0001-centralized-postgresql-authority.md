# ADR-0001: Centralized PostgreSQL Authority

- **Status:** Accepted
- **Date:** 2026-07-12
- **Decision owners:** Omnix maintainers
- **Related roadmap:** `docs/CENTRALIZED_POSTGRESQL_ARCHITECTURE_ROADMAP.md`

## Context

Omnix currently persists structured state through multiple SQLite databases, JSON files, JSONL logs, and manifest files. The application is already multi-process: the gateway, background workers, local model services, event delivery, and RPG foreground execution can overlap even on one workstation. Separate persistence systems prevent one atomic transaction from covering related domain changes and create different concurrency, migration, backup, and recovery rules per subsystem.

Offline operation does not require SQLite. PostgreSQL can run on the same workstation and remain fully private, self-hosted, and disconnected from the internet.

## Decision

PostgreSQL will become the sole authoritative database for structured Omnix domain state. Initial deployment is local PostgreSQL on the operator workstation. A future hosted deployment will use the same domain and transaction model.

Large binary artifacts remain outside PostgreSQL behind a provider-neutral `BlobStore`. PostgreSQL stores their ownership, checksums, lifecycle state, and storage references.

SQLite will be removed from normal runtime operation after migration. JSON and JSONL will remain valid for exports, fixtures, reports, migration inputs, and diagnostics, but not as mutable authoritative application state.

Redis may be introduced only after PostgreSQL-backed correctness and profiling are established. Redis is reconstructible and non-authoritative.

## Required invariants

1. Related authoritative writes share one PostgreSQL transaction.
2. Mutable aggregates use monotonic revisions or equivalent compare-and-swap protection.
3. Retried commands use durable idempotency keys and return an existing committed result.
4. Every user- or workspace-owned record has a trusted tenant boundary.
5. Domain changes and outbox events commit in the same transaction.
6. Redis loss may reduce performance or remove ephemeral presence, but may not lose or corrupt durable state.
7. GitHub Actions remain provider-free; live LLM acceptance stays local and explicitly enabled.
8. PostgreSQL may run entirely on localhost, preserving offline operation and local model execution.

## Initial RPG persistence decision

The first PostgreSQL RPG model uses:

- authoritative normalized campaign state in JSONB;
- a monotonic campaign revision;
- state hashes before and after each turn;
- a unique submission ID per campaign;
- an append-only turn ledger containing canonical effects;
- periodic snapshots;
- a transactional outbox.

Full replay-from-genesis event sourcing is not required for migration or cutover.

## Consequences

### Positive

- one source of structured truth;
- atomic cross-domain operations;
- safe multi-process access;
- one backup and restore model;
- a direct path to multiple gateways, remote workers, and hosted deployment;
- measured PostgreSQL and Redis optimization rather than fragmented local stores.

### Costs

- PostgreSQL becomes a required local service;
- installation, health checks, migrations, backups, and restore tooling become product responsibilities;
- existing SQLite and JSON data require verified importers;
- repository contracts and service transaction boundaries require redesign.

## Rejected alternatives

### Permanent SQLite and PostgreSQL parity

Rejected because it doubles persistence implementations and contract testing, preserves incompatible concurrency assumptions, and limits transactional features to the least capable backend.

### Redis as authoritative state or job truth

Rejected because cache loss or eviction must not determine committed domain outcomes.

### Full event sourcing before centralization

Rejected because revisioned JSONB plus an idempotent turn ledger supplies safe concurrency and auditing without blocking the migration on a complete simulation replay redesign.
