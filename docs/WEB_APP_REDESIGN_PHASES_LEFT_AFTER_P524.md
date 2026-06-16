# Omnix Web App Redesign — Phases Left After P524

Last updated: 2026-06-15

## Completed in this slice

- Settings preservation now has focused backend regression coverage.
- Masked provider credentials can round-trip through `/api/settings` without replacing the stored value.
- Newly supplied provider credentials are saved in the protected configuration file rather than in normal provider settings.
- Provider-cache invalidation is covered for provider-affecting changes and protected from unrelated prompt-only settings edits.

## Completed locally after P524

- Non-image legacy asset families have read-only dry-run diagnostics through
  `/api/assets/migrations/legacy-non-image/dry-run`.
- The dry-run reports scanned voice/audio/document roots, category counts,
  manifest collision ids, skipped unsupported files, and non-colliding import
  candidates.
- Focused tests prove the dry-run does not mutate the shared manifest and keeps
  manifest-backed shared assets authoritative when legacy ids collide.
- Settings/config preservation coverage now includes worker URLs, audio
  provider selection/config, local model path settings, and nested image/RPG
  visual options without moving provider credentials out of the protected
  secrets file.

## Remaining phases

### Phase 20 — Data preservation expansion

Status: locally complete.

Completed locally:

- Non-image asset dry-run diagnostics are read-only and collision-aware.
- Settings/config preservation covers worker-local URLs, audio provider options,
  local model paths, and nested module-specific image/RPG visual options.

### Phase 21 — Full GPU/model residency scheduler

Completed locally:

- Worker model-control hooks can now call `/provider/load` and
  `/provider/unload` on runtimes that expose those endpoints, preserve worker
  responses in shared job output refs, and compose with the shared
  `model.load`/`model.evict` executor path.

Remaining work:

- Gather live-worker evidence with a real process-control runtime configured.

### Phase 22 — Legacy backend compatibility cleanup

Completed locally:

- Inventoried the remaining `run_app.py` compatibility endpoint families.
- Marked compatibility surfaces as keep, wrap, migrate, or remove in
  `docs/WEB_APP_RUN_APP_COMPATIBILITY_ROUTES.md`.
- Added guards for route classification and representative must-remain
  compatibility endpoints.

Remaining work:

- Remove dead compatibility surfaces only after the new gateway route has equivalent coverage.

### Phase 23 — Provider/model live refresh and diagnostics

Completed locally:

- Keep listing operations provider-light and safe for CI.
- Provider/model refresh jobs now have local executor handlers that run
  provider-light discovery, persist timestamped SQLite refresh snapshots with
  provider/model counts, cache status, diagnostics, and payloads, and emit
  normal shared job terminal events.

Remaining work:

- Attach the refresh handler to the optional external worker deployment and
  gather live-worker evidence that refresh history updates under real provider
  settings without making gateway listing operations instantiate heavy models.

### Phase 24 — Release packaging and endurance

Completed locally:

- Added a release smoke script for gateway + web + worker health.
- Added longer job/event endurance checks.
- Added backup guidance for `resources/data`.
- Added operator-facing troubleshooting for CI artifacts, gateway logs, worker logs, and model downloads.
- Added an opt-in live-worker endurance collector that requires `--allow-live`,
  samples configured worker health for repeated iterations, and writes
  timestamped JSON evidence artifacts outside the provider-free local gate.

Remaining work:

- Run the opt-in live-worker endurance collector against real configured
  workers and attach the resulting artifact.
