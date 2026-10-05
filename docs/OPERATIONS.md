# Omnix Operations Guide

## Production worker/API operations

Run one worker/control gateway per workspace and scale API replicas separately. `python scripts/run_omnix_gateway.py --api-replicas 2` supervises worker port 8000 plus APIs 8001/8002. Deployment input is validated once at production composition; changing role/topology variables requires a process restart. Keep `OMNIX_DATABASE_URL` configured for authoritative PostgreSQL and apply/verify migrations through the persistence CLI before rollout.

In local `development` or `local` mode, that launcher also supervises one standalone job-worker process. Start the same process explicitly with `PYTHONPATH=src python -m app.worker --pools llm=2,image=1,tts=1,research=2,cpu=4,stt=1`. Each pool claims only its registered resource classes and has its own concurrency. The process uses per-job lease fencing and does not take the gateway's singleton lock. Set `OMNIX_LOCAL_JOB_WORKER=0` to turn off automatic local startup. Pool readiness is at `http://127.0.0.1:8090/health/ready`; Prometheus metrics by pool are at `/metrics`. Configure the bind with `OMNIX_JOB_WORKER_METRICS_HOST` and `OMNIX_JOB_WORKER_METRICS_PORT`, and set the shutdown drain period with `OMNIX_JOB_WORKER_SHUTDOWN_GRACE_SECONDS`.

Set `OMNIX_TTS_URL` to a shared HTTP service on every API process that serves speech. APIs cannot load local Qwen/CUDA TTS. `OMNIX_GATEWAY_TTS_HTTP=1` also routes the worker through that service. Live-call PCM uses `/api/tts/live-call/stream`; PostgreSQL permit saturation returns HTTP 429 with `Retry-After: 1`. `OMNIX_LIVE_MAX_CALLS` bounds persistent WebSockets per replica and defaults to the TTS permit capacity; `/ready` reports active and available call slots. `OMNIX_GATEWAY_REQUIRED_WORKERS=tts,stt` makes those services readiness dependencies; omit optional services from this list. Invalid URLs, unknown roles and contradictory explicit ownership flags fail startup.

All local GPU inference paths coordinate with PostgreSQL device permits. Set the same `OMNIX_DEVICE_ID` and per-model `OMNIX_DEVICE_*_CAPACITY` values in every process that can use one physical device; `OMNIX_DEVICE_*_REALTIME_RESERVED` keeps configured capacity available to realtime work. `OMNIX_TTS_MODEL_OWNER=gateway` makes the gateway worker the local TTS model owner. Set it to `tts-server` and configure `OMNIX_TTS_URL` on gateway/job-worker processes to serve TTS through the dedicated process. The service reports active permit holders and the TTS model owner in `/api/diagnostics`; a duplicate model load fails instead of silently loading another copy. Capacity changes require draining holders and updating the persisted `omnix_device_capacity` row before restart.

Use [production ingress](architecture/OMNIX_PRODUCTION_INGRESS.md) for the built web app. Vite remains a developer proxy. Probe `/health` for liveness and `/ready` on each gateway origin before admitting it. Readiness requires startup, PostgreSQL authority/schema, a live execution identity and worker ownership when applicable. Connection/authority loss makes the process unready without selecting fallback persistence. Restart the affected worker with a fresh identity after restoring PostgreSQL; a revoked lock or expired execution owner is never revived in place.

Inspect `/api/diagnostics` for process role/capabilities, lock health and registered/started workers, job counts by resource/status, oldest queue age, expired leases/dead letters, chat slots/rejections/recovery duration, TTS refresh/delivery saturation, device permit capacity/holders/queues, model ownership, and pool usage. Durable counts are workspace-scoped. Remote replica readiness is unknown (`null`) until separately probed. Transition logs include safe component/role/owner/transition/duration/error-class fields, without raw database exceptions or credentials.

If a worker dies, PostgreSQL releases its advisory lock. Another worker acquires ownership; expired job attempts are fenced. Chat owner loss produces one terminal recovery event and no duplicate assistant output. A canceled expired lease becomes terminal `canceled`. Use the [release gate commands and measurement profiles](testing/ARCHITECTURE_GATES.md) before rollout; scheduled CPU soak is separate from live GPU/provider certification.

The HTTP worker protocol uses `POST /internal/jobs/claim` and `/internal/jobs/{job_id}/complete` or `/fail`, with `X-Omnix-Service-Token`. Finalization requires the `worker_id` and `lease_token` from that worker's original claim. Missing credentials return 422; an expired, changed or foreign lease returns 409. The retired `/api/jobs/claim`, `/api/jobs/{job_id}/complete` and `/fail` paths return 410 for the compatibility release. Browser job creation, reads and cancellation retain their public paths. Inline chat finalization remains governed by its gateway execution owner.

Every model-service route except `GET`/`HEAD /health` requires `X-Omnix-Service-Token`, including read routes, docs and WebSocket handshakes. Gateway clients send the issued credential and reject redirects. Worker model-control jobs can target only the configured TTS/STT/image endpoints. HTTP errors use `{"error":"<code>","request_id":"<id>"}` without provider exception text or tracebacks. Correlate with `X-Request-ID` and the server logs.

Configure remote/custom STT addresses with the serving process's `OMNIX_STT_URL`. Mutable provider settings cannot select an address for the private service credential; the retired loopback gateway settings still migrate to the local STT worker.

`OMNIX_MAX_UPLOAD_BYTES` defaults to 50 MiB and counts the complete streamed request body, including multipart overhead. Oversized HTTP requests return 413; oversized WebSocket messages close with 1009. The existing STT segment duration/byte limits also apply. Browser STT uses `/api/stt/transcribe`, `/api/stt/authorityz` and `/api/stt/ws/transcribe` through the gateway. Set `VITE_ASSISTANT_STT_URL=/api/stt?authority=auto`; set the server's `OMNIX_STT_URL` to its worker address. Keep the service credential out of browser configuration.

This guide is for running a local Omnix stack, diagnosing failures, and preserving recoverable state. It complements [SETUP.md](SETUP.md), which explains installation and configuration, and [ARCHITECTURE.md](ARCHITECTURE.md), which explains ownership and trust boundaries.

The source tree defines current runtime behavior. The commands and endpoints below describe the supported local development topology documented in this repository as of 2026-09-12.

## Operating principles

1. Identify the failing layer before changing feature configuration.
2. Treat PostgreSQL as the authoritative structured-data runtime.
3. Treat jobs, events, assets, and reports as shared platform surfaces.
4. Keep provider credentials out of source, browser storage, and general settings.
5. Keep model reasoning separate from capability authority and external effects.
6. Record the exact workspace, job/run, provider, model, and revision involved in an incident.
7. Prefer reversible recovery: retry a failed job, restore a known-good artifact, or restart one service before resetting data.

## Service topology

The normal local stack is a set of independently observable processes. Optional services may be stopped without making the core web shell unavailable.

