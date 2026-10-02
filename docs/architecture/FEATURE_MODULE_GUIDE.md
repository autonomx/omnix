# FeatureModule guide

A feature is an optional Omnix capability (audiobook, image, trading, …) that the gateway composes from a declaration. The catalog at `app.runtime.feature_catalog.FEATURE_CATALOG` is the only list of features. Audiobook (`src/app/audiobook/`) is the reference implementation: copy its structure, and use the checklist at the end to review a new feature.

## Composition

A feature package exposes `feature.py` with one `FEATURE = FeatureModule(...)` value and a catalog entry pointing at it (`"audiobook": "app.audiobook.feature:FEATURE"`). The declaration is all the gateway knows about the feature:

| Field | Use |
|---|---|
| `routers` | Router factories for the public HTTP and WebSocket API. |
| `internal_routers` | Service-token or other internal HTTP surfaces only. |
| `background_workers` | Long-running loops owned by the background runtime. |
| `job_handlers` | Durable jobs executed by the shared durable worker. |
| `scheduled_tasks`, `outbox_consumers`, `hooks` | Periodic work, outbox delivery and runtime hooks. |
| `repositories`, `settings`, `permissions` | Persistence, configuration and permission declarations. |
| `depends_on`, `requires` | Other features and runtime capabilities the feature needs. |

Factories receive a `FeatureContext` (runtime configuration, capabilities, kernel services, a feature logger). A feature never imports the gateway composition root and never patches other packages at import time.

`OMNIX_FEATURES` and `OMNIX_FEATURES_DISABLED` control enablement. Startup fails if an enabled feature depends on a disabled one. A disabled feature's modules are not imported, and its routes and job handlers are absent, while kernel health and readiness routes stay available (`src/tests/app/test_feature_matrix.py` checks every optional feature).

## Package layout

| Module | Owns | Audiobook |
|---|---|---|
| `feature.py` | The declaration and nothing else. | `audiobook/feature.py` |
| `routes.py` | HTTP: request models, status codes, streaming bodies. | `audiobook/routes.py` |
| `service.py` | Workflow decisions and transaction boundaries. No SQL. | `audiobook/service.py` |
| `*_repository.py` | Every SQL statement, one method per intent. | `audiobook/project_repository.py`, `repository.py`, `review_repository.py`, `analysis_repository.py`, `document_structure_repository.py` |
| job modules | Claiming and executing durable jobs. | `audiobook/worker.py`, `render_service.py`, `assembly_service.py`, `export_service.py` |

### Routes

- A module-level `router = APIRouter()` with module-level handler functions; the router factory in `feature.py` returns it. No handlers defined inside a factory function.
- Request bodies are Pydantic models. Keep existing public URLs when restructuring.
- Handlers translate domain exceptions to status codes (`KeyError` → 404, validation `ValueError` → 422, state conflicts → 409). They hold no business logic.
- Blocking work runs off the event loop: plain `def` handlers run in the threadpool; `async def` handlers call blocking services through `asyncio.to_thread`.
- Uploads are read as a stream with a hard cap that also holds for chunked bodies without a Content-Length, and large bodies spill to a temporary file instead of memory (`_spool_body`). Declare the raw body for the OpenAPI contract with `openapi_extra` (`_octet_stream_body`).
- Downloads stream from the blob store (`StreamingResponse`) with integrity verification.

### Service and repositories

- The service opens a `unit_of_work`, takes the locks a decision needs, and commits once. It never calls `connection.execute`.
- Repositories take the connection, filter every statement by `workspace_id`, and return rows; methods are named by what they mean (`lock_render_settings`, `reset_render`), not by the SQL.
- Feature tables carry `workspace_id` and are covered by row-level security (migration `0106_row_level_security.sql`). Schema changes are forward migrations with a checksum entry in `resources/architecture/migration-checksums.json`; a new JSONB column read by queries needs a decision in `resources/architecture/jsonb-decisions.json`.
- Assets and blobs go through the platform stores (`work.assets`, `BlobStore`); `put_stream` stores large content in bounded memory.

