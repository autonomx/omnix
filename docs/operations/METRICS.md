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
metrics below will cover them. Permission refusals and rate limits happen at
the route and are counted.

## Planned (WP-10.3)

| Area | Metrics |
|---|---|
| Database | statement duration by repository method (sampled); a wait-time histogram (the pool reports only total wait) |
| Jobs | claims, retries and execution duration by type (recorded in the worker process, which serves no metrics yet) |
| Providers | call latency, errors, circuit state, retries by provider |
| Speech | TTS first-audio latency; live calls active; STT latency |
| Events and outbox | SSE subscribers, events delivered, resyncs; outbox publish rate |
| Maintenance | retention rows deleted, run duration; scheduler task duration, failures, lag |
| Capacity | device permits held and waiting by class |
| Security | auth failures, rate-limit rejections |
