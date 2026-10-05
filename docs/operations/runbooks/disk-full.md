# Disk full or retention failing

## Symptoms

- PostgreSQL or blob writes fail; jobs fail while saving outputs.
- `OmnixScheduledTaskFailing` for the retention task.

## Dashboards and metrics

- *Scheduled task failures* on the overview dashboard;
  `omnix_scheduler_task_failures_total{task=...}` and its
  `omnix_scheduler_task_last_duration_seconds`.
- `omnix_retention_rows_deleted_total{record_type}` stops increasing.

## Diagnosis

1. Which disk: the PostgreSQL data directory, the blob root
   (`OMNIX_BLOB_ROOT`, default `resources/data/blobs`), the blob cache
   (`resources/data/cache/blobs`) or the log directory?
2. Retention runs every hour in batches; each run is a row in
   `omnix_lifecycle_cleanup_runs` with its status, counts and error.
3. A disabled or missing policy row in `omnix_retention_policies`.

## Remediation

- Free space first (move logs, clear the content-addressed blob cache: it is
  rebuilt from the blob store on demand). Do not delete blobs that assets
  reference ([OPERATIONS: Assets, blobs, and retention](../../OPERATIONS.md#assets-blobs-and-retention)).
- Run retention by hand, including maintenance-only policies:
  `python -m app.persistence retention` (migration role).
- Fix the failing policy (its error is in `omnix_lifecycle_cleanup_runs`),
  or shorten `retention_days` on the large table.

## Verification

- The next scheduled retention run succeeds; `omnix_retention_rows_deleted_total`
  increases; free space stays above your threshold.
