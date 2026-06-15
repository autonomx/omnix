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

## Phases left

### Phase 20 — Data preservation expansion

Goal: finish compatibility read-through or import diagnostics for every legacy data family.

Remaining work:

- Prove old STT/TTS generated audio remains discoverable through shared assets.
- Prove podcast, story, and generic exported files remain discoverable through shared assets.
- Add explicit dry-run/import diagnostics for non-image asset families where read-through alone is not enough.
- Add more settings and secrets preservation tests, especially masked API-key round trips and provider-cache invalidation behavior.

### Phase 21 — Full GPU/model residency scheduler

Goal: move beyond resource-aware scheduler v1 into durable model residency accounting.

Remaining work:

- Track loaded models, estimated VRAM, and owning worker process.
- Add load/evict transition jobs and event records.
- Prevent unsafe GPU co-residency while allowing compatible local GPU work to share capacity when explicitly allowed.
- Surface scheduler state in Diagnostics and Jobs.

### Phase 22 — Legacy backend compatibility cleanup

Goal: make compatibility routes intentional and auditable rather than accidental leftovers.

Remaining work:

- Inventory every remaining `run_app.py` compatibility endpoint.
- Mark each endpoint as keep, wrap, migrate, or remove.
- Add tests for endpoints that must remain during the transition.
- Remove dead compatibility surfaces only after the new gateway route has equivalent coverage.

### Phase 23 — Provider/model live refresh and diagnostics

Goal: make provider/model registry state observable without instantiating heavy providers in the gateway.

Remaining work:

- Add explicit refresh jobs for local model discovery.
- Publish provider/model refresh events.
- Add stale/error diagnostics for missing local servers, model paths, or worker URLs.
- Keep listing operations provider-light and safe for CI.

### Phase 24 — Release packaging and endurance

Goal: make the redesigned platform reliable for local user operation.

Remaining work:

- Add a release smoke script for gateway + web + worker health.
- Add longer job/event endurance checks.
- Add backup/restore guidance for `resources/data`.
- Add operator-facing troubleshooting for CI artifacts, gateway logs, worker logs, and model downloads.

## Current rule

All remaining work should continue as narrow branches against `rpg`, with PRs merged only after `RPG Phase 0 architecture compliance` and `RPG deterministic PR gates` pass on the exact PR head SHA.
