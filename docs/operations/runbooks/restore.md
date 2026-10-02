# Restore

Test every restore against an isolated database first; never restore over the
active database without a fresh backup of it.

## Restore a database backup

1. Create an empty database, or use `--clean` on a disposable one.
2. With `OMNIX_MIGRATION_DATABASE_URL` pointing at it (the migration role,
   which can read every workspace):
   `python -m app.persistence restore <file>` (add `--clean` to drop restored
   objects first).
3. `python -m app.persistence verify`: healthy and no migration drift. Run
   `python -m app.persistence migrate` if the backup predates the current
   revision.
4. Blobs: the database references blobs by key. With the local backend,
   restore the blob root from the same point in time; with S3, use bucket
   versioning. `python -m app.persistence recovery verify-blobs` checks a
   recovery generation's blobs.

## Switch over

1. Stop every Omnix process.
2. Point `OMNIX_DATABASE_URL` (and the migration URL) at the restored database.
3. Start the processes; check `/ready` and sign in.

## Verification

- `/ready` returns 200; recent sessions, jobs and assets open; their blobs
  load (`/api/assets/{id}/file`).
- Record the restore (what, from when, data lost since the backup) in an
  incident record ([OPERATIONS: Incident record template](../../OPERATIONS.md#incident-record-template)).