| Service | Default endpoint | Responsibility | Required |
| --- | --- | --- | --- |
| Web / Vite | http://127.0.0.1:5173 | Browser application and /api plus /events proxy | Yes |
| FastAPI gateway | http://127.0.0.1:8000 | Browser/API boundary, domain orchestration, events | Yes |
| PostgreSQL | 127.0.0.1:5432 | Authoritative structured persistence | Yes |
| Launcher | http://127.0.0.1:5055 | Windows service-control dashboard | Optional |
| TTS | http://127.0.0.1:5101 | Speech synthesis worker | Feature-dependent |
| STT | http://127.0.0.1:5201 | Speech recognition/transcription worker | Feature-dependent |
| Image | http://127.0.0.1:5301 | Image service and model residency | Feature-dependent |
| Hermes | http://127.0.0.1:8642 | Optional out-of-process agent proposals | Optional |

The Vite server proxies browser calls to the gateway. A direct browser request to a worker is not a substitute for a gateway contract: feature code should continue to use the shared API and event boundaries.

```omnix-diagram service-topology
```

## Containers

Images (`deploy/docker/`):

| Image | Dockerfile | Contents | Runs as |
| --- | --- | --- | --- |
| `omnix-gateway` | `gateway.Dockerfile` | Gateway lock in a venv, `src/app`, scripts, ffmpeg; no CUDA, no models. API replicas, the gateway worker, the job worker and migrations all use it. `--build-arg OMNIX_LOCK=tracing` adds OpenTelemetry. | uid 10001, read-only root |
| `omnix-web` | `web.Dockerfile` | The built SPA behind Nginx with the ingress routes (`deploy/docker/nginx/omnix.conf`, generated from the route policy). | Nginx's unprivileged user |
| `omnix-tts`, `omnix-stt`, `omnix-image` | `tts`/`stt`/`image.Dockerfile` | CUDA 12.4 runtime, Python 3.11, the service's Linux lock (one Torch version). No weights. | uid 10001 |

Model weights are not in the images. `python -m app.models download --service <tts|stt|image>`
fetches the pinned files listed in `src/app/models/catalog.json` (a commit per
repository and a SHA-256 per file) into the Hugging Face cache on the `/models`
volume, refuses any file whose digest differs, and points the cache's `main` ref
at the pinned commit. The services run with `HF_HUB_OFFLINE=1`, so they load
only those files. `python -m app.models verify --service <name>` checks a cache
without downloading. To move a model to a new upstream commit, a maintainer runs
`python -m app.models pin <id> --repo <repo> --service <name> --include <files...>`
and reviews the catalog diff.

Compose (`docker-compose.yml`) needs a `.env` (template: `.env.example`) with
`OMNIX_POSTGRES_PASSWORD` (database owner, migrations), `OMNIX_APP_DB_PASSWORD`
(the `omnix_app` runtime role, created when the database volume is first
initialized) and `OMNIX_SERVICE_TOKEN`; it refuses to start without them.

