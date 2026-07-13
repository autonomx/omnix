# PostgreSQL Live Cutover Runbook

This runbook moves an existing local Omnix installation from legacy SQLite, JSON, JSONL, and mutable manifests to PostgreSQL and BlobStore authority. Merged code is not evidence that an installation has been cut over.

Do not begin against live data until the exact software revision containing the authoritative cutover CLI and runtime authority barrier is installed.

## 1. Discover and enter maintenance mode

Record the repository path, Python environment, PostgreSQL/Docker availability, PostgreSQL client tools, every legacy authority path, active BlobStore root, running application processes/ports, free disk space, and backup destination. Stop if any authority source is unidentified.

Stop gateways, workers, event consumers, idle RPG ticks, schedulers, and asset-generation processes. Confirm no process writes legacy files or PostgreSQL.

```powershell
$maintenanceStart = Get-Date -AsUTC
git status --short
git rev-parse HEAD
```

The worktree must be clean. Save the exact SHA as `<software-revision>`.

## 2. Back up legacy authority

Create a dated, read-only backup of every applicable source:

- chat, assistant-memory, character, and job SQLite databases;
- RPG session JSON and interaction JSONL;
- asset/image manifests and every referenced artifact;
- provider/settings references;
- prompt, research, report, and module stores.

Create a deterministic manifest containing relative path, byte size, and SHA-256. Do not alter originals. Record the manifest path and hash in the private operator report.

## 3. Prepare PostgreSQL

Set `PYTHONPATH=src`, `OMNIX_DATABASE_URL`, and `OMNIX_SOFTWARE_REVISION` without printing the password.

```powershell
docker compose -f docker-compose.postgres.yml up -d
python -m app.persistence health
python -m app.persistence migrate
python -m app.persistence status
python -m app.persistence verify
```

All must report `ok: true`. If the database is not empty, create and rehearse a pre-import backup first.

## 4. Export, preflight, and import

Use discovered paths rather than these placeholders:

```powershell
python scripts/export_legacy_persistence_bundle.py `
  --source-id "<unique-local-installation-id>" `
  --output "resources/data/migration/legacy-bundle.json" `
  --asset-manifest "<actual-manifest-path>" `
  --character-db "<actual-character-db>" `
  --memory-db "<actual-memory-db>" `
  --chat-db "<actual-chat-db>" `
  --jobs-db "<actual-jobs-db>" `
  --rpg-sessions-dir "<actual-rpg-session-directory>"

python scripts/import_legacy_persistence_bundle.py preflight `
  "resources/data/migration/legacy-bundle.json"

python scripts/import_legacy_persistence_bundle.py import `
  "resources/data/migration/legacy-bundle.json" `
  --dry-run `
  --blob-root "<live-blob-root>"

python scripts/import_legacy_persistence_bundle.py import `
  "resources/data/migration/legacy-bundle.json" `
  --blob-root "<live-blob-root>"
```

Stop if secrets, missing source hashes/files, unsupported records, omitted authority, or validation errors appear. A clean import requires `ok = true`, `run.status = completed`, `verification.ok = true`, empty mismatches, and empty failed counts. Record the import run ID and bundle hash.

## 5. Record import verification states

```powershell
python -m app.persistence cutover mark-imported-unverified `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --legacy-import-run-id "<import-run-id>" `
  --operator-note "Canonical import completed; detailed checks begin"
```

Verify counts, revisions, ordering, state hashes, artifact checksums, and absence of credential values. Then run:

```powershell
python -m app.persistence cutover mark-imported-verified `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --legacy-import-run-id "<import-run-id>" `
  --operator-note "Detailed import checks passed"
```

## 6. Create a coordinated recovery generation

```powershell
python -m app.persistence recovery create-generation `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --blob-root "<live-blob-root>" `
  --retention-days 30 --rpo-seconds 86400 --rto-seconds 3600 `
  --encryption-required `
  --operator-note "Post-import pre-activation generation"
```

Record the returned generation ID, then:

```powershell
python -m app.persistence recovery capture-manifest `
  --backup-generation-id "<generation-id>"

python -m app.persistence recovery copy-blobs `
  --backup-generation-id "<generation-id>" `
  --source-blob-root "<live-blob-root>" `
  --destination-blob-root "<empty-generation-blob-backup-root>"

python -m app.persistence backup "<generation-dump-path>"

python -m app.persistence recovery record-database-backup `
  --backup-generation-id "<generation-id>" `
  --postgresql-dump-reference "<generation-dump-path>"
```

