# Omnix Web App Redesign — Phases Left

Last updated: 2026-06-15

This note tracks what is still left after the current web-platform hardening work. The redesign baseline is no longer the early scaffold: the React/TanStack/Mantine shell, FastAPI gateway, generated API types, shared jobs, providers/models facade, shared assets, reports, diagnostics, replay wrappers, event stream, and CI-backed web checks are in place.

## Completed or materially hardened

- Required `rpg` PR CI now runs consistently and uploads downloadable failure artifacts.
- Gateway SSE lifecycle events have live streaming, ids, heartbeats, and resume support.
- The web event client handles reconnects, cursor resume, malformed events, close/reset semantics, and query normalization.
- Jobs, Assets, Reports, and Diagnostics refresh from job lifecycle events with focused Vitest coverage.
- OpenAPI drift is guarded in CI against the checked-in generated web schema.
- Web typecheck and Vitest are part of the required deterministic gate.
- Image assets have explicit shared-asset import diagnostics.
- Existing voice clone profiles are exposed through shared asset read-through without mutating legacy data.
- Existing generated STT/TTS audio files are exposed through shared asset read-through without mutating legacy data.
- Non-image legacy asset families now have read-only dry-run diagnostics for
  voice profiles, generated audio, and document artifacts. The dry-run reports
  scanned roots, category counts, collisions with shared manifest records,
  skipped unsupported files, and import candidates without mutating legacy files
  or shared manifests.
- Settings preservation now covers worker URLs, audio provider selection/config,
  local model path settings, and nested image/RPG visual options while keeping
  provider secrets in the protected secrets file and preserving provider-cache
  invalidation boundaries.

## Phases left

### Phase 20 — Data preservation expansion

Status: locally complete.

Goal: finish compatibility read-through or import diagnostics for every legacy data family.

Completed locally:

- Podcast, story, report, transcript, run-log, and generic exported documents
  remain discoverable through shared asset read-through.
- Image assets have explicit import diagnostics.
- Voice clone, generated audio, and document artifact families have read-only
  dry-run diagnostics.
- Settings/config preservation covers provider secrets, worker URLs, audio
  provider config, local model path settings, and nested image/RPG visual
  options.

### Phase 21 — Full GPU/model residency scheduler

Goal: move beyond resource-aware scheduler v1 into durable model residency accounting.

Completed locally:

- Added a pure GPU residency planner with deterministic decisions for
  non-GPU bypass, conservative single-GPU behavior, compatible co-residency,
  unknown-VRAM safety, model transition queuing, and errored model diagnostics.
- Added model load/evict transition job request helpers so residency transitions
  can appear in the shared Jobs system before worker integration.
- Added a provider-light `model_residency` Diagnostics payload section and
  surfaced it in the web Diagnostics module.
- Added a durable SQLite model residency store for worker-reported model state
  keyed by `model_id`, including worker/status indexes, restart-safe records,
  delete/unload cleanup, and Diagnostics integration through the gateway app.
- Wired the residency planner into the SQLite job store's optional claim path:
  when live residency records are supplied, claim selection skips GPU jobs that
  require eviction/queue/blocking and only permits compatible active-GPU
  co-residency under an explicit co-residency policy.
- Added local executor handlers for `model.load` and `model.evict` transition
  jobs. The handlers update the durable residency store, preserve worker ids
  from the lease/payload, complete through the shared job store, and emit normal
  terminal job events.
- Load/evict handlers now accept real provider process-control hooks, record
  `loading`/`unloading` before hook invocation, preserve hook logs/output refs,
  and persist `error` residency state while failing the shared job when a hook
  raises.
- Added concrete worker model-control hooks for runtimes that expose
  `/provider/load` and `/provider/unload` endpoints, including the standalone
  image worker shape. The hooks post provider/model/job metadata to the worker,
  preserve worker responses in job output refs, and compose with the shared
  `model.load`/`model.evict` executor path.
- Added OpenAPI-backed `/api/model-residency` read/report/delete routes so live
  workers can report load/unload/error state into the durable residency store;
  regenerated the checked-in gateway schema and web TypeScript API surface.

Remaining work:

- Gather live-worker evidence with a real process-control runtime configured.

### Phase 22 — Legacy backend compatibility cleanup

Goal: make compatibility routes intentional and auditable rather than accidental leftovers.

Completed locally:

- Added `docs/WEB_APP_RUN_APP_COMPATIBILITY_ROUTES.md` with classifications for
  every remaining `src/run_app.py` route family.
- Added a route-classification guard that fails if a newly mounted
  compatibility route is not assigned to an explicit status bucket.
- Added a must-remain route guard for representative backend status, runtime
  data, settings, sessions, RPG, image, voice, podcast/audiobook, provider,
  chat, and service-log compatibility surfaces.

Remaining work:

- Remove dead compatibility surfaces only after the new gateway route has equivalent coverage.

### Phase 23 — Provider/model live refresh and diagnostics

Goal: make provider/model registry state observable without instantiating heavy providers in the gateway.

Completed locally:

- Added a provider-light model/cache status service that reports configured
  remote models, local model paths, worker URL configuration, missing local
  paths, and diagnostics without instantiating providers or performing network
  calls.
- Added `provider_model_cache` to the Diagnostics payload and surfaced its
  status in the web Diagnostics module.
- Added explicit provider/model refresh job endpoints backed by the shared
  durable job queue, with CPU-only discovery stages, typed OpenAPI/web client
  coverage, and normal job lifecycle events for provider/model refreshes.
- Providers and Models web modules can enqueue refresh jobs and refetch from
  shared job lifecycle events alongside Jobs and Diagnostics.
- Provider/model cache diagnostics now actively classify configured local
  provider servers and worker URLs as unreachable via a short, provider-light
  reachability probe, with deterministic tests using an injected probe.
- Added provider/model refresh executor handlers that run provider-light
  discovery through the shared job system, persist timestamped SQLite refresh
  snapshots with provider/model counts, cache status, diagnostics, and payloads,
  and complete or fail through normal shared job terminal events.

Remaining work:

- Attach the refresh handler to the optional external worker deployment and
  gather live-worker evidence that refresh history updates under real provider
  settings without making gateway listing operations instantiate heavy models.

### Phase 24 — Release packaging and endurance

Goal: make the redesigned platform reliable for local user operation.

Completed locally:

- Added `scripts/smoke_web_platform.py`, a CI-safe smoke script for gateway
  health, mock-worker health, Diagnostics, event-stream route registration, and
  checked-in OpenAPI drift. Optional web checks run typecheck, Vitest,
  `api:check`, and the Vite build.
- Added backend-mode smoke coverage and release-runbook guidance.
- Added bounded job-event endurance coverage for many events, history limits,
  resume cursors, and terminal event visibility.
- Added `scripts/live_worker_endurance.py`, an opt-in live-worker evidence
  collector that refuses to run without `--allow-live`, repeatedly samples
  configured worker health, and writes timestamped JSON artifacts under
  `resources/data/test-results/web-platform-live-worker-endurance/`.
- Expanded backup/restore and troubleshooting guidance for `resources/data`,
  shared asset manifests, settings/secrets, worker health, model cache
  diagnostics, and local smoke commands.
  The runbook now includes the live-worker endurance command and artifact
  expectations.

Remaining work:

- Run the opt-in live-worker endurance collector against real configured
  workers and attach the resulting artifact.

## Current rule

All remaining work should continue as narrow branches against `rpg`, with PRs merged only after `RPG Phase 0 architecture compliance` and `RPG deterministic PR gates` pass on the exact PR head SHA.
