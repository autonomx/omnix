# Metrics catalog

The gateway serves Prometheus metrics at `GET /metrics` (text exposition
format). The route needs the `admin:metrics` permission; with sign-in off the
local owner has it. Each process keeps its own registry: scrape every gateway
process, not one through a load balancer.

Labels are bounded. `route` is the matched route's template
(`/api/chat/sessions/{session_id}`), never the raw path; requests that match no
route share `route="unmatched"`. `status_class` is `1xx` to `5xx`.

## Implemented

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_http_requests_total` | counter | `route`, `method`, `status_class` | HTTP requests handled. Errors are `status_class="5xx"`. |
| `omnix_http_request_duration_seconds` | histogram | `route`, `method` | Time from the request passing sign-in to the end of the response, including streamed bodies. Buckets: 5 ms to 30 s. |
| `omnix_http_requests_in_flight` | gauge | — | HTTP requests being handled. |
| `omnix_event_loop_lag_seconds` | histogram | — | How late the gateway's event loop woke a task sleeping 0.5 s, sampled twice a second: time spent in blocking code instead of serving requests. Buckets: 1 ms to 5 s. |

### Capacity

GPU and model device permits on this host, read from PostgreSQL on each scrape
without changing anything (expired leases and requests are excluded, not
deleted). Every process on the host reports the same values: aggregate with
`max`.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_device_permit_capacity_units` | gauge | `device`, `model_class` | Permit units the device offers to a model class. |
| `omnix_device_permit_held_units` | gauge | `device`, `model_class` | Units held by running model calls. |
| `omnix_device_permit_waiting_requests` | gauge | `device`, `model_class` | Model calls waiting for a permit. |

### Maintenance

Scheduled tasks run in the process that owns the background lock; read these
from that process (elsewhere the counters stay at zero).

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_scheduler_task_runs_total` | counter | `task` | Runs of each registered scheduled task. |
| `omnix_scheduler_task_failures_total` | counter | `task` | Runs that failed. |
| `omnix_scheduler_task_timeouts_total` | counter | `task` | Runs stopped at the task's timeout. |
| `omnix_scheduler_task_last_duration_seconds` | gauge | `task` | Duration of the last run (absent before the first). |
| `omnix_scheduler_task_last_lag_seconds` | gauge | `task` | How late the last run started (absent before the first). |
| `omnix_retention_rows_deleted_total` | counter | `record_type` | Rows deleted by retention, per policy record type. |

### Security

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_auth_rejections_total` | counter | `reason` | Requests refused by sign-in (`authentication_required`, `run_token_required`, `authentication_unavailable`), the CSRF check (`csrf_failed`), a failed local login (`invalid_credential`) or a permission check (`permission_denied`). |
| `omnix_rate_limit_rejections_total` | counter | `limit` | Requests refused by a rate limit (`login`, `approvals`). |

These refusals happen before routing or in route dependencies, so the HTTP
request metrics above do not show them by route.

### Providers and model services

