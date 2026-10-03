# Release process

## Versions

Omnix uses semantic versioning. `pyproject.toml` holds the release version;
`src/apps/web/package.json` and the root `package.json` carry the same number
(a test checks they agree). A running process reports its build in `/ready`
and `/api/diagnostics` as `build_revision`, from `OMNIX_SOFTWARE_REVISION`:
set it to `<version>+<short commit>` (for example `0.2.0+3cff3630b`) when you
deploy.

- Major: a change that needs operator action beyond the upgrade steps
  (removed configuration, a contract migration that cannot ship with its code).
- Minor: new features and expand migrations.
- Patch: fixes only, no migrations.

## Checklist

1. `CHANGELOG.md`: move `[Unreleased]` under the new version and date.
2. Bump the version in the three files above.
3. Migrations reviewed: each new one is `phase=expand` unless it is a planned
   contract step whose code change shipped in an earlier release; a
   non-transactional migration contains one statement.
4. OpenAPI diff reviewed (`npm --prefix src/apps/web run api:check` shows the
   intended changes only); clients that read removed fields are updated.
5. Security scan green (dependency audit and secret scan in CI).
6. Restore rehearsal green: the nightly `restore-rehearsal` job, and a manual
   rehearsal of the previous release's backup ([BACKUP_RESTORE.md](BACKUP_RESTORE.md)).
7. The architecture gates and the full test suite pass on the release commit.
8. Tag the commit `v<version>` and push the tag.

## Deployment order

1. Back up (`scripts/backup_omnix.py`).
2. Migrate: `python -m app.persistence migrate` (expand migrations only).
3. Job workers, then the worker/scheduler gateway, then the API replicas, one
   at a time with draining ([rolling upgrade runbook](runbooks/rolling-upgrade.md)).
4. The web assets.
5. Contract migrations, if the release notes call for them, only after every
   process runs the new version.

## Rollback

Redeploy the previous release the same way, one process at a time. Expand
migrations stay applied; older code ignores what they added. A contract
migration never ships in the same release as the code that stops using what
it removes, so rolling back the code never meets a schema it cannot read. If a
release must be abandoned after a contract migration ran, restore the backup
from step 1 into a new database instead of editing the schema
([restore runbook](runbooks/restore.md)).

## Images

Pushing the `v<version>` tag runs `.github/workflows/images.yml`: it builds the
gateway, web, TTS, STT and image images with
`OMNIX_SOFTWARE_REVISION=<version>+<commit>`, fails on critical vulnerabilities
that have a fix, attaches a CycloneDX SBOM per image, smoke-tests the gateway
against PostgreSQL, and pushes `ghcr.io/<owner>/omnix-<image>:<version>` and
`:<commit>`. Deploy with `OMNIX_IMAGE_REGISTRY=ghcr.io/<owner>/` and
`OMNIX_IMAGE_TAG=<version>` in the Compose `.env` (then `docker compose pull`)
(see [Containers](../OPERATIONS.md#containers)); a rollback sets the previous
version and runs the same order. Source deployments still use the tagged commit
and the lock files.
