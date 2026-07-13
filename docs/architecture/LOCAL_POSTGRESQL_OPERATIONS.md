# Local PostgreSQL Operations

Omnix uses PostgreSQL for authoritative structured data even when all services run on one offline workstation. Set an operator-owned password and do not place it in reports, shell transcripts, or Git.

## Start and verify

```powershell
$env:OMNIX_POSTGRES_PASSWORD = "<operator-owned-password>"
$env:OMNIX_DATABASE_URL = "postgresql://omnix:$env:OMNIX_POSTGRES_PASSWORD@127.0.0.1:5432/omnix"
$env:OMNIX_SOFTWARE_REVISION = (git rev-parse HEAD)
docker compose -f docker-compose.postgres.yml up -d
python -m app.persistence health
python -m app.persistence migrate
python -m app.persistence status
python -m app.persistence verify
```

`verify` requires healthy PostgreSQL, no checksum drift, and no pending migrations. SQLite URLs and silent fallback are rejected.

## Authority and recovery status

```powershell
python -m app.persistence cutover status
python -m app.persistence recovery status
```

All authority changes use `python -m app.persistence cutover ...`. The legacy import script only performs preflight and import; its old `status`, `activate`, and `record-rollback` commands fail closed.

## Backup and restore

Install `pg_dump` and `pg_restore` and keep backup paths credential-free:

```powershell
python -m app.persistence backup "resources/data/backups/omnix.dump"
```

The CLI supplies database passwords to PostgreSQL tools through their environment, not process arguments, and redacts credential-bearing operator output.

Restore into an empty disposable database first:

```powershell
$realDatabaseUrl = $env:OMNIX_DATABASE_URL
$env:OMNIX_DATABASE_URL = "postgresql://omnix:<password>@127.0.0.1:5432/omnix_restore_test"
python -m app.persistence restore "resources/data/backups/omnix.dump" --clean
python -m app.persistence verify
# Run deterministic restored-database smoke checks here.
$env:OMNIX_DATABASE_URL = $realDatabaseUrl
```

Do not declare a generation verified until the clean database restore and clean BlobStore restore both pass.

## Runtime authority barrier

Normal gateway/worker startup succeeds only in `postgresql_open_for_writes` or `postgresql_stabilized`. `postgresql_activated_frozen` is for CLI/database inspection; normal runtime mutations remain blocked. `rollback_recorded` also blocks runtime mutation until deliberate repair or restore.

## Stop

```powershell
docker compose -f docker-compose.postgres.yml down
```

Do not use `down -v` during normal operations; it destroys the PostgreSQL volume.