The dump reference must not contain credentials.

## 7. Rehearse clean restoration

Create an empty disposable PostgreSQL database and an empty disposable BlobStore directory. Save the real URL without printing it, switch to the disposable database, restore, and verify:

```powershell
$realDatabaseUrl = $env:OMNIX_DATABASE_URL
$env:OMNIX_DATABASE_URL = "postgresql://omnix:<password>@127.0.0.1:5432/omnix_restore_test"
python -m app.persistence restore "<generation-dump-path>" --clean
python -m app.persistence verify
# Run deterministic restored-database smoke checks.
```

Restore/copy the generation BlobStore backup into the empty disposable BlobStore root. Do not verify the original live root.

Return to the real database, then record combined evidence:

```powershell
$env:OMNIX_DATABASE_URL = $realDatabaseUrl
python -m app.persistence recovery verify-blobs `
  --backup-generation-id "<generation-id>" `
  --blob-root "<empty-restored-blob-root>" `
  --database-restore-verified `
  --migrations-verified `
  --smoke-checks-verified

python -m app.persistence recovery status `
  --backup-generation-id "<generation-id>"
```

Require zero missing/mismatched blobs, matching manifest hash/count/bytes, healthy restored database, zero migration drift, and passing deterministic smoke checks.

## 8. Activate PostgreSQL frozen

```powershell
python -m app.persistence cutover activate-frozen `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --legacy-import-run-id "<import-run-id>" `
  --backup-generation-id "<generation-id>" `
  --operator-note "Verified import and coordinated restore rehearsal"
```

At `postgresql_activated_frozen`, PostgreSQL is selected authority but normal runtime start and mutations are blocked. Use CLI/database read-only inspection for users/workspaces, characters, memory, chats, jobs, assets/blobs, RPG revisions/state hashes, provider references, diagnostics, and migrations. Legacy files remain immutable and there is no fallback.

## 9. Open writes

Immediately before the irreversible gate, run `python -m app.persistence cutover status` and record the import run, generation, dump/blob backup locations, restore result, and current state. Explicitly acknowledge that legacy rollback cannot preserve new PostgreSQL writes.

```powershell
python -m app.persistence cutover open-writes `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --operator-note "Operator accepts that legacy rollback is no longer lossless" `
  --write-reopen-acknowledged
```

Start normal gateways, workers, consumers, and RPG runtime only after this succeeds.

## 10. Acceptance and stabilization

Run deterministic checks for chat, character versions, memory writes/snapshots, job lifecycle/retry, outbox/inbox/idempotency, assets/blob reads, RPG load/new deterministic turn/replay/stale revision, gateway/worker restart, recovery of unpublished events, runtime-node expiry, lifecycle, and capacity.

Run configured local-provider checks separately for LLM, image, TTS/STT, RPG, conversation, and asset generation. Do not place credentials or provider calls in CI.

Monitor PostgreSQL health, pools, locks/timeouts, leases, outbox/dead letters, blob failures, runtime nodes, RPG conflicts, disk, cleanup, application errors, and deterministic state hashes for an operator-defined window. Do not stabilize after only one request.

```powershell
python -m app.persistence cutover stabilize `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --latest-authoritative-revision "<revision-marker>" `
  --operator-note "Stabilization window and acceptance checks completed"
```

## 11. Rollback policy

Before writes reopen, restore the coordinated generation or matching immutable legacy installation deliberately. After writes reopen, prefer forward repair or coordinated PostgreSQL-plus-BlobStore restoration. Never mix PostgreSQL writes back into legacy files.

Recording legacy rollback after writes requires accepted data loss:

```powershell
python -m app.persistence cutover record-rollback `
  --software-revision "<software-revision>" `
  --schema-version "<current-schema>" `
  --operator-note "<bounded reason and accepted data loss>" `
  --destructive-rollback-acknowledged
```

## 12. Completion evidence

Use [POSTGRESQL_CUTOVER_OPERATOR_REPORT_TEMPLATE.md](POSTGRESQL_CUTOVER_OPERATOR_REPORT_TEMPLATE.md). Keep the completed report private if it contains installation paths or user-derived counts. Cutover is complete only at `postgresql_stabilized`, with exact revision/schema, clean import, verified coordinated generation, clean restore rehearsals, passing acceptance, latest authoritative revision, immutable legacy archives, and no runtime writer targeting SQLite/JSONL/mutable JSON.
