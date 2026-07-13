# Local PostgreSQL Operations

Omnix uses PostgreSQL as its authoritative structured-data database even when every service runs on one offline workstation.

## Start

```powershell
$env:OMNIX_POSTGRES_PASSWORD = "choose-a-local-password"
docker compose -f docker-compose.postgres.yml up -d
$env:OMNIX_DATABASE_URL = "postgresql://omnix:$env:OMNIX_POSTGRES_PASSWORD@127.0.0.1:5432/omnix"
python -m app.persistence migrate
python -m app.persistence verify
```

The default development credentials are intentionally simple for localhost-only evaluation. Set an operator-owned password before retaining real data.

## Environment

```text
OMNIX_DATABASE_URL
OMNIX_DATABASE_POOL_MIN=1
OMNIX_DATABASE_POOL_MAX=10
OMNIX_DATABASE_CONNECT_TIMEOUT=5
OMNIX_DATABASE_STATEMENT_TIMEOUT=30000
OMNIX_DATABASE_APPLICATION_NAME=omnix
```

SQLite URLs are rejected. Omnix does not silently fall back when PostgreSQL is unavailable.

## Status and health

```powershell
python -m app.persistence health
python -m app.persistence status
python -m app.persistence verify
```

`verify` requires a healthy database, no migration checksum drift, and no pending migrations.

## Backup

Install PostgreSQL client tools so `pg_dump` and `pg_restore` are available.

```powershell
python -m app.persistence backup resources/data/backups/omnix.dump
```

Backups use PostgreSQL custom format without ownership or ACL records.

## Restore rehearsal

Restore into an empty disposable database first:

```powershell
$env:OMNIX_DATABASE_URL = "postgresql://omnix:<password>@127.0.0.1:5432/omnix_restore_test"
python -m app.persistence restore resources/data/backups/omnix.dump --clean
python -m app.persistence verify
```

Do not declare a backup strategy complete until a full restore has been verified.

## Stop

```powershell
docker compose -f docker-compose.postgres.yml down
```

The named volume remains. To remove all PostgreSQL data deliberately:

```powershell
docker compose -f docker-compose.postgres.yml down -v
```

This operation is destructive and must not be part of normal shutdown.

## Offline operation

The PostgreSQL container, gateway, workers, and local model services communicate over localhost. Internet access is not required after images and dependencies are installed.
