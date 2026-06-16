# `run_app.py` Compatibility Route Inventory

Last updated: 2026-06-15

`apps/web` plus `app.gateway.main:app` are the supported browser platform.
`src/run_app.py` remains a compatibility backend for legacy voice, audiobook,
image, and RPG runtime surfaces while gateway equivalents are proven.

## Classification Rules

The route guard in `src/tests/api/test_legacy_ui_retirement.py` classifies every
mounted `run_app.py` route. New routes must fit one of these classifications or
the guard fails.

| Classification | Scope | Status |
| --- | --- | --- |
| `framework-docs` | `/docs`, `/docs/oauth2-redirect`, `/redoc`, `/openapi.json` | Keep as FastAPI defaults while `run_app.py` exists. |
| `backend-status` | `/`, `/health`, `/api/health`, `/api/runtime/status`, `/api/services/status` | Keep until process supervision moves fully behind gateway/launcher docs. |
| `runtime-data` | `/generated-images/{filename:path}` | Keep. Generated media is runtime data, not classic UI static source. |
| `legacy-settings` | `/api/settings` | Wrap/migrate. Gateway `/api/settings` already preserves core settings behavior. |
| `legacy-sessions` | `/api/sessions*` | Wrap/migrate. Gateway session compatibility exists for core CRUD/title fallback. |
| `legacy-rpg` | `/api/rpg*`, root-level RPG setup helpers such as `/setup-flow` and `/session-bootstrap` | Migrate gradually. Deterministic read routes have gateway bridges; live turn, mutation, presentation, and authoring routes remain compatibility surfaces. |
| `legacy-image` | `/api/image*` | Migrate behind shared jobs/assets/providers before removal. |
| `legacy-voice` | `/api/tts*`, `/api/stt*`, `/api/voice*`, `/api/voice_*`, `/ws/conversation`, `/ws/tts` | Migrate behind shared jobs/assets/workers before removal. |
| `legacy-podcast-story-audiobook` | `/api/podcast*`, `/api/story*`, `/api/audiobook*`, `/ws/audiobook` | Migrate behind shared jobs/assets before removal. |
| `legacy-provider-models` | `/api/openrouter*`, `/api/providers*`, `/api/models`, `/api/llm*`, `/api/llamacpp*` | Migrate behind provider/model facade and refresh diagnostics. |
| `legacy-chat-control` | `/api/chat*`, `/api/conversation*`, `/api/clear` | Migrate behind shared chat/jobs/session contracts before removal. |
| `legacy-service-logs` | `/api/services/xtts/logs`, `/api/services/stt/logs` | Keep until worker logging diagnostics replace direct service log proxies. |

## Removal Rule

Do not remove a compatibility route only because `apps/web` no longer uses it.
First prove a gateway or worker equivalent exists, add regression coverage for
that equivalent, then remove or redirect the legacy route in a separate slice.
