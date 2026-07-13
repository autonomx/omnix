# PostgreSQL and BlobStore Coordinated Recovery

A PostgreSQL dump alone is not an Omnix backup. A verified generation covers structured PostgreSQL authority and every BlobStore object referenced by the captured asset manifest.

## Required workflow

1. Create a generation with the exact software revision, current schema, live BlobStore root, retention, RPO, RTO, encryption decision, and operator note.
2. Capture the active manifest. This extends `deletion_not_before` for manifested assets.
3. Copy only manifested blobs into an empty generation-specific backup root.
4. Run `pg_dump` explicitly and inspect its exit result.
5. Record the credential-free dump reference.
6. Restore the dump into an empty disposable database.
7. Restore the blob backup into an empty disposable BlobStore root.
8. Against the disposable database, run migration verification and deterministic smoke checks.
9. Return to the real database and verify the restored BlobStore by key, size, and SHA-256 while attesting the database/migration/smoke results.

Example command surface:

```powershell
python -m app.persistence recovery create-generation `
  --software-revision "<git-sha>" `
  --schema-version "<current-schema>" `
  --blob-root "<live-blob-root>" `
  --retention-days 30 --rpo-seconds 86400 --rto-seconds 3600 `
  --encryption-required `
  --operator-note "Post-import coordinated recovery rehearsal"

python -m app.persistence recovery capture-manifest `
  --backup-generation-id "<generation-id>"

python -m app.persistence recovery copy-blobs `
  --backup-generation-id "<generation-id>" `
  --source-blob-root "<live-blob-root>" `
  --destination-blob-root "<empty-generation-backup-root>"

python -m app.persistence backup "<dump-path>"

python -m app.persistence recovery record-database-backup `
  --backup-generation-id "<generation-id>" `
  --postgresql-dump-reference "<dump-path-without-credentials>"
```

After restoring and checking both authorities, return `OMNIX_DATABASE_URL` to the real Omnix database and run:

```powershell
python -m app.persistence recovery verify-blobs `
  --backup-generation-id "<generation-id>" `
  --blob-root "<empty-restored-blob-root>" `
  --database-restore-verified `
  --migrations-verified `
  --smoke-checks-verified

python -m app.persistence recovery status `
  --backup-generation-id "<generation-id>"
```

Verification against the original live BlobStore is rejected. Missing, size-mismatched, or checksum-mismatched blobs fail the generation. Unexpected restored files are reported separately. Dump references containing credentials are rejected. A failed database restore, migration verification, or deterministic smoke run cannot produce a verified generation.
