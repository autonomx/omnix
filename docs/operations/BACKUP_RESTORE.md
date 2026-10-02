# Backup, restore and disaster recovery

## Targets

| | Local install | Hosted install |
|---|---|---|
| Recovery point objective (RPO): data you can lose | 24 hours (one backup a day) | 1 hour (hourly backups or WAL archiving) |
| Recovery time objective (RTO): time to serve again | 1 hour | 1 hour |

Measured on 2026-10-02 at benchmark volume (100,000 jobs, 303,000 job events,
100,000 assets, 10,000 chat sessions, 1,000,000 chat messages; a 65 MB dump):
the backup took 6 s and the full restore rehearsal 42 s
(`docs/measurements/restore-rehearsal-2026-10-02.json`). Restoring the
database is a small part of the hour; most of it is noticing, deciding and
switching over.

## Back up

    python scripts/backup_omnix.py --output-dir <backup directory>

It runs as the migration role (`OMNIX_MIGRATION_DATABASE_URL`, else
`OMNIX_DATABASE_URL`), which can read every workspace, and writes:

| File | Content |
|---|---|
| `database.dump` | `pg_dump --format=custom` (through `python -m app.persistence backup`). |
| `blobs.tar.gz` | The local blob root (`OMNIX_BLOB_ROOT`, default `resources/data/blobs`). With `OMNIX_BLOB_BACKEND=s3` nothing is copied: enable versioning on the bucket and restore objects from their versions at the backup time. |
| `manifest.json` | Time, software revision (`OMNIX_SOFTWARE_REVISION`), schema version, row counts of the main tables, each file's SHA-256, and the hashes of a sample of blobs. |

`pg_dump` must be the server's major version or newer. Schedule the script
daily (local) with the operating system's scheduler, and copy the directory
off the machine: a backup on the same disk does not survive the disk.
Backups contain every workspace's data and are not encrypted by the script;
store them encrypted.

## Rehearse a restore

    python scripts/restore_rehearsal.py --backup-dir <backup directory> \
        --target-url postgresql://<user>@<host>/<name with test, bench or rehearsal> \
        --blob-root <empty directory> --output restore-rehearsal.json

The target must be a disposable database: the script refuses a name without
`test`, `bench` or `rehearsal`, and overwrites it. It checks the files against
the manifest, restores the dump, applies migrations if the backup is older,
runs `python -m app.persistence verify`, compares row counts with the
manifest, extracts the blobs and checks the sampled hashes. The nightly
`restore-rehearsal` job runs it on a generated dataset.

Rehearse with real data before you need it: restore last night's backup into
a disposable database on another machine at least once a quarter, and after
every major upgrade.

## Restore for real

Follow the [restore runbook](runbooks/restore.md): restore into a new
database, verify it, then stop every Omnix process and switch
`OMNIX_DATABASE_URL` (and the blob root) over. Do not restore over the active
database without a fresh backup of it.

For coordinated recovery generations (database and blob store captured as one
recovery point with a deletion grace period), see
`python -m app.persistence recovery --help`.
