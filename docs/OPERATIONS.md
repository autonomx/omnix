# Omnix Operations Guide

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

## Startup runbook

### Separate process mode

1. Start PostgreSQL:

       docker compose -f docker-compose.postgres.yml up -d

2. Set the database URL. PowerShell:

       $env:OMNIX_DATABASE_URL = 'postgresql://omnix:<password>@127.0.0.1:5432/omnix'

   Bash or WSL:

       export OMNIX_DATABASE_URL='postgresql://omnix:<password>@127.0.0.1:5432/omnix'

3. Install dependencies and apply migrations:

       pip install -r requirements.txt
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

start_all.bat can coordinate PostgreSQL, the gateway, optional workers, Hermes, and the browser. Treat workstation-specific Python/Conda paths in that script as operator configuration. The portable contract is the service URLs and environment variables, not a particular absolute path.

Use the launcher dashboard at http://127.0.0.1:5055 to inspect or control services when the launcher is configured. The launcher can auto-start optional services; keep auto-start flags explicit when diagnosing startup order.

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

## Triage decision tree

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

For a local backup, use the PostgreSQL tooling appropriate to your environment and keep the output outside the repository. Example:

    pg_dump --dbname="$OMNIX_DATABASE_URL" --format=custom --file=omnix-backup.dump

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

## Secrets and networked integrations

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
