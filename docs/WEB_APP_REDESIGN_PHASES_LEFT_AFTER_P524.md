# Omnix Web App Redesign — Phases Left After P524

Last updated: 2026-06-15

## Completed in this slice

- Settings preservation now has focused backend regression coverage.
- Masked provider credentials can round-trip through `/api/settings` without replacing the stored value.
- Newly supplied provider credentials are saved in the protected configuration file rather than in normal provider settings.
- Provider-cache invalidation is covered for provider-affecting changes and protected from unrelated prompt-only settings edits.

## Remaining phases

### Phase 20 — Data preservation expansion

Remaining work:

- Add dry-run/import diagnostics for non-image asset families where read-through alone is not enough.
- Add broader preservation coverage for settings families not routed through `/api/settings`, especially worker-local configuration files and module-specific option files.

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
