# Omnix Web App Redesign — Phases Left After P523

Last updated: 2026-06-15

## Completed in this slice

- Legacy podcast scripts, story files, reports, transcripts, run logs, and generic document artifacts are exposed through shared asset read-through.
- The read-through is non-destructive: listing shared assets does not create or mutate the shared asset manifest or legacy files.
- Manifest-backed shared assets remain authoritative when an id collides with a legacy document artifact.

## Remaining phases

### Phase 20 — Data preservation expansion

Remaining work:

- Add dry-run/import diagnostics for non-image asset families where read-through alone is not enough.
- Add more settings and credential-configuration preservation tests, including masked-key round trips and provider-cache invalidation behavior.

### Phase 21 — Full GPU/model residency scheduler

Remaining work:

- Track loaded models, estimated VRAM, and owning worker process.
- Add load/evict transition jobs and event records.
- Prevent unsafe GPU co-residency while allowing compatible local GPU work to share capacity when explicitly allowed.
- Surface scheduler state in Diagnostics and Jobs.

### Phase 22 — Legacy backend compatibility cleanup

Remaining work:

- Inventory every remaining `run_app.py` compatibility endpoint.
- Mark each endpoint as keep, wrap, migrate, or remove.
- Add tests for endpoints that must remain during the transition.
- Remove dead compatibility surfaces only after the new gateway route has equivalent coverage.

### Phase 23 — Provider/model live refresh and diagnostics

Remaining work:

- Add explicit refresh jobs for local model discovery.
- Publish provider/model refresh events.
- Add stale/error diagnostics for missing local servers, model paths, or worker URLs.
- Keep listing operations provider-light and safe for CI.

### Phase 24 — Release packaging and endurance

Remaining work:

- Add a release smoke script for gateway + web + worker health.
- Add longer job/event endurance checks.
- Add backup guidance for `resources/data`.
- Add operator-facing troubleshooting for CI artifacts, gateway logs, worker logs, and model downloads.
