# Stuck jobs or queue growth

## Symptoms

- `OmnixInteractiveQueueStalled` (a Chat turn waited more than 30 s) or
  `OmnixBackgroundQueueStalled` (a job type waited more than 5 minutes).
- `OmnixExpiredLeasesNotRecovered` or `OmnixDeadLetters`.
- Users see jobs stay queued in `/jobs`.

## Dashboards and metrics

- Omnix overview: *Active jobs by type and status*, *Oldest waiting job*,
  *Job execution p95*, *Dead letters and expired leases*.
- Job worker `/metrics` (its private listener): `omnix_job_worker_pool_ready`,
  `omnix_job_worker_pool_active_jobs` against `..._concurrency_limit`.

## Diagnosis

1. Which job types are waiting? `max by (job_type, status) (omnix_jobs_active)`.
2. Is a worker pool for that resource class running and ready? Read the job
   worker's `/health/ready` and `/metrics`. A pool at its concurrency limit
   with long `omnix_job_execution_seconds` is saturated; a pool that is not
   ready is down.
3. Are GPU jobs waiting on permits? See [GPU saturation](gpu-saturation.md).
4. Is the provider failing? `omnix_provider_calls_total` by outcome; see
   [Provider outage](provider-outage.md).
5. For one job, open it in `/jobs`: stage, logs, lease, attempts
   ([OPERATIONS: A job is queued or stuck](../../OPERATIONS.md#4-a-job-is-queued-or-stuck)).
   Preserve the job id and logs before changing anything.

## Remediation

- Worker down: restart the job worker for that pool. Running jobs whose lease
  expires are retried by another worker; their attempts are fenced.
- Saturated: add a worker process for the pool, or raise its concurrency if
  the resource allows.
- Expired leases not recovered: confirm the background owner is healthy
  ([Worker ownership lost](worker-ownership-lost.md)); recovery runs there.
- Dead letters: read the error on the dead-lettered job, fix the cause, then
  resubmit from the feature (a new run gets a new identity).

## Verification

- `omnix_jobs_oldest_waiting_age_seconds` returns under its objective
  ([SLOS.md](../SLOS.md)); the alert resolves.
- `omnix_job_dead_letters` does not grow.
