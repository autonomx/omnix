# PostgreSQL Migration and Cutover Runbook

This runbook moves an existing local Omnix installation from legacy SQLite, JSON, JSONL, and manifest-backed authority to PostgreSQL and local BlobStore authority.

The migration is designed for a local maintenance window. Do not keep legacy and PostgreSQL writes active indefinitely.

## Preconditions

- The implementation branch or release containing migrations through `0008_legacy_cutover.sql` is installed.
- PostgreSQL is healthy and reachable through `OMNIX_DATABASE_URL`.
- Omnix gateways, workers, idle RPG ticks, and generation services that mutate persistence are stopped.
- PostgreSQL client tools are installed for backup and restore.
- The operator has enough free disk space for:
  - legacy backups;
  - the migration bundle;
  - copied BlobStore artifacts;
  - a PostgreSQL backup after import.

## 1. Record the exact software revision

```powershell
git status --short
git rev-parse HEAD
```

The working tree should be clean. Save the exact commit SHA in the migration notes.

## 2. Back up legacy data

Copy all applicable legacy sources into a dated, read-only backup directory:

- chat SQLite database;
- assistant-memory SQLite database;
- character SQLite database;
- jobs SQLite database;
- asset and image manifests;
- RPG session JSON files and interaction JSONL files;
- generated assets referenced by manifests;
- provider and settings files;
- prompt, research, report, and module-specific stores.

Calculate a directory hash or file manifest for the backup. Do not delete or modify the original sources yet.

## 3. Start and prepare PostgreSQL

```powershell
docker compose -f docker-compose.postgres.yml up -d
python -m app.persistence migrate
python -m app.persistence verify
```

Create a pre-import PostgreSQL backup when the database is not empty:

```powershell
python -m app.persistence backup resources/data/backups/before-legacy-import.dump
```

## 4. Export a canonical migration bundle

Example:

```powershell
$env:PYTHONPATH = "src"
python scripts/export_legacy_persistence_bundle.py `
  --source-id "local-installation-2026-07-12" `
  --output "resources/data/migration/legacy-bundle.json" `
  --asset-manifest "resources/data/assets/manifest.json" `
  --character-db "resources/data/omnix_characters.sqlite3" `
  --memory-db "resources/data/omnix_assistant_memory.sqlite3" `
  --chat-db "resources/data/omnix_chat.sqlite3" `
  --jobs-db "resources/data/omnix_jobs.sqlite" `
  --rpg-sessions-dir "resources/data/rpg_sessions"
```

Arguments may be omitted when a source does not exist. The exporter reads legacy SQLite in a one-shot tool; normal Omnix runtime does not.

The report records:

- source ID;
- canonical source hash;
- entity counts;
- validation errors;
- output path.

The bundle must not contain API keys, OAuth tokens, passwords, or other secret values. Only secret references may be migrated.

## 5. Run preflight and dry-run import

```powershell
python scripts/import_legacy_persistence_bundle.py preflight `
  "resources/data/migration/legacy-bundle.json"

python scripts/import_legacy_persistence_bundle.py import `
  "resources/data/migration/legacy-bundle.json" `
  --dry-run `
  --blob-root "resources/data/blobs"
```

Both commands must return `ok: true`.

Resolve duplicate IDs, unsupported records, missing files, source-hash mismatch, and secret-bearing values before continuing.

## 6. Import

```powershell
python scripts/import_legacy_persistence_bundle.py import `
  "resources/data/migration/legacy-bundle.json" `
  --blob-root "resources/data/blobs"
```

The importer is resumable:

- each item has a source hash;
- completed items are reused;
- changed source data is rejected;
- failed items are recorded with bounded error details;
- a completed source ID cannot be silently replaced by different content.

A clean result requires:

```text
ok = true
run.status = completed
verification.ok = true
verification.mismatches = {}
verification.failed_counts = {}
```

Save the import run ID.

## 7. Inspect and verify

Check cutover status:

```powershell
python scripts/import_legacy_persistence_bundle.py status
```

Before activation, it should remain `legacy_preflight`.

Verify at minimum:

- user/workspace bootstrap exists;
- character versions and active versions match;
- memory owner scopes and revisions match;
- chat message order and counts match;
- completed and failed job states are preserved;
- RPG campaign revision and state hashes match;
- referenced artifact files exist and pass checksum verification;
- provider configs contain no credential values;
- report and asset references resolve;
- imported counts equal discovered counts.

## 8. Back up the imported PostgreSQL database

```powershell
python -m app.persistence backup `
  "resources/data/backups/after-legacy-import-before-cutover.dump"
```

Restore that backup into a disposable database and run:

```powershell
python -m app.persistence verify
```

Do not activate cutover until a restore rehearsal passes.

## 9. Activate PostgreSQL authority

```powershell
python scripts/import_legacy_persistence_bundle.py activate `
  "<legacy-import-run-id>" `
  --note "Legacy backup and PostgreSQL restore verified"
```

Activation is rejected unless the import run is completed and verification is clean.

After activation, legacy sources are read-only backups. Omnix must not silently fall back to them.

## 10. Restart and acceptance checks

Start Omnix with the PostgreSQL configuration and run deterministic smoke checks for:

- chat create/read/message append;
- character read and version update;
- memory read and snapshot access;
- job create/claim/complete;
- asset metadata and blob read;
- RPG campaign load and one idempotent turn replay;
- diagnostics and migration status.

Run local provider-backed RPG acceptance separately when the configured local provider is available. It remains outside GitHub Actions.

## 11. Rollback rehearsal

A runtime failure after activation does not trigger automatic SQLite fallback.

Restore the pre-cutover application and legacy backup deliberately. Record the rollback in the PostgreSQL migration ledger:

```powershell
python scripts/import_legacy_persistence_bundle.py record-rollback `
  "<legacy-import-run-id>" `
  --reason "<bounded operator reason>"
```

Then restore either:

- the verified pre-import PostgreSQL backup; or
- the backed-up legacy installation and its matching software revision.

Do not mix post-cutover writes into the legacy source set.

## 12. Archive legacy sources

After sustained verification:

- mark the legacy backup directory read-only;
- retain its file-hash manifest;
- retain the canonical migration bundle and import report;
- retain the before/after PostgreSQL backups according to the backup policy;
- remove legacy files from normal runtime paths only during Phase 9 retirement.

## Success criteria

Cutover is complete when:

1. the import run is `completed`;
2. discovered and imported counts match;
3. no failed import items remain;
4. PostgreSQL backup and restore pass;
5. cutover mode is `postgresql`;
6. deterministic smoke checks pass;
7. no normal runtime write targets SQLite, JSONL, or mutable JSON manifests;
8. legacy data remains an immutable rollback archive only.
