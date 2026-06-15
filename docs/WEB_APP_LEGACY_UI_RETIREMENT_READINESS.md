# Web App Legacy UI Retirement Readiness

Last updated: 2026-06-15

Phase 18 is the classic browser UI retirement pass. The shared React/Vite app
under `apps/web` is now the supported browser UI. Backend compatibility routes
may remain while they are migrated into typed gateway contracts, but the
template/static browser shell is retired.

## Target Startup Path

For new browser-facing development, use the shared web app:

```powershell
npm.cmd run web:dev
```

The Vite dev server runs on port `5173` and proxies `/api` and `/events` to the
FastAPI gateway configured in `apps/web/vite.config.ts`.

For gateway development, start the gateway separately:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

`src/run_app.py` is no longer a browser app entrypoint. It can still be started
for backend compatibility routes and generated media while older scripts are
unwound:

```powershell
python src/run_app.py
```

`GET /` returns backend status JSON that points browser users to `apps/web`;
`/static/*` and `/logo/*` are not mounted as classic UI routes.

## Current Compatibility Surfaces

Retired classic browser entrypoints:

- `src/run_app.py` no longer serves the classic HTML shell from `/`.
- `src/run_app.py` no longer mounts `/static/{path}` or `/logo/{path}`.
- `src/templates/index.html` and `src/static/` have been deleted from the Phase
  18 branch.
- Legacy static-source inspections are skipped by default in
  `src/tests/conftest.py`; set `OMNIX_RUN_RETIRED_LEGACY_UI_TESTS=1` only when
  intentionally auditing archived classic UI files.

Still-active backend/data compatibility surfaces:

- `/generated-images/{filename}` remains available from `src/run_app.py`
  because generated images are user/runtime data, not classic UI chrome.
- `src/tests/conftest.py` still provides older Flask/page-object fixtures for
  backend compatibility tests until those suites are migrated or retired.
- Selected `/api/rpg/*`, `/api/settings`, and `/api/sessions` flows remain
  covered through gateway compatibility routes or backend-only compatibility
  tests.

## Retirement Blockers

The classic browser UI does not need to stay available. Remaining Phase 18 work
is about proving that deletion does not orphan data or hide backend regressions:

- Legacy Flask/FastAPI routes used by tests are either migrated to the shared
  gateway or explicitly documented as backend-only compatibility routes.
- Existing saves, settings, generated images, reports, voice assets, and RPG
  checkpoints are covered by compatibility or migration tests.
- Startup docs consistently name `apps/web` plus the FastAPI gateway as the
  supported browser path.

## Retirement Progress

- 2026-06-15: `/api/settings` is bridged through the shared gateway. `GET`
  remains a sanitized platform settings summary for `apps/web`, also includes a
  legacy-compatible `{ success, settings }` envelope with masked API keys, and
  `POST` preserves the legacy mutation split between settings and secrets.
- 2026-06-15: legacy `/api/sessions` CRUD and `/api/sessions/generate-title`
  fallback are bridged through the shared gateway. The gateway preserves the
  legacy response envelopes, session file semantics, newest-first session list,
  and update/delete behavior without introducing provider calls into the gateway.
- 2026-06-15: low-risk RPG adventure-builder compatibility routes are bridged
  through the shared gateway: `GET /api/rpg/adventure/templates`,
  `POST /api/rpg/adventure/validate`, and
  `POST /api/rpg/adventure/preview`. These delegate to deterministic creator
  preview helpers and intentionally exclude adventure start, regeneration, live
  turns, and model-backed flows.
- 2026-06-15: RPG session inspection compatibility routes are bridged through
  the shared gateway: `POST /api/rpg/session/list` and
  `POST /api/rpg/session/get`. These preserve the legacy JSON envelopes for
  session list, missing-session-id, missing-session, and frontend bootstrap
  payloads without mounting the full RPG API routers or live turn mutations.
  Frontend OpenAPI/types are regenerated and covered by the shared generated
  route smoke test.
- 2026-06-15: RPG inspector read routes are bridged through the shared gateway:
  `POST /api/rpg/inspect/timeline`,
  `POST /api/rpg/inspect/timeline_tick`,
  `POST /api/rpg/inspect/tick_diff`,
  `POST /api/rpg/inspect/npc_reasoning`, and
  `POST /api/rpg/inspect/world_events`. These delegate to deterministic
  analytics helpers and intentionally exclude GM force/debug mutations.
  Frontend OpenAPI/types are regenerated and covered by the shared generated
  route smoke test.
- 2026-06-15: RPG player-facing read routes are bridged through the shared
  gateway: `POST /api/rpg/player/state`, `POST /api/rpg/player/journal`,
  `POST /api/rpg/player/codex`, `POST /api/rpg/player/objectives`, and
  `POST /api/rpg/player/encounter`. These delegate to deterministic player
  state and encounter view helpers and intentionally exclude dialogue
  transitions, inventory mutations, equipment changes, progression allocation,
  and session persistence. Frontend OpenAPI/types are regenerated and covered by
  the shared generated route smoke test.
- 2026-06-15: RPG adventure-builder diagnostic routes are bridged through the
  shared gateway: `POST /api/rpg/adventure/inspect-world`,
  `POST /api/rpg/adventure/inspect-world-snapshot`,
  `POST /api/rpg/adventure/compare-world`,
  `POST /api/rpg/adventure/compare-entity`,
  `POST /api/rpg/adventure/simulate-step`, and
  `POST /api/rpg/adventure/simulation-state`. These delegate to deterministic
  world inspection/simulation helpers and intentionally exclude adventure start,
  regeneration, generated package application, scene narration, and LLM-backed
  NPC filling. Frontend OpenAPI/types are regenerated and covered by the shared
  generated route smoke test.
- 2026-06-15: `src/run_app.py` no longer serves the classic browser shell.
  `GET /` returns backend status JSON, `/static/*` returns 404, and the
  gateway compatibility metadata reports the legacy UI as `retired`. Static JS
  source-inspection tests are skipped by default as retired classic UI coverage;
  backend compatibility tests and generated frontend API type checks remain the
  active safety net.

## Freeze Rule

Do not add user-facing behavior to `src/templates` or `src/static`. Those files
are retired classic UI sources and should only be touched to complete deletion
or preserve access to non-UI user data through backend compatibility paths.

## Safe Next Slices

- Add representative data compatibility tests for saves, settings, generated
  images, reports, voice assets, and RPG checkpoints.
- Continue migrating selected remaining `/api/rpg/*` backend flows into typed
  gateway contracts only when active workflows need them.