### Durable jobs and background work

- Prefer `job_handlers` on the shared durable worker: it claims, renews leases and handles cancellation for you.
- A feature that needs its own claim loops (audiobook does: render jobs checkpoint per synthesized unit and yield to higher-priority speech) follows the audiobook lease pattern:
  - claim with a short lease (`leases.JOB_LEASE_SECONDS`, two minutes) and run the claimed job inside `lease_heartbeat`, which renews it every 30 seconds, so a crashed worker's job is reclaimable quickly;
  - publish results only in transactions that renew the lease with the job's own worker id and lease token, so a worker that lost its lease cannot publish;
  - make retries resume from durable checkpoints rather than restart.
- A background worker is a small class with `start` and `stop`, declared through `background_workers` with the capability it needs (`RuntimeCapability.RUN_JOB_WORKERS`). Its loops call `require_background_owner()` before each claim and exit when ownership is revoked; `stop` joins its threads within a deadline.

### Providers

Depend on provider ports, not on a concrete provider module. Audiobook asks `app.providers.tts_artifacts.local_model_artifacts(provider_id)` where the installed TTS model lives (to pin renders to a model revision) and `app.providers.service.get_tts_provider` for synthesis. Import heavy provider code on demand so registering the feature's routes stays cheap.

### Permissions

Add the feature's read and write permissions to `app.security.permissions` (`CATALOG`, `FEATURE_DEFAULTS`, and `WEBSOCKET_PERMISSIONS` for sockets). Feature routes are guarded by `feature_permission_guard`: reads need the read permission, everything else the write permission, unless a route declares its own with `requires(...)`.

## Tests

- Unit tests fake the seams: `unit_of_work` or the repository for services, the service for routes (`_service_and_context`), the claim functions for workers.
- PostgreSQL integration tests run the real SQL, migrations and row-level security (`src/tests/persistence/test_audiobook_*.py`).
- Route tests cover status mapping and streaming limits (`src/tests/unit/audiobook/test_routes.py`, `test_uploads.py`).
- The feature matrix test proves the feature can be disabled.

## Checklist

| # | Requirement | Audiobook |
|---|---|---|
| 1 | One `FEATURE` declaration and a catalog entry. | `feature.py`; `FEATURE_CATALOG["audiobook"]` |
| 2 | Disabling the feature removes its routes and workers; kernel routes remain. | `test_feature_matrix.py` |
| 3 | Module-level routes; no handlers defined in closures. | `routes.py` |
| 4 | Request models for request bodies; existing URLs preserved. | `routes.py`; OpenAPI unchanged by WP-8.7 |
| 5 | No SQL in the service; every statement in a repository and scoped by workspace. | `service.py` has no `execute`; `project_repository.py` |
| 6 | Feature tables under row-level security; forward migrations only. | `0085`–`0106` |
| 7 | Uploads streamed with a hard cap; downloads streamed. | `_spool_body`, `submit_source(content=stream)`, `StreamingResponse` |
| 8 | Durable jobs with short leases, renewal, and lease-fenced writes. | `leases.py`; fenced `renew_lease` at each checkpoint |
| 9 | Background loops start and stop with background ownership. | `_AudiobookWorkers`; `test_audiobook_background_ownership.py` |
| 10 | Providers reached through ports, imported on demand. | `model_identity.py` → `tts_artifacts` |
| 11 | Read and write permissions declared. | `audiobook:read`, `audiobook:write` |
| 12 | Unit, route and PostgreSQL integration tests. | `src/tests/unit/audiobook/`, `src/tests/persistence/test_audiobook_*.py` |

Not yet part of the reference: typed response models. Audiobook routes return dictionaries, so their OpenAPI response schemas are generic; new features should declare `response_model`s.
