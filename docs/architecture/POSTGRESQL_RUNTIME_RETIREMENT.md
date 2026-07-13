# PostgreSQL Runtime Retirement

Phase 9 retires SQLite, JSONL, and mutable JSON manifests as normal Omnix runtime authorities.

## Production behavior

Normal processes use:

```text
OMNIX_PERSISTENCE_MODE=postgresql
```

This is the default when the variable is omitted.

At Python process startup, Omnix:

1. verifies PostgreSQL health;
2. applies and verifies schema migrations;
3. activates an empty fresh installation directly into PostgreSQL authority;
4. requires an imported installation to have a completed, verified Phase 8 cutover;
5. installs PostgreSQL-backed compatibility adapters for chat, characters, memory, jobs, shared assets, RPG sessions, and interaction records;
6. replaces `sqlite3.connect` with a fail-closed retirement sentinel;
7. installs an import barrier for retired mutable JSON/manifest stores.

There is no automatic SQLite fallback.

## Fresh installation

A database with no legacy import runs and no domain rows is treated as a new installation. Its cutover record is activated as PostgreSQL without requiring an empty migration bundle.

If domain data or an import run exists, activation is not automatic. The Phase 8 importer and cutover command must be used.

## Legacy access

Legacy persistence is allowed only for isolated tests and one-shot migration tools.

### Tests

```text
OMNIX_PERSISTENCE_MODE=legacy_test
OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE=1
```

`legacy_test` is rejected outside pytest or CI execution.

### Import tools

```text
OMNIX_PERSISTENCE_MODE=legacy_import
OMNIX_ALLOW_LEGACY_IMPORT=1
```

The supplied export/import scripts select this mode automatically.

Neither mode is a supported production deployment.

## Compatibility adapters

The current API and service contracts remain stable during cutover:

- `ChatStore` receives a PostgreSQL Chat repository adapter.
- `MemoryService` receives a PostgreSQL memory repository adapter.
- `CharacterService` receives a PostgreSQL character repository adapter.
- the default JobStore uses the PostgreSQL job ledger and lease system.
- shared asset metadata uses PostgreSQL and BlobStore.
- RPG save/load/archive and interaction-log operations use PostgreSQL.

These adapters exist to keep feature routes operational while removing the legacy source of truth. New code should depend directly on semantic repositories and the Unit of Work instead of adding more compatibility behavior.

## Mutable JSON retirement

The following modules are treated as retired mutable authorities in production:

- assist-core policy store;
- assistant-tools configuration store;
- chat prompt store;
- live-chat evaluation store;
- image asset manifest;
- research source store;
- RPG narrative persistence file;
- NPC evolution profile store.

When imported in production mode, their store/repository classes and mutating functions are replaced by fail-closed retirement sentinels. Their data must be migrated to the matching Phase 3–7 PostgreSQL repository or treated as export-only output.

## SQLite code retained temporarily

SQLite implementation files may remain temporarily as frozen legacy adapters so existing deterministic tests and the one-shot export process can read old installations. They are not selected in production mode and cannot open a SQLite connection after the runtime bootstrap installs.

The supported migration window may remove these files entirely after operators have completed cutover. Their presence does not make SQLite a supported backend.

## Diagnostics

PostgreSQL runtime readiness includes:

- database health;
- migration drift and pending revision checks;
- cutover mode;
- runtime schema version;
- the `sqlite_runtime_retired` marker.

A failure is surfaced as a startup/readiness error. It is not hidden by switching persistence backends.

## Acceptance criteria

Phase 9 is complete when:

1. a normal subprocess starts with PostgreSQL adapters installed;
2. a fresh empty database activates PostgreSQL authority;
3. imported installations require a verified cutover;
4. SQLite connections fail in normal runtime;
5. chat, character, memory, job, asset, and RPG compatibility operations persist successfully through PostgreSQL;
6. mutable JSON authority modules are blocked;
7. provider-free GitHub Actions pass on the exact implementation head;
8. live model/provider checks remain local operator evidence only.
