# Diagnostics

`GET /api/diagnostics` is the one diagnostics document for a gateway process.
It needs the `admin:diagnostics` permission (with sign-in off, the local owner
has it). It is content-free: no prompts, transcripts, credentials, database
URLs or exception messages, only states, counts, ages, identifiers of
processes and error classes. Values that look like credentials are redacted
before the response leaves the process.

The response model is `DiagnosticsPayload` in `src/app/composition/gateway/diagnostics.py`
(and in the generated OpenAPI schema).

## Top level

| Field | Content |
|---|---|
| `ok`, `status` | `ready` when every required worker is healthy, else `degraded`. |
| `workers` | Model-service and worker health (TTS, STT, image): reachable, status. |
| `model_residency` | Which models are resident on which device, and the residency policy. |
| `device_permits` | Device capacity per model class, current holders and queues, the model owner. |
| `provider_model_cache` | The provider model catalog cache: state and diagnostics codes. |
| `event_stream` | The browser event transport. |
| `runtime` | This process (below). |

## `runtime` (schema version 2)

| Section | Content |
|---|---|
| `version` | `build_revision` (`OMNIX_SOFTWARE_REVISION`) and `application_schema`, the newest migration this build knows. |
| `features` | Enabled feature ids. |
| `process` | Process id, runtime id, gateway role, uptime, granted capabilities, request totals (`active_requests`, `request_count`, `error_count`, from the metrics registry), and `capability_catalog_digest`: a digest of this process's tool catalog. Processes can differ during a rolling upgrade or an MCP policy reload; a mismatch is for investigation only and never refuses an execution, because approvals are bound to each capability's definition. |
| `postgresql` | Connectivity, authority state, statement timeout, pool statistics, pending migrations, outbox lag (`outbox`). On failure: `connectivity: false` and the error class. |
| `background` | Role and whether this process owns the background lock. |
| `jobs` | Jobs by resource class and status, oldest queued age, expired leases, dead letters, events in the last minute and claim, failure and retry rates. |
| `chat` | Chat dispatcher: workers, queue, provider calls in flight, admissions rejected, recovery state, execution owner health. |
| `scheduler` | Registered and owned scheduled tasks with run, failure and timeout counts, last duration and lag. |
| `tts` | TTS mode and endpoint, stream counters, provider refresh and delivery queue. |
| `events` | Live job events in this process: readers, open subscriptions, reader queries, NOTIFY listeners alive. |
| `retention` | The newest retention run: status, start and end, rows deleted per record type, and the error class if it failed (never its message). |
| `replicas` | Known API replica origins and whether this process started its runtime. |

Durable counts (jobs, outbox, retention) come from PostgreSQL and are
workspace-scoped; the other sections describe this process only.

## Other status endpoints

`GET /api/runtime/status` and `GET /api/workers/health` are views of the same
worker-health data as `workers` above (the first adds the gateway's format
version). `GET /ready` is the readiness probe for load balancers and is
public. Prometheus metrics: `GET /metrics` ([METRICS.md](METRICS.md)).
