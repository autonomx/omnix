# PostgreSQL Persistence Specification

This document is normative for Omnix persistence work and supplements `SPEC.md` during the centralized-database migration.

## Product posture

Omnix is self-hostable and offline-capable. Its authoritative PostgreSQL service may run entirely on the same local machine as the gateway, workers, and local model services. Local operation does not imply SQLite authority.

## Sources of truth

- **PostgreSQL:** all authoritative structured domain data.
- **BlobStore:** large binary and immutable artifact bytes.
- **SecretStore:** credential and token bytes.
- **Redis:** optional reconstructible cache, presence, fan-out, and measured coordination only.
- **JSON/JSONL:** exports, reports, fixtures, migration input, and diagnostics only after cutover.
- **SQLite:** legacy migration input only after Phase 9.

## Application boundary

Routes call application services. Application services open a Unit of Work. Repositories within that Unit of Work share one PostgreSQL transaction. Domain code does not create database connections, write mutable JSON manifests, or depend on a concrete database adapter.

```text
route
  -> application service
     -> TenantContext
     -> UnitOfWork
        -> PostgreSQL repositories
        -> outbox repository
     -> commit
  -> event publisher / response
```

## Required database behavior

- UTC timestamps use timezone-aware PostgreSQL values.
- IDs are stable strings or UUIDs with explicit external representations.
- every user-owned aggregate includes `workspace_id` and, where applicable, `owner_user_id`;
- mutable aggregates have monotonic revisions;
- idempotent operations have database unique constraints;
- pagination is cursor-based for unbounded collections;
- destructive deletion is explicit and audited;
- large payloads are bounded and moved to BlobStore when appropriate;
- domain writes and outbox events are atomic;
- retries handle only classified transient errors;
- stale writes return conflicts rather than overwriting newer state.

## PostgreSQL availability

Normal startup fails clearly when the required database is unavailable or behind the required migration revision. Omnix must never silently fall back to SQLite or mutable JSON authority.

## Local deployment

The supported local deployment provides:

- a localhost PostgreSQL service;
- a persistent data volume;
- health and readiness checks;
- migration commands;
- backup and restore commands;
- safe local credentials configurable by the operator;
- no required internet connection;
- no Redis requirement through Phase 12.

## Verification

GitHub Actions use an ephemeral PostgreSQL service and deterministic/provider-free tests. Live LLM, TTS, STT, and image acceptance remains explicitly local and is not required by CI.

## Compatibility period

Legacy SQLite and JSON stores may be read by idempotent importers until cutover. They must not become permanent alternative backends. After a domain cutover, legacy writes are disabled. After Phase 9, normal runtime code contains no active SQLite connection path.
