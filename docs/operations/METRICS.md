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

### Job queue

Read from PostgreSQL on each scrape (one indexed query over the workspace's
active jobs, and a count of unresolved dead letters). They describe the
workspace's queue, not the process: every gateway process reports the same
values, so aggregate them with `max`, never `sum`.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `omnix_jobs_snapshot_up` | gauge | — | 1 when the queue was read; 0 when the database read failed (the other job metrics are then absent). |
| `omnix_jobs_active` | gauge | `job_type`, `status` | Jobs queued, leased, running, waiting, retrying or cancel-requested. |
| `omnix_jobs_oldest_waiting_age_seconds` | gauge | `job_type` | Age of the oldest job waiting to be claimed (queued, waiting or retrying). |
| `omnix_jobs_expired_leases` | gauge | `job_type` | Active jobs whose lease has expired and not yet been recovered. |
| `omnix_job_dead_letters` | gauge | — | Unresolved dead-lettered jobs. |

`job_type` values are the registered job types, a fixed set.

`GET /api/diagnostics` reports the same totals per process
(`active_requests`, `request_count`, `error_count`).

Requests refused before routing (draining, host and CSRF checks, CORS, sign-in)
are not counted, since no route template exists for them yet; the security
metrics below will cover them. Permission refusals and rate limits happen at
the route and are counted.

## Planned (WP-10.3)

| Area | Metrics |
|---|---|
| Runtime | event-loop lag histogram |
| Database | pool size, in use, wait-time histogram, statement duration by repository method (sampled) |
| Jobs | claims, retries and execution duration by type (recorded in the worker process, which serves no metrics yet) |
| Providers | call latency, errors, circuit state, retries by provider |
| Speech | TTS first-audio latency; live calls active; STT latency |
| Events and outbox | SSE subscribers, events delivered, resyncs; outbox lag and publish rate |
| Maintenance | retention rows deleted, run duration; scheduler task duration, failures, lag |
| Capacity | device permits held and waiting by class |
| Security | auth failures, rate-limit rejections |
