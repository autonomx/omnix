# PostgreSQL migration policy

Schema mutation is a release operation, never request-path work. Operators apply migrations with:

```bash
python -m app.persistence migrate
python -m app.persistence status --json
```

Docker Compose runs the one-shot `omnix-migrate` service before gateway services. The Windows launcher runs the same migration command before auto-starting the gateway cohort. Runtime readiness verifies compatibility and does not apply migrations.

## Expand / data / contract

Every new migration starts with:

```sql
-- omnix-migration: phase=expand transactional=true
```

Valid phases are `expand`, `data`, and `contract`. Files without a header are treated as legacy `contract transactional=true` migrations.

Use the compatibility sequence:

1. **Expand**: add nullable columns/tables/index support that both old and new app versions tolerate.
2. Dual-write where required.
3. **Data**: backfill in an idempotent migration.
4. Switch reads in the application after the backfill is deployed.
5. **Contract**: remove old columns or behavior only in a later release.

The application declares `SCHEMA_MIN_CONTRACT` and `SCHEMA_KNOWN`. Unknown newer expand/data migrations are tolerated; unknown contract migrations are rejected because they can mean the database has removed behavior required by the running app.

## Where migrations live

Migrations are read from exactly three places (ADR-0016, PA-2.3), found by convention so the persistence kernel never reads the feature catalog:

1. the kernel folder `src/app/persistence/migrations/`, for kernel tables and the historical migrations that touch several owners;
2. a `migrations/` folder next to a module's `feature.py` (for example `src/app/trading/migrations/`), for the tables that module owns;
3. `src/app/persistence/retired/<package>/migrations/`, the tombstone of a retired module.

Every module's migrations run whether or not its feature is enabled: the schema is a release artifact, not a feature flag. A `.sql` file in any other `migrations/` folder is an architecture-lint error (AL014), so a save-format folder such as `src/app/rpg/persistence/migrations/` can never become schema by accident. A migration's version is its file stem, unique across all three places; moving a file between them is not a change. `SCHEMA_KNOWN` is the newest version found, never a hand-edited constant. Which module owns each table is recorded in `resources/architecture/historical-table-owners.json` (frozen) and derived for tables a module's own migrations create; AL016 rejects a migration that changes another module's table.

## Ordering

Canonical migration order is lexical filename order across all three places. The runner refuses to apply an unapplied lower-sorting migration after a higher version was already applied unless an operator explicitly passes `--allow-out-of-order`.

Transactional migrations run inside one database transaction. A migration marked `transactional=false` runs outside a transaction and must contain exactly one SQL statement, which is appropriate for operations such as `CREATE INDEX CONCURRENTLY`.

## CI checks

`scripts/architecture_lint.py` (rule AL014) runs in CI on every push and pull request. Migrations that already exist at the comparison base are frozen; every new migration must:

- start with the `-- omnix-migration: phase=... transactional=...` header;
- not drop a column or table in an `expand` migration (do that in a later `contract` migration);
- build indexes on large tables with `CREATE INDEX CONCURRENTLY` in a `transactional=false` migration, so writes continue during the build. The large tables are `omnix_agent_run_events`, `omnix_assets`, `omnix_audit_events`, `omnix_chat_messages`, `omnix_job_events`, `omnix_job_logs`, `omnix_jobs`, `omnix_memory_records`, `omnix_module_records`, `omnix_outbox_events` and `omnix_trading_strategy_events` (`LARGE_TABLES` in the lint script).

An interrupted concurrent build leaves an INVALID index; drop it with `DROP INDEX CONCURRENTLY` and run the migration again.

## Database roles

`OMNIX_DATABASE_URL` is the runtime DML role. `OMNIX_MIGRATION_DATABASE_URL` is the DDL/migration role. Local single-role development remains supported. Production deployments can require separation with `OMNIX_REQUIRE_ROLE_SEPARATION=true`.