Recorded by the pooled HTTP client every LLM provider and model-service call
goes through, once per attempt (a retried call counts each attempt). The
gateway installs the recorder (the job worker composes the same app, so its
calls are recorded and served on the worker's own listener). `client`
is the provider's name (`lmstudio`, `openrouter`, ...) or the service
(`tts-service`, `stt-service`, `hermes`, ...), a fixed set.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_provider_calls_total` | counter | `client`, `outcome` | Attempts by outcome: a status class (`2xx` ... `5xx`), `transport_error` (no response: refused, reset, timed out) or `circuit_open` (refused by the circuit breaker without being sent). |
| `omnix_provider_response_seconds` | histogram | `client` | Time from sending to the response headers (to the first byte of a stream, not its end). |
| `omnix_provider_retries_total` | counter | `client` | Attempts sent again after a retryable failure. |

### Event streams

The shared job event stream (`/events`, `/api/jobs/events`; `stream="jobs"`).

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_sse_subscribers` | gauge | `stream` | Open streams in this process. |
| `omnix_sse_events_delivered_total` | counter | `stream`, `phase` | Events written: `replay` (catching up from the client's `Last-Event-ID`) or `live`. |
| `omnix_sse_resyncs_total` | counter | `stream`, `reason` | Streams closed with `event: resync`: `replay_limit` (too far behind to replay) or `overflow` (the subscriber's queue filled). |

### Job queue and outbox

Read from PostgreSQL on each scrape (one indexed query over the workspace's
active jobs, a count of unresolved dead letters, and the outbox relay lag).
They describe the workspace, not the process: every gateway process reports
the same values, so aggregate them with `max`, never `sum`.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_jobs_snapshot_up` | gauge | — | 1 when the queue was read; 0 when the database read failed (the other job metrics are then absent). |
| `omnix_jobs_active` | gauge | `job_type`, `status` | Jobs queued, leased, running, waiting, retrying or cancel-requested. |
| `omnix_jobs_oldest_waiting_age_seconds` | gauge | `job_type` | Age of the oldest job waiting to be claimed (queued, waiting or retrying). |
| `omnix_jobs_expired_leases` | gauge | `job_type` | Active jobs whose lease has expired and not yet been recovered. |
| `omnix_job_dead_letters` | gauge | — | Unresolved dead-lettered jobs. |

| `omnix_outbox_unpublished` | gauge | — | Outbox events the relay has not delivered yet. |
| `omnix_outbox_oldest_unpublished_age_seconds` | gauge | — | Age of the oldest undelivered outbox event. |
| `omnix_outbox_dead_letters` | gauge | — | Outbox events the relay gave up on. |

`job_type` values are the registered job types, a fixed set.

### Database pool

This process's PostgreSQL pool (psycopg_pool statistics); sum them across
processes to compare with `max_connections`.

| Metric | Type | Meaning |
|---|---|---|
| `omnix_db_pool_size` | gauge | Connections the pool holds. |
| `omnix_db_pool_in_use` | gauge | Connections lent out. |
| `omnix_db_pool_max` | gauge | Connections the pool may hold (`OMNIX_DATABASE_POOL_MAX` or the role default). |
| `omnix_db_pool_requests_waiting` | gauge | Callers waiting for a connection. |
| `omnix_db_pool_requests_total` | counter | Connection requests. |
| `omnix_db_pool_request_wait_seconds_total` | counter | Time callers spent waiting for a connection; divide its rate by the request rate for the mean wait. |
| `omnix_db_pool_request_errors_total` | counter | Connection requests that timed out or failed. |
| `omnix_db_pool_connections_lost_total` | counter | Pooled connections found broken. |

`GET /api/diagnostics` reports the same totals per process
(`active_requests`, `request_count`, `error_count`).

Requests refused before routing (draining, host and CSRF checks, CORS, sign-in)
are not counted, since no route template exists for them yet; the security
metrics below count sign-in and CSRF refusals. Permission refusals and rate
limits happen at the route and are counted in both.

## Job worker

The job worker process (`python -m app.worker`) serves its own `GET /metrics`
on its private listener (`--metrics-host`, `--metrics-port`), per resource pool:
`omnix_job_worker_pool_ready`, `omnix_job_worker_pool_active_jobs`,
`omnix_job_worker_pool_concurrency_limit`, and the counters
`omnix_job_worker_pool_claimed_total`, `omnix_job_worker_pool_completed_total`
and `omnix_job_worker_pool_failures_total`. The same page then serves the
process registry: the provider metrics above for calls its jobs make, and

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_job_execution_seconds` | histogram | `job_type`, `outcome` | Durable job executions. `outcome` is the job's resulting status (`completed`, `failed`, `retrying`, `canceled`, ...), `lease_lost` when the lease expired before the result was written, or `error` when the worker caught an unexpected failure. Buckets: 0.1 s to 1 h. A retried job records one execution per attempt. |

## Planned (WP-10.3)

| Area | Metrics |
|---|---|
| Database | statement duration by repository method (sampled); a wait-time histogram (the pool reports only total wait) |
| Speech | TTS first-audio latency; live calls active; STT latency |
| Events and outbox | outbox publish rate; agent-run and Chat streams |
