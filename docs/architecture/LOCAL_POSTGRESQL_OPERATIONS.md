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

## Protected Windows startup credential

For the normal `start_all.bat` path, provision a current-user Windows DPAPI credential from the already configured PostgreSQL container:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/manage_postgresql_credential.ps1 `
  -Action provision-from-container

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/manage_postgresql_credential.ps1 `
  -Action status
```

The protected value is written outside the repository under
`%LOCALAPPDATA%\Omnix\secrets\postgresql-url.dpapi`. Its directory ACL is restricted to the current Windows user and `SYSTEM`, and the encrypted value can only be decrypted by the Windows user that provisioned it. The scripts never print the database password or unredacted URL.

`start_all.bat` now performs this sequence:

1. Verify Docker is available and start the existing `omnix-postgres` container when needed.
2. Wait for the container health check.
3. Use an existing session-only `OMNIX_DATABASE_URL`, or decrypt the current-user DPAPI credential into the launcher process environment.
4. Run `python -m app.persistence health` before opening the launcher dashboard.
5. Auto-start launcher-managed services. Each child inherits the same database environment without placing it in command arguments or launcher logs.
6. Stop launcher-managed child processes when the launcher shuts down.

The session environment intentionally takes precedence over the DPAPI credential for recovery rehearsals and disposable test databases. If Docker, the provisioned container, the protected credential, or PostgreSQL health is unavailable, startup fails closed before application services launch.

For a content-free credential and database startup rehearsal without opening the launcher or application services:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/manage_postgresql_credential.ps1 `
  -Action launch -BatchPath .\start_all.bat -CheckOnly
```

Set `OMNIX_LAUNCHER_OPEN_BROWSER=0` before running `start_all.bat` when starting it under a background supervisor or during an unattended restart rehearsal.

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