| Profile | Services |
| --- | --- |
| default | `postgres`, `migrate` (one-shot), `gateway-worker` (scheduler and singletons), `api` (`OMNIX_API_REPLICAS`, default 2), `job-worker`, `web` (http://127.0.0.1:8080) |
| `gpu` | `tts`, `stt`, `image`, each after a one-shot `*-models` download |
| `storage` | `s3` (SeaweedFS) and a one-shot `s3-bucket`; set `OMNIX_BLOB_BACKEND=s3` and the `OMNIX_S3_*` credentials |
| `observability` | `otel-collector`, `jaeger`, `prometheus` (http://127.0.0.1:9090, with `deploy/observability/alerts.yml`), `grafana` (http://127.0.0.1:3000, read-only dashboards without sign-in) |
| `agent-tests` | `postgres-agent-tests`, a disposable test database on port 55432 |

The `postgres` service shares its container and volume names with
`docker-compose.postgres.yml`, so both refer to the same local database. An
existing volume was initialized without `omnix_app`: create the role by hand
(see Database roles below) before starting the stack against it.

`.github/workflows/images.yml` builds every image nightly and on release tags,
scans it with trivy (fails on critical vulnerabilities that have a fix), stores
a CycloneDX SBOM and smoke-tests the gateway image against PostgreSQL; release
tags also push the images to GHCR.

## Startup runbook

### Separate process mode

1. Start PostgreSQL:

       docker compose -f docker-compose.postgres.yml up -d

2. Set the database URL. PowerShell:

       $env:OMNIX_DATABASE_URL = 'postgresql://omnix:<password>@127.0.0.1:5432/omnix'

   Bash or WSL:

       export OMNIX_DATABASE_URL='postgresql://omnix:<password>@127.0.0.1:5432/omnix'

3. Install dependencies and apply migrations:

       python -m pip install --require-hashes -r requirements.txt
       npm install
       python -m app.persistence migrate
       python -m app.persistence verify

4. Start the gateway in one terminal:

       PYTHONPATH=src python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000

   In PowerShell, set $env:PYTHONPATH = 'src' first if it is not already set.

5. Start the web app in another terminal:

       npm run web:dev

6. Open http://localhost:5173/. The root route redirects to /chatbot.

### Windows launcher mode

`python -m app.launcher start` (wrapped by start_all.bat and start_all.sh) coordinates PostgreSQL, the gateway, optional workers, Hermes, and the browser. Interpreter paths come from `RPG_*_PYTHON`, `resources/config/launcher.toml` or the Conda environments, not from the scripts. The portable contract is the service URLs and environment variables, not a particular absolute path.

Use the launcher dashboard at http://127.0.0.1:5055 to inspect or control services when the launcher is configured. The launcher can auto-start optional services; keep auto-start flags explicit when diagnosing startup order.

## Logs and request ids

The gateway (`src/main.py`, `src/launch.py`) and the worker process configure one
structured log handler on stderr. `OMNIX_LOG_FORMAT=json` writes one JSON object
per line (use it in containers); the default `text` appends the bound ids in
brackets. `OMNIX_LOG_LEVEL` sets the root level and `OMNIX_LOG_LEVELS` per-logger
levels, for example `uvicorn.access=WARNING,omnix.tts=DEBUG`.

Every gateway request and WebSocket gets a request id: a valid inbound
`X-Request-ID` (8–128 of `A-Z a-z 0-9 . _ : -`) is kept, otherwise one is
generated, and it is returned in the `X-Request-ID` response header. Log lines
written while handling the request carry `request_id`; lines written while a
job runs carry `job_id` (and `attempt` and `feature` for durable worker jobs),
including lines from the provider call made for a Chat turn. Quote the
response's `X-Request-ID` when reporting a failed request.

A job keeps the id of the request that submitted it as `correlation_id` (shown
on the job API and in the Chat stream's `job` event). The Chat dispatcher and
the durable worker log under that `request_id`, so one id follows a submission
from its request into the job and its provider calls; a job submitted by a
running job inherits it. Scheduler and CLI submissions have none.

Calls to the TTS, STT and image services forward the id in `X-Request-ID`. The
services keep a valid forwarded id (otherwise they generate one), return it,
and log under it, so a gateway line and a model-service line for the same call
share one `request_id`. The model services configure the same handler, so
`OMNIX_LOG_FORMAT` and the level settings apply to them too.

The web app sends its own id with every gateway call, and its API error
messages end with `(request id …)`: search the gateway logs for that id.

### Error responses

Gateway errors answer with `application/problem+json` (RFC 9457): `type`,
`title`, `status`, `detail`, `instance` (the request path), `request_id` and
`code`, a stable machine code (`session_not_found`, `rate_limited`,
`permission_denied`, `invalid_request`, `internal_error`, or the status name).
`detail` is the value the route has always returned, so existing clients read
it unchanged. An unhandled exception answers 500 with a generic detail and the
request id; the stack trace is logged under that request id, never returned.

## Metrics

`GET /metrics` serves Prometheus metrics for the process that answers (it
needs `admin:metrics`). Scrape each gateway process directly. The catalog and
label rules are in [operations/METRICS.md](operations/METRICS.md).

Objectives and their error budget are in [operations/SLOS.md](operations/SLOS.md).
The diagnostics document (`/api/diagnostics`) is described in [operations/DIAGNOSTICS.md](operations/DIAGNOSTICS.md).
Prometheus alert rules: `deploy/observability/alerts.yml`; Grafana dashboard
(import with a Prometheus data source): `deploy/observability/dashboards/omnix-overview.json`.

## Tracing

Tracing is optional and off by default. To turn it on:

1. Install the tracing lock (a superset of the gateway lock):
   `python -m pip install --require-hashes -r requirements/tracing.lock.txt`.
   For the gateway image, build `deploy/docker/gateway.Dockerfile` with
   `--build-arg OMNIX_LOCK=tracing` (Compose: `OMNIX_LOCK=tracing` in `.env`).
2. Set `OMNIX_OTEL_ENABLED=true` and the standard exporter variables, for
   example `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318` (OTLP over HTTP).
   `OTEL_SERVICE_NAME` overrides the service name (`omnix-gateway`,
   `omnix-job-worker`).

If the variable is set but the packages are missing, the process logs a warning
and runs without tracing.

What is traced:

- every gateway request (FastAPI server spans; `/health`, `/health/ready` and
  `/metrics` are left out), with the request id as `omnix.request_id`;
- outbound httpx calls (model services and providers), which carry the
  `traceparent` header, and psycopg statements;
- durable job execution (`job.execute`, with job type, id, attempt and pool) in
  the job worker and the Chat dispatcher;
- RPG turn stages (`rpg.turn.pipeline` and its `rpg.turn.*` stages, with their
  scalar measurements);
- live speech stages (`live_speech.utterance`, `.transcript`, `.first_audio`,
  `.response`), recorded from the turn's timestamps;
- agent steps: the model-call and capability request spans name the run
  (`omnix.agent_run_id`, `omnix.agent_step`), and capability adapters run in a
  `capability.execute` span.

Spans carry identifiers and measurements, never prompts, transcripts or tool
input. While a span is active, log lines carry its `trace_id`.

A job runs in its own trace: the worker does not continue the submitting
request's trace. Use `request_id` (the job's correlation id, also a span
attribute) to join them.

Local viewer: `docker compose --profile observability up -d otel-collector jaeger`
starts a collector (`deploy/observability/otel-collector.yaml`) and Jaeger
(UI on http://127.0.0.1:16686). Processes on the host send to
`http://127.0.0.1:4318`; services in the Compose network send to
`http://otel-collector:4318`. This profile is
documentation for operators and is not exercised in CI.

## Health and readiness checks

Health means different things at different layers.

| Check | What it proves | What it does not prove |
| --- | --- | --- |
| Vite page loads | The browser server is reachable | The gateway, database, or providers are healthy |
| GET /api/health | The gateway process can answer | PostgreSQL migrations, model residency, or a feature provider |
| PostgreSQL health | The database process accepts connections | The current schema is migrated or application data is valid |
| Provider status | A provider adapter can report state | A selected model can satisfy the current request |
| Worker health | A worker process is reachable | The requested model is loaded or resource capacity is free |
| Job status | A durable job/run has a known lifecycle state | Its output passed acceptance or evidence gates |
| Event connection | The browser can receive updates | The underlying job or provider is successful |
| Image runtime status | Image service and residency state are observable | Generation will succeed for every prompt |

```omnix-diagram job-lifecycle
```

Check the gateway before debugging a feature:

    http://127.0.0.1:8000/health
    http://127.0.0.1:8000/api/health

Use the /diagnostics workspace, /jobs, /providers, and /models to correlate runtime state with the failing feature.

## Rolling restarts and draining

`/ready` reports the running revision in `build_revision`, which comes from
`OMNIX_SOFTWARE_REVISION`.

On SIGTERM, or the launcher's stop, a gateway drains before it exits:

1. `/ready` returns 503 with reason `draining` at once.
2. New requests get 503 `draining` with `Retry-After: 1` and `Connection: close`.
   New WebSockets close with code 1012. Clients and the ingress retry on
   another replica.
3. Requests and streams already in progress get up to `OMNIX_DRAIN_SECONDS`
   (default 30) to finish.
4. The process then shuts down normally, which releases its runtime lease,
   scheduler locks and job leases.

`OMNIX_DRAIN_MIN_SECONDS` (default 0) keeps a draining replica visibly
not-ready for at least that long, even when it is idle. In multi-replica
deployments, set it to at least the ingress readiness-probe interval. A second
Ctrl+C forces an immediate exit.

Job workers stop claiming on shutdown. They let running jobs finish within
`OMNIX_JOB_WORKER_SHUTDOWN_GRACE_SECONDS` and release the leases of any that
are still running, so another worker retries them.

Releases (versions, checklist, deployment order and rollback): [operations/RELEASE.md](operations/RELEASE.md).

To upgrade replicas one at a time:

1. Apply expand migrations first (`python -m app.persistence migrate`).
2. Stop one replica and wait for it to exit.
3. Start it on the new revision and wait for `/ready` to report the new
   `build_revision`.
4. Repeat for each replica, then each job worker.

The nightly `rolling-upgrade` job runs this sequence under load
(`scripts/rolling_upgrade_test.py`).

## Multi-host topology test

`docker-compose.multihost-test.yml` runs Omnix as separate hosts behind Nginx:

- two API replicas and one worker/scheduler gateway;
- two job workers;
- a fake model service (LM Studio–compatible chat and remote TTS, CPU only);
- PostgreSQL and an S3-compatible store (SeaweedFS).

Each Omnix service has its own container filesystem, and blobs use the `s3`
backend. The Nginx config `deploy/multihost/nginx.conf` is generated from the
same routing policy as `deploy/nginx/omnix.conf`
(`python scripts/render_gateway_ingress.py`).

    docker compose -f docker-compose.multihost-test.yml up -d --build --wait
    docker compose -f docker-compose.multihost-test.yml run --no-deps --rm driver
    docker compose -f docker-compose.multihost-test.yml down -v

The driver (`scripts/multihost_topology_test.py`) checks:

- chat across replicas;
- the event stream;
- an asset saved on one host and read on another;
- live-call PCM streaming.

It then runs a mixed load and writes p50/p95/p99 latency and throughput to
`artifacts/multihost-topology.json`. The nightly `multihost-topology` job runs
it. When you re-run `up --build` against an existing stack, recreate Nginx
(`--force-recreate`): it resolves replica addresses only at startup.

## Triage decision tree

For alerts and recurring incidents, follow the [runbooks](operations/runbooks/README.md):
worker ownership lost, stuck jobs, PostgreSQL outage, GPU saturation, provider
outage, sign-in outage, disk full, secret rotation, rolling upgrade and
rollback, and restore. The steps below cover first-run and development
problems.

### 1. The page does not open

- Confirm the Vite process is running on port 5173.
- If using a launcher, confirm the launcher opened the configured app URL.
- Check for a port conflict.
- If the page loads but assets are missing, inspect the Vite terminal for build/module errors.

### 2. The page opens but requests fail

- Request /api/health from the gateway.
- Confirm the Vite proxy target is 127.0.0.1:8000.
- Confirm the gateway inherited PYTHONPATH=src.
- Inspect the browser Network panel for the first failing request, not only the final cascade of errors.
- Check gateway logs for validation, persistence, or provider errors.

### 3. The gateway starts but persistence fails

- Confirm OMNIX_DATABASE_URL is set in the same process environment as the gateway.
- Confirm the URL uses PostgreSQL; SQLite is not the supported production runtime.
- Check the PostgreSQL container is healthy and the port is reachable.
- Run:

      python -m app.persistence migrate
      python -m app.persistence verify

- If the schema is current but a feature still fails, capture the request path, job/session ID, and gateway error before changing data.

### 4. A job is queued or stuck

Inspect the shared job record in /jobs:

- module and job type;
- queue and execution state;
- current semantic stage;
- resource class or lock;
- progress and status message;
- latest logs;
- input/output asset references;
- event-stream connection state.

A queued job usually indicates a worker, resource lock, or provider readiness boundary. A running job with no visible progress may indicate an event connection problem; inspect the job record and logs before retrying.

Cancel only active work that is safe to stop. Retry from the feature surface when the job contract supports retry so the new run has a clear identity.

### 5. A provider or model is unavailable

Check /providers and /models together:

1. Is the provider configured?
2. Does it advertise the capability the feature needs?
3. Is its health/readiness state current?
4. Is the selected model associated with the provider?
5. Is the model installed or remote as expected?
6. Is the requested resource class available?
7. Is the failure an authentication, timeout, capacity, or validation error?

A provider selector should be capability-driven. Do not work around a missing capability by calling an unrelated provider directly from a feature.

### 6. Image generation reports an unloaded model

The image service has separate states for process health, model download/completeness, model load, and generation readiness.

Use the /image-generation workspace and check:

- OMNIX_IMAGE_ENABLED;
- OMNIX_IMAGE_URL;
- image service health and provider status;
- model file completeness;
- explicit model load state;
- GPU/VRAM availability;
- image job logs and cancellation state.

The supported flow is: select model -> download if needed -> explicitly load -> generate -> inspect the asset. Service health alone does not imply that weights are resident in memory.

### 7. Voice or transcription fails

For TTS:

- check the TTS endpoint at 127.0.0.1:5101;
- confirm a TTS-capable provider and voice profile;
- inspect the input script and speaker assignment;
- inspect the shared voice job and resource lock;
- verify the generated audio asset path and metadata.

For STT:

- check the STT endpoint at 127.0.0.1:5201;
- confirm the source asset is indexed and readable;
- confirm the provider supports transcription;
- check language/automatic-detection settings;
- inspect the stt.transcribe job and transcript asset.

### 8. An agent proposes but does not execute

This can be an expected governance result. Inspect:

- semantic route and mode;
- issued capability grants;
- workspace and path scope;
- network and credential requirements;
- required approval or confirmation;
- stale-proposal/revision state;
- acceptance and evidence requirements;
- reviewer or recovery status.

Profiles are ceilings, not grants. Approval policy cannot widen a grant that was not issued. A model proposal is not proof that an external effect is authorized.

## Events and realtime

SSE is preferred for one-way updates:

- job progress and stages;
- report generation;
- provider health;
- diagnostics;
- streaming text;
- background narration.

WebSockets are reserved for true bidirectional workflows such as live voice. If the browser shows stale progress:

1. Inspect the event connection state.
2. Compare the displayed job ID with /jobs.
3. Refresh the workspace to test server-state recovery.
4. Inspect gateway logs for disconnects or serialization errors.
5. Use the durable job record as the source of truth.

A reconnecting browser should be able to recover from the current backend state; it should not require the event stream to be the only record of progress.

## PostgreSQL and recovery

PostgreSQL stores authoritative structured state used by sessions, jobs, provider/model metadata, settings, agent lifecycle, RPG state, trading paper state, and other durable workflows. Migrations are forward changes under src/app/persistence/migrations.

Before a schema or runtime change:

    python -m app.persistence verify

Backups, restore rehearsals and the recovery targets are in [operations/BACKUP_RESTORE.md](operations/BACKUP_RESTORE.md) (`scripts/backup_omnix.py`, `scripts/restore_rehearsal.py`). For a database-only backup, use the PostgreSQL tooling appropriate to your environment and keep the output outside the repository. Back up as the migration role (`OMNIX_MIGRATION_DATABASE_URL`, or `OMNIX_DATABASE_URL` when you use one role); `python -m app.persistence backup` does this for you. Example:

    pg_dump --dbname="$OMNIX_MIGRATION_DATABASE_URL" --format=custom --file=omnix-backup.dump

### Retention

The scheduler deletes old rows every hour, in small batches, following
`omnix_retention_policies`:

| Data | Kept for |
|---|---|
| Finished jobs (with their events, logs and attempts) | 30 days |
| Job events | 90 days |
| Agent run events of finished runs | 30 days; evidence, approval, acceptance, artifact and lifecycle events stay |
| Published outbox events, processed inbox entries | 7 days |
| Resolved dead letters | 90 days |
| Expired sign-in sessions | 7 days after expiry |
| Stopped runtime nodes | 7 days |
| Audit events | 365 days, maintenance only |
| Trading strategy events | 180 days, disabled by default |

Change a policy by updating its row (`retention_days`, `enabled`). Audit
retention runs only through `python -m app.persistence retention`, which
uses the migration role and runs every enabled policy. Each run is recorded
in `omnix_lifecycle_cleanup_runs`.

### Live events

Each gateway process runs one event reader per workspace for `/events`. It
wakes on `NOTIFY omnix_events` (sent when a job event commits) and polls every
5 seconds as a fallback, so the database load does not grow with the number
of open browser tabs. Event ids have the form `<transaction>:<id>`; a client
reconnecting with an older integer id restarts from the oldest event since the
upgrade. A client that falls more than 1,000 events behind, or asks to replay
more than 5,000, receives `event: resync` and reloads its data. If the log
shows `event_reader_listen_unavailable`, events still arrive, up to 5 seconds
late.

Events are delivered only once every older transaction on the PostgreSQL
server has finished, so none is skipped. A transaction left open (for example
an idle `psql` session inside `BEGIN`) holds back live events until it ends.
Find one with:

    SELECT pid, state, xact_start, query FROM pg_stat_activity
     WHERE backend_xid IS NOT NULL ORDER BY xact_start LIMIT 5;

### Database connections

Each process keeps a connection pool sized by its role (API and worker 10,
job worker 5, scheduler 3); `OMNIX_DATABASE_POOL_MAX` sets one size for all.
Each process also opens up to three connections outside its pool (its
background or scheduler lock and the live-event listeners). Set
`OMNIX_DEPLOYMENT_PROCESS_COUNTS` (for example `api=2,worker=1,job-worker=2,scheduler=1`)
and startup logs `database_connection_budget` when the total would exceed 80%
of PostgreSQL's `max_connections`; `/ready` reports the computed budget.

Statement time limits: requests use `OMNIX_DATABASE_STATEMENT_TIMEOUT`
(30 s by default), jobs 30 s and scheduled maintenance 120 s; override with
`OMNIX_DATABASE_STATEMENT_TIMEOUT_REQUEST`, `..._JOB` and `..._MAINTENANCE`.

### Index migrations

Some migrations build indexes with `CREATE INDEX CONCURRENTLY` (for example
`0110_chat_message_search_index`), so chat keeps working while they run. If
such a migration is interrupted, PostgreSQL leaves an INVALID index; drop it
(`DROP INDEX CONCURRENTLY <name>`) and run `python -m app.persistence migrate`
again.

### Outbox

Agent, task-graph and workflow run events are also written to
`omnix_outbox_events` in the same transaction. A scheduled task delivers them
every second to their consumers; today the only consumer wakes the open run
event streams. `/api/diagnostics` shows `runtime.postgresql.outbox`: the
number of undelivered events, the age of the oldest one, and dead letters.
An age that keeps growing means no process is running schedulers. A consumer
that fails five times moves the event to `omnix_outbox_dead_letters` with the
error; after fixing the cause, set the event back to `pending` to retry it:

    UPDATE omnix_outbox_events SET status = 'pending', available_at = now()
     WHERE event_key = '<key>';
    DELETE FROM omnix_outbox_consumer_inbox WHERE event_key = '<key>' AND status = 'dead_letter';

### Document shapes

Small feature documents live in `omnix_module_records`. Each kind
(`module`/`record_type`) has a Pydantic shape its feature registers; a write
with the wrong shape is refused (`DocumentShapeError`). A stored document that
does not match is still read, logged as `document_shape_mismatch` and counted
in `omnix_document_shape_mismatches_total`. To list every stored document that
does not match, or whose kind has no shape:

```
python scripts/check_document_shapes.py
```

It exits 1 when it finds one. Run it after importing legacy data and before a
release that tightens a shape.

### Database roles and row-level security

Every table with a `workspace_id` has a row-level security policy: a connection sees only the rows of the workspace it serves. Omnix sets that workspace on each pooled connection, so a query that forgets its workspace filter still cannot read another workspace. A short list of system operations (sign-in lookups, listing workspaces, migrations, operator commands) may see every workspace; it lives in `src/app/persistence/tenant_scope.py`.

PostgreSQL does not apply these policies to superusers or roles with `BYPASSRLS`. A single superuser role (the default local install) keeps working, but has no database-level isolation. For isolation, use two roles:

- a migration role that owns the tables and runs migrations and backups (`OMNIX_MIGRATION_DATABASE_URL`). Backups read every workspace, so this role must be a superuser or have `BYPASSRLS`;
- a runtime role for the application (`OMNIX_DATABASE_URL`): not a superuser, not the owner, no `BYPASSRLS`.

Create the runtime role before applying migrations; migrations grant it data access to every table:

    CREATE ROLE omnix_app LOGIN PASSWORD '<secret>' NOSUPERUSER NOBYPASSRLS;
    python -m app.persistence migrate    # with OMNIX_MIGRATION_DATABASE_URL set

Upgrades: migration `0106_row_level_security` is a contract migration. Upgrade every Omnix process first, then apply it; older processes do not set the workspace and would see no rows.

Do not commit dumps, credentials, runtime blobs, model weights, or generated private assets. A restore should be tested against an isolated database before replacing an active environment.

For recovery-sensitive agent or job incidents, preserve the durable identifiers and logs before restarting or cleaning anything:

- session ID;
- job/run ID;
- task revision;
- workspace/candidate identity;
- provider/model;
- event timestamps;
- acceptance/evidence/review state.

## Assets, blobs, and retention

The asset system indexes generated and ingested files with ownership, type, MIME metadata, and storage references. The blob root can be configured with OMNIX_BLOB_ROOT; agent logs can be configured with OMNIX_AGENT_LOG_DIR.

Operational rules:

- Keep generated output in the shared asset/artifact path.
- Do not delete a blob before confirming its asset/report reference and retention policy.
- Preserve reports and evidence needed to explain an accepted or rejected run.
- Treat paths returned by compatibility routes as untrusted until they pass the gateway's content/type/size policy.
- Keep large model files and runtime caches out of version control.

### Blob storage backends

`OMNIX_BLOB_BACKEND` selects where blobs live. Every process (gateway, job
workers, image service) must use the same settings.

| Value | Storage |
|---|---|
| `local` (default) | Files under `OMNIX_BLOB_ROOT`, or `resources/data/blobs` when unset. Single-host deployments. |
| `s3` | Any S3-compatible bucket: AWS S3, SeaweedFS, MinIO. Required when gateways and workers run on different hosts. |

The `s3` backend uses these settings:

- `OMNIX_S3_ENDPOINT`: an http(s) origin with no path.
- `OMNIX_S3_BUCKET`: the bucket must already exist.
- `OMNIX_S3_ACCESS_KEY_ID` and `OMNIX_S3_SECRET_ACCESS_KEY`.
- `OMNIX_S3_REGION`: default `us-east-1`.
- `OMNIX_S3_PREFIX`: optional key prefix.
- `OMNIX_S3_TIMEOUT_SECONDS`: default 60.

Requests use path-style addressing with AWS Signature Version 4. Every
object's SHA-256 is stored as metadata and verified on read.

Assets keep a relative `storage_key`. Feature code reads content through
`app.assets.content`; tools that need a file path get a checksum-verified
copy from a content-addressed cache under `resources/data/cache/blobs`. Audio
assets stream from `/api/assets/{asset_id}/audio`, which supports Range
requests. Job rows reference assets and never embed audio. Voice-clone
samples submitted inline are moved into the blob store when the job is
admitted.

With `s3`, the image service also uploads each output to the bucket and
returns its key. A gateway on another host then never needs the image
service's disk. Voice clones are still file-managed on the voice/TTS host;
moving them into blob-backed asset records is a follow-up.

## Memory v2 switch

Curated memory (what a person saves, approves, edits, pins, moves, archives or
forgets) is served by Memory v1 until an operator switches it to Memory v2.
After the switch every process reads and writes curated memory in the v2
observation log: one `curated_memory` observation per record revision, where
a new revision retires the previous one in the same transaction and
forgetting purges every revision's text. The memory screens, chat memory
commands, suggestion approvals, session snapshots and live voice keep working
unchanged; v1's record table becomes read-only. Chat prompts put pinned
memories first, then the memories v2 retrieval ranks highest for the turn;
character sessions with shared memory access still get the System Assistant's
allowed categories. Only active, non-secret, approved memories are
retrievable, and each stops at its expiry, the same rule v1 applies. Every v2
memory space belongs to a tenant workspace, so workspaces never share memory.

Memory v2 retrieves by meaning as well as by words, as VoiceMem does, when its
embedding model is installed. `setup.bat` / `setup.sh` download it; on a host
installed by hand, run `python -m app.assistant_memory.v2.embeddings download`
once on each host that runs the scheduler or serves retrieval (about
490 MB, pinned `intfloat/multilingual-e5-small`, SHA-256 checked, stored under
`resources/models/multilingual-e5-small` or `OMNIX_MEMORY_EMBEDDING_MODEL_DIR`).
Without the model, retrieval uses words only. `OMNIX_MEMORY_EMBEDDINGS=0`
turns it off. `python scripts/compare_memory_retrieval.py --database-url
<disposable test database>` compares v1 and v2 retrieval on the same memories.

Each write derives and indexes its memory immediately; the scheduler's
`memory-v2.convergence` task (every 10 s, only once v2 is authoritative)
retries anything that did not converge, with the worker's backoff.

### Switching

The switch is a human decision. With the gateway running this code (migration
`0119_memory_v2_curated_records` applied):

```powershell
$env:PYTHONPATH = "src"
python scripts/backup_omnix.py --output-dir <backup folder>        # 1. back up
python -m app.assistant_memory.v2.shadow_runner                   # 2. import and compare
python -m app.assistant_memory.v2.shadow_report --require-ready   # 3. verdict
python -m app.assistant_memory.v2.cutover activate --by <name> --reason "<why>"   # 4. switch
python -m app.assistant_memory.v2.cutover status                  # 5. confirm
```

The shadow runner works only while v1 is authoritative, one run at a time,
across every workspace. For each memory owner it imports every v1 record
(archived, secret and unapproved ones too, so they stay manageable),
revoking revisions v1 replaced and purging records v1 forgot, derives the
retrievable memories without a model, rebuilds the search index and
embeddings, then asks v2 for up to `--probes` (default 200) prompt-eligible
records by their own words, under the record's scope, with Chat's limits
(top 12, 50 ms; `--deadline-ms` to change). Recall is the share of records v2
found (`--required-recall`, default 0.95); precision is the share of returned
memories backed only by eligible v1 records visible to the question
(`--required-precision`, default 1.0). It then validates replay and records a
readiness receipt. Its output lists each space's counts, recall, precision,
`embeddings` (`synced`, or `model_absent` when the probes measured word
retrieval) and verdict; it exits 1 unless every space is ready. `--owner
character:<id>` (repeatable) runs one owner. An owner with a v1 row the v1
contract rejects is skipped and listed.

The report is read-only and covers every workspace. It prints the current
authority epoch and, for each v2 memory space, its watermarks, latest shadow
retrieval evaluation (recall, precision, pass) and latest cutover readiness
receipt, with a status: `not_evaluated`, `v1_changed` (the owner's v1 records
changed since the last run: run the runner again), `evaluation_stale`
(observations arrived after the evaluation), `shadow_failed`, `not_ready` (no
current ready receipt) or `ready`. It also lists v1 owners with memories that
have no v2 space yet. `--require-ready` exits 1 unless every space is `ready`
and every v1 owner is imported.

`activate` refuses unless the report is ready, or v1 holds no memory at all.
Under the authority lock it re-checks every receipt and that v1 did not change
since the shadow run (in-flight v1 saves finish first; later ones are
refused), then switches. If a person saved a memory in between, it refuses
with "v1 memory changed since the shadow run": run the shadow runner again.

### Rolling back

`python -m app.assistant_memory.v2.cutover rollback --by <name> --reason
"<why>"` returns curated memory to v1 only while nothing has been saved,
edited or forgotten under v2 (v1 would lose or resurrect those memories);
otherwise it refuses. Rollback is meant for the minutes right after a switch.
Later, restore the step 1 backup instead, accepting the loss of memory saved
since.

## Secrets and networked integrations

Connected assistant tools (Gmail, Calendar, GitHub and others) keep their
OAuth tokens and OAuth client secrets in the secret store, one entry per
workspace. They never go to PostgreSQL, the settings document or a plain file.
Choose the store with `OMNIX_SECRET_STORE`:

- `auto` (default): Windows DPAPI on Windows; the OS keychain elsewhere when
  the `keyring` package is installed; otherwise the read-only environment
  store;
- `dpapi`: an encrypted file under `%LOCALAPPDATA%\Omnix\secrets`
  (`OMNIX_SECRET_STORE_PATH` to move it);
- `keyring`: macOS Keychain or Secret Service on Linux
  (`pip install keyring`);
- `env`: read-only `OMNIX_SECRET_<NAME>` variables, for containers that
  receive secrets from their platform.

With the read-only store, connecting a tool fails with a clear error instead
of writing a plaintext file. To use an external vault (HashiCorp Vault, Azure
Key Vault), implement the `SecretStore` protocol in
`src/app/security/secrets.py` and install it at startup.


Provider secrets are environment- or protected-store-owned. Examples include LLM/search, market-data, and integration credentials.

- Never paste a secret into a chat message, issue, log, source file, or committed settings fixture.
- Redact authorization headers, API keys, DSNs, cookies, and tokens from incident captures.
- Keep local-network discovery and device control behind the governed capability system.
- Review network, credential, and confirmation requirements before enabling a tool.
- Treat trading credentials and execution endpoints as higher risk than read-only market data.

The settings UI can expose status and configuration summaries, but it should not become an unredacted secret store.

## Hermes sidecar

Hermes is optional and runs out of process. The sidecar may contribute planning, route decisions, or proposals, but Omnix retains:

- capability registry and policy authority;
- application and domain state;
- approval/confirmation decisions;
- execution broker authority;
- evidence and acceptance decisions;
- durable lifecycle persistence.

Follow HERMES_SIDECAR_SETUP.md to install and verify it. Keep Hermes disabled until the endpoint is reachable and the intended policy is understood.

Tool execution uses a durable proposal flow. Submit the tool, action, input and session to `POST /api/assistant/tools/proposals`. If its response requires approval, the user confirms the exact action with `POST /api/assistant/tools/proposals/{proposal_id}/approve` (or rejects it with `/deny`). Execute it with `POST /api/assistant/tools/proposals/{proposal_id}/execute`. The server checks current policy, expiry and the stored input digest, then consumes the proposal and reserves its execution ledger in one PostgreSQL transaction before dispatch. A failed or interrupted execution cannot reuse that proposal.

Public tool request envelopes reject `approved` and `approval_policy`. The browser uses the proposal flow after explicit confirmation. The legacy `/api/hermes/assistant/tools/execute` endpoint is internal, absent from the public OpenAPI schema, and requires both an existing proposal ID and `X-Omnix-Service-Token`. Configure `OMNIX_SERVICE_TOKEN` with at least 32 random bytes encoded URL-safe; missing or invalid service credentials fail closed.

In local mode, the launcher creates the service token at first start and reuses it for child services. Windows stores an encrypted `service-token.dpapi` alongside the provider secret store; POSIX uses a mode-0600 file at `resources/data/secure/service-token`. Concurrent launchers publish one complete token atomically. A corrupt stored token or invalid explicit environment value fails startup instead of replacing the credential. Nonlocal authentication modes require an explicit service token. The web development process does not receive it. `scripts/run_omnix_gateway.py --check` does not create credentials.

Workers claim and finalize through `/internal/jobs`, sending the service header and the original `worker_id` and `lease_token` returned by their claim. The retired public claim/complete/fail routes return 410. A stale or expired worker cannot finalize a successor's attempt. Public `/api/jobs` admission rejects foreground job types and execution-authority compatibility fields with 422; submit chat through its chat route and direct RPG turns through their turn route. Unleased chat requires its live gateway owner. RPG audit jobs require the original started foreground submission claim, scoped to the exact workspace, session, submission and job. Their canonical turn, job result and submission commit atomically.

Agent request policies may only tighten profile ceilings for approval policy, writable paths and isolation. Repository and workspace paths must resolve under `OMNIX_AGENT_WORKSPACE_ROOTS` (platform path-list separator); defaults are the repository and `resources/agent_workspaces`. An explicitly empty setting permits no roots. Broker approval IDs are random and stay outside model-visible tool parameters and results.

## Trading safety

Trading AI and Hermes research are research inputs. They do not automatically become order authority.

Keep these layers distinct:

- market-data reads;
- charting, indicators, scanner, and replay;
- deterministic strategy/backtest logic;
- paper-account and paper-order state;
- any future live execution authority.

When investigating a trading issue, record the instrument, venue/provider binding, interval, timestamp range, strategy/replay mode, and whether the result is research, backtest, or paper simulation. Never infer live execution from a research result.

## Incident record template

Use a short, reproducible record:

    Date/time:
    Operator:
    Environment:
    Browser URL / route:
    Service topology:
    First failing endpoint or feature:
    Session ID:
    Job/run ID:
    Provider/model:
    Task revision / workspace:
    Observed status:
    Relevant logs:
    Steps already attempted:
    Expected result:
    Actual result:
    Next safe action:

The goal is to preserve enough identity to reproduce the failure without capturing secrets or widening the repair scope.

## Validation after recovery

After changing runtime state:

    python -m app.persistence verify
    npm run web:typecheck
    npm run web:test
    npm run web:build

Run the feature-specific tests and end-to-end checks relevant to the incident. Recheck the affected workspace, job/run, asset/report output, and diagnostics state. Earlier tests are stale after a code or migration change.

See also:

- [SETUP.md](SETUP.md) for installation and environment configuration.
- [ARCHITECTURE.md](ARCHITECTURE.md) for service ownership and invariants.
- [DEVELOPMENT.md](DEVELOPMENT.md) for safe implementation and testing patterns.
- [FEATURES.md](FEATURES.md) for workspace behavior.
- [../SPEC.md](../SPEC.md) for target platform rules.

## Listener policy

Omnix-managed services default to loopback. Non-loopback binding requires both
`OMNIX_BIND_HOST=<address>` and `OMNIX_ALLOW_LAN=true` and emits a startup warning.
Use `OMNIX_BIND_HOST` instead of legacy per-service listener host variables.
`OMNIX_ALLOWED_ORIGINS` is a comma-separated list of exact HTTP(S) origins;
wildcards are rejected for credential-bearing CORS.

The request guard rejects untrusted Hosts with 421, and untrusted browser
Origins or missing `X-Omnix-Client` on state-changing HTTP requests with 403.
WebSockets with untrusted Origins close with policy code 1008. Add legitimate
public hostnames to `OMNIX_ALLOWED_HOSTS` and browser origins to
`OMNIX_ALLOWED_ORIGINS`. Command-line mutation requests must send
`X-Omnix-Client: cli`. This header is a request guard, not authentication.

## Sign-in and sessions

`OMNIX_AUTH_MODE` selects how the gateway authenticates requests:

| Value | Behaviour |
|---|---|
| unset | No sign-in, as before. The gateway logs `authentication_not_enforced` at startup. |
| `local` | Sign-in required. One local owner account (`user:local`) signs in with the install credential or a launcher link. |
| `oidc` | Sign-in through your identity provider (Authorization Code + PKCE). API clients may send `Authorization: Bearer <access token>`. |
| `disabled` | No sign-in. Startup fails unless `OMNIX_ENV=test`, or `OMNIX_ENV=development` with a loopback `OMNIX_BIND_HOST`. |

Leaving the variable unset keeps existing installations working unchanged.
Making `local` the default is a separate, approved change (roadmap WP-4.1).

When sign-in is required, every route needs a session except `/health`,
`/ready`, `/api/health` and `/api/auth/*`. Unauthenticated requests get 401;
WebSockets close with code 1008. Internal `/internal/*` routes accept the
service token instead. Until run-scoped tokens land (WP-4.6), the Pi agent
extensions reach their broker and model-gateway routes from loopback without a
session.

Sessions use the `omnix_session` cookie (HttpOnly, `SameSite=Strict`). They end
after 12 idle hours (`OMNIX_AUTH_SESSION_IDLE_HOURS`) or 7 days
(`OMNIX_AUTH_SESSION_MAX_DAYS`), whichever comes first. When the browser
reaches Omnix over HTTPS (directly or through an ingress that sends
`X-Forwarded-Proto: https`) the cookies are `Secure` and the session cookie is
named `__Host-omnix_session`, which no other host or path can set or read;
`OMNIX_AUTH_COOKIE_SECURE=true` forces this for every request. Browser
requests that change state must echo the `omnix_csrf` cookie in
`X-Omnix-CSRF`; the web app does this automatically. Missing or wrong values
get 403 `csrf_failed`.

Settings → Overview lists the signed-in user's sessions
(`GET /api/auth/sessions`). Signing out one other session or all others
(`POST /api/auth/sessions/revoke`) needs proof of identity again: the install
credential in local mode, a sign-in within the last 10 minutes in OIDC mode.
It shares the sign-in rate limit and is audited (`auth.sessions.revoked`).
Sign-out answers `Clear-Site-Data: "cache", "storage"`, so the browser drops
what the app stored locally.

Disconnecting a tool account (Settings → Tools, or
`POST /api/assistant/tools/connect/{tool_id}/disconnect`) deletes its stored
OAuth token and revokes the grant at the provider: Google once no other Google
tool uses the grant, GitHub with the OAuth app's client credentials. When the
provider cannot be reached, the token is still deleted and the reply says to
revoke Omnix's access in the provider's account settings.

### Local mode

On first start the gateway creates a random install credential. The plaintext
is kept in the protected secret store (DPAPI on Windows, a 0600 file on POSIX);
the database keeps only a scrypt hash.

- **Launcher:** **Open app** signs the browser in through a single-use link
  that expires after 60 seconds.
- **By hand:** open `/login` and paste the credential that
  `python -m app.security show-install-credential` prints. The command works
  only from an interactive console.
- **Other single-use codes:** `python -m app.security login-code` prints one.
  Open `/api/auth/local/callback?code=<code>` within 60 seconds.
- **Rotate:** `python -m app.security rotate-install-credential` replaces the
  credential and signs out every local session. If the protected copy is
  deleted, the next gateway start replaces it the same way.

### OIDC mode

Required settings:

- `OMNIX_OIDC_ISSUER`: HTTPS, except on loopback.
- `OMNIX_OIDC_CLIENT_ID`.
- `OMNIX_OIDC_REDIRECT_URI`: `<public origin>/api/auth/oidc/callback`.

Optional settings:

- `OMNIX_OIDC_CLIENT_SECRET`, for confidential clients.
- `OMNIX_OIDC_SCOPES`.
- `OMNIX_OIDC_API_AUDIENCE`, to accept bearer access tokens.
- `OMNIX_OIDC_ALLOWED_DOMAINS`, which requires a verified email in one of the
  listed domains.
- `OMNIX_OIDC_REQUIRED_GROUP` and `OMNIX_OIDC_GROUPS_CLAIM`.

New users are added to `OMNIX_OIDC_WORKSPACE_ID` with
`OMNIX_OIDC_DEFAULT_ROLE`, which is `member` or `viewer`. Grant higher roles
explicitly. Accounts are matched by issuer and subject, never by email.

Every successful sign-in, failed attempt, sign-out and credential rotation is
written to `omnix_audit_events`.

### Workspaces

Each request runs in one workspace:

- **Signed in:** the user's default workspace, or the one named in the
  `X-Omnix-Workspace` header if the user is an active member of it. A
  workspace the user does not belong to gets 403 `workspace_access_denied`.
- **Sign-in off:** the local workspace.

Job workers run jobs from every active workspace, each in its own workspace.

### Roles and permissions

Each workspace membership has roles: `owner`, `admin`, `member`, `approver`
(adds approvals) and `viewer` (read-only). Every route requires a permission
from the catalog; a missing one gets 403 `permission_denied` naming the
permission. The full table is `docs/security/PERMISSIONS.md`. With
sign-in off the local user is `owner`, so nothing changes for local installs.

Approvals are made by people. Approving or denying a tool proposal needs
`tools:approve`; approving an agent run, task graph or workflow step needs
`agent:approve`. Service tokens, workers and agent runs can never approve,
and every approval records who made it. Approving your own tool proposal is
limited by `OMNIX_APPROVAL_SELF_ALLOWED_MAX_RISK` (`none`, `low`, `medium` or
`high`): the default is `high` with sign-in off (one local user) and `low`
with sign-in on.

The launcher control app (port 5055) does not ask you to sign in. It is an
operator surface and refuses every non-loopback client.

## Gateway hardening

- Every gateway response carries security headers: `nosniff`, no referrer,
  no framing, a Permissions-Policy that allows only the microphone and screen
  capture, and a Content-Security-Policy. Behind HTTPS (or
  `X-Forwarded-Proto: https`) the gateway also sends HSTS.
- Sign-in attempts are limited to 5 per minute per client address
  (`OMNIX_LOGIN_RATE_LIMIT_PER_MINUTE`). Approve, deny and execute calls are
  limited to 60 per minute per user (`OMNIX_APPROVAL_RATE_LIMIT_PER_MINUTE`).
  Limits apply per gateway process.
- `/docs`, `/redoc` and `/openapi.json` require the `admin:docs` permission
  unless `OMNIX_ENV` is `development` or `local`.
- Model server URLs (LM Studio, llama.cpp, Parakeet) are checked when saved
  and before each request. Link-local and cloud metadata addresses are
  always refused. Private network addresses are allowed while sign-in is off.
  With sign-in on, list them in `OMNIX_ALLOWED_PRIVATE_NETWORKS` (CIDRs,
  comma-separated).
- llama.cpp: Omnix stops only the server it started. If the configured port
  is already in use, it reports the conflict instead of killing the other
  process. Model files must be inside the models directory.

## Audit trail

Sensitive actions are recorded in `omnix_audit_events` with the acting user,
the workspace and the outcome (`success`, `failure` or `denied`). Recorded actions:

- sign-in, sign-out and failed sign-ins;
- settings changes and tool connection secrets;
- approval decisions (tool proposals, agent runs, task graphs, workflows,
  chat confirmations);
- every capability execution;
- agent run start, stop and promotion;
- trading control changes and paper orders;
- feature toggles and workspace administration.

Details never contain prompts, messages or secrets. The table is append-only:
rows cannot be updated or deleted, even by the database owner. Deleting a
workspace keeps its audit rows (the workspace reference becomes empty).
Retention runs through the maintenance path (planned).

## Agent run tokens

An agent's Pi process talks to the broker and the model gateway with a token
that belongs to its run (`Authorization: OmnixRun <token>`). The token names
the run, its workspace and the process that owns it, lasts 15 minutes and is
renewed while the run is active. It stops working when the run finishes, its
capabilities change or another process takes the run over. A run id alone,
or a signed-in browser session, is refused on these routes. Pi's extensions
remove the token from their environment before any tool runs, so shell
commands never see it.

Every Omnix process of an installation must share the signing key. The
launcher's service token provides it; otherwise set `OMNIX_RUN_TOKEN_KEY` (at
least 32 characters) on every gateway and worker. `scripts/gateway_cluster.py`
generates one shared key for its replicas when neither is set.

## Agent request ceilings

Public agent-run requests may tighten the selected profile's approval policy;
`allow_automatic` is rejected when the profile default is `ask_sensitive`.
Allowed file patterns must remain within the profile ceiling, and isolation
cannot be lowered. Reviewer requests use immutable review snapshots.

Both `repository` and `workspace_root` must resolve under operator-approved
roots. `OMNIX_AGENT_WORKSPACE_ROOTS` is a path list separated by `;` on Windows
or `:` on POSIX. The default roots are the repository and
`resources/agent_workspaces`. Empty configuration denies every root. Relative
configured roots are anchored to the repository; request roots must be absolute.
Resolved symlinks and parent traversal are checked before a run starts.
The same roots bound the local folders attached to Chat agent runs and any
workspace an agent changes in place.

## Agent sandbox

Agent runs that can change their workspace (the `coding` and `ops` profiles)
run in a Docker sandbox: read-only, without capabilities, with resource
limits, a private home and a network that reaches only the broker. Build its
image once per host, then check it:

```powershell
$env:PYTHONPATH = "src"
python -m app.agent_runtime.sandbox build
python -m app.agent_runtime.sandbox check-egress   # exits 1 if the sandbox can reach anything but the relay
```

Without Docker or the image, such a run fails with the reason. To run them
unsandboxed instead (every command then asks for approval, each run is audited
and shows a warning), set `OMNIX_AGENT_ALLOW_UNSANDBOXED=true`. On Windows
hosts, dependencies installed on the host (node_modules, virtualenvs) do not
run in the Linux sandbox: give projects that validate with them a sandbox image
with their toolchain (`OMNIX_AGENT_DOCKER_IMAGE`), or use the override. At most
`OMNIX_AGENT_MAX_CONCURRENT_RUNS` (default 2) agents run at once. Details:
[security/AGENT_SANDBOX.md](security/AGENT_SANDBOX.md).
