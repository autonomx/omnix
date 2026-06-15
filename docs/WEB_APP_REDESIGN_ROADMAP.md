# Omnix Web App Redesign Roadmap

This roadmap turns the Omnix-wide web app architecture into an implementation sequence. The goal is to move Omnix from a legacy single-page local UI plus separate model services into a coherent local-first AI workstation platform.

The roadmap is intentionally ordered to avoid the biggest risk: creating third implementations of systems that already exist in more than one form. Shared systems such as jobs, providers, assets, prompts, replay, diagnostics, and worker health should be consolidated from existing code before new feature modules depend on them.

This roadmap is also ordered to avoid a second risk: building backend contracts before the type-generation path exists. A minimal FastAPI gateway and OpenAPI type generation must land early enough that later backend consolidation phases can publish typed contracts as they are built.

## Implementation Status

Last updated: 2026-06-15

| Phase | Status | Evidence |
| --- | --- | --- |
| Phase 0 - Architecture Design Hardening | Implemented | `docs/WEB_APP_INFRASTRUCTURE.md` now records as-built drift, target stack decisions, the FastAPI gateway/worker split, single-user-for-now owner seams, resource-aware jobs, and data preservation requirements. |
| Phase 1 - Tiny Frontend Alignment Patch | Implemented | `apps/web/src/app/modules.ts` now includes all 15 canonical modules in order, including `models` and `reports`; app shell, registry, and Playwright entrypoint tests cover the new modules. |
| Phase 2 - Event Client Hardening | Implemented | `apps/web/src/events/eventClient.ts` now owns one multiplexed SSE connection, named-event subscriptions, connection status, reconnect backoff, listener rebinding, clean close behavior, pending reconnect cancellation, and an `eventSourceFactory` seam with focused Vitest coverage. |
| Phase 3 - Backend Reality Inventory and Feasibility Notes | Implemented | `docs/WEB_APP_BACKEND_REALITY_INVENTORY.md` inventories existing jobs, providers, assets, prompts, replay, persistence, incompatibilities, migration needs, tests, rollback paths, and reference implementation candidates. |
| Phase 4 - FastAPI Gateway Cutover Foundation | Implemented | `src/app/gateway/main.py` provides a thin provider-free FastAPI gateway with health, runtime status, worker-health placeholder, compatibility handoff, and `/openapi.json`; `docs/WEB_APP_GATEWAY_STARTUP.md` documents coexistence with the current app. |
| Phase 5 - Gateway and Worker Contract | Implemented | `src/app/gateway/workers.py` defines env-driven worker discovery, compatibility env support, standard health envelopes, unreachable-worker diagnostics, payload policy, and mock-worker mode for CI/local tests. |
| Phase 6 - Minimal API Contract and Type Generation | Implemented | `openapi-typescript` is wired through `apps/web/package.json`; `scripts/export_gateway_openapi.py` exports the gateway schema; `apps/web/src/api/generated/types.ts` and `apps/web/src/api/client.ts` provide the generated import convention; `docs/WEB_APP_API_TYPES.md` documents regeneration and the deferred drift check. |
| Phase 7 - Resource-Aware Job Schema and Scheduler Design | Implemented | `docs/WEB_APP_JOB_RUN_SCHEMA.md` defines the shared job/run schema, resource classes, safe single-GPU scheduler rules, stage/checkpoint semantics, cancellation, SSE lifecycle events, compatibility mapping, and Phase 8 implementation boundaries. |
| Phase 8 - Shared Job/Run System Consolidation | Implemented | `src/app/jobs/` adds the SQLite-backed shared job store, resource-aware claim/lease scheduler, local async executor, TTS/image compatibility submission adapters, cancellation, completion/failure transitions, and job event records; `src/app/gateway/main.py` exposes typed `/api/jobs*` endpoints and regenerated OpenAPI types. |
| Phase 9 - Provider and Model Registry Consolidation | Implemented | `src/app/providers/facade.py` normalizes existing LLM, audio, image, and RPG visual registries into one read-only provider/model facade; `src/app/gateway/main.py` exposes typed `/api/providers` and `/api/models`; generated API types include the facade contract. |
| Phase 10 - Shared Asset and Artifact Library with Data Migration | Implemented | `src/app/assets/` defines the shared asset model and manifest-backed store; image-manifest compatibility import supports dry-run, missing-file diagnostics, and import without deleting legacy data; `src/app/gateway/main.py` exposes typed `/api/assets*` endpoints with regenerated API types. |
| Phase 11 - Prompt and Template System | Implemented | `src/app/prompts/` adds shared prompt/template metadata, strict variable rendering, safety/grounding metadata propagation, replay metadata hashes, and a typed `/api/prompts/render` diagnostics endpoint without moving RPG-specific prompt semantics. |
| Phase 12 - Replay and Persistence Platformization | Implemented | `src/app/replay/` defines shared replay/persistence primitives and an RPG delegate adapter for state hashing, provider recording metadata, checkpoint envelopes, session inventory, and migration references; `src/app/gateway/main.py` exposes typed `/api/replay/*` diagnostics without moving RPG internals. |
| Phase 13 - API Contract Hardening and Typegen Drift Checks | Implemented | `src/app/platform/` adds typed settings, reports, and diagnostics summaries; gateway contract tests cover jobs, providers, assets, prompts, replay, settings, reports, and diagnostics; generated API files are refreshed; `apps/web/package.json` has a passing `api:check` drift gate. |
| Phase 14 - Router Migration | Implemented | `@tanstack/react-router` is installed; `apps/web/src/app/router.tsx` defines the app route tree, root redirect, and canonical module routes; `OmnixApp` now uses `RouterProvider`; no top-level `pushState` shell routing remains; unit and Playwright navigation tests cover the route entrypoints. |
| Phase 15 - Design System Foundation | Implemented | Mantine is installed and wired through `MantineProvider`; `apps/web/src/design/theme.ts` defines Omnix theme tokens; `apps/web/src/design/primitives.tsx` provides shared shell, nav, topbar, status, workspace, progress/log, transcript, audio, asset, and diagnostics primitives used by the app shell and workspace tests. |
| Phase 16 - Platform Modules First | Implemented | `apps/web/src/features/platform/PlatformModuleWorkspace.tsx` provides Providers, Models, Jobs, Assets, Reports, Settings, and Diagnostics views against typed gateway helpers; focused Vitest and Playwright coverage use mocked gateway payloads and empty states. |
| Phase 17 - Feature Module Migration | Implemented | Chatbot, Voice / TTS, STT, Image Generation, Storyteller, Podcast, Voice Cloning, and RPG now live in shared-shell feature workspaces with focused Vitest and Playwright coverage. |
| Phase 18 - Legacy UI Retirement | Implemented | `src/run_app.py` no longer serves the classic browser shell or `/static/*`; gateway compatibility metadata reports the legacy UI as `retired`; retired static-source tests are skipped by default while gateway/new-web checks stay active; `src/templates` and `src/static` have been deleted. |
| Phase 19 - Hardening and Release Readiness | Implemented | CI-safe backend and web readiness checks cover mock-worker runtime status, worker-down diagnostics, job failure/cancellation events, app-shell/module E2E smoke, mock job/asset/report lifecycle surfaces, generated-media compatibility, image migration dry-run/import diagnostics, and release runbook guidance. |

## Current Branch Baseline

The `rpg` branch already contains an early `apps/web` React/Vite scaffold and a legacy Python/Flask-oriented application. The current architecture standard is documented in `docs/WEB_APP_INFRASTRUCTURE.md`, but the branch still has known drift:

- The module registry now includes the canonical 15 modules, but the module workspaces are still placeholders.
- Routing is still hand-rolled in the web shell rather than using the chosen router.
- The event client now owns reconnect, status, listener rebinding, and a test/future auth-aware transport seam.
- The backend reality inventory is captured in `docs/WEB_APP_BACKEND_REALITY_INVENTORY.md`; consolidation should use those reference candidates and compatibility notes before changing queues, registries, stores, prompts, or replay paths.
- A thin provider-free FastAPI gateway now exists at `app.gateway.main:app` with `/openapi.json`, health, runtime status, worker health, payload policy, mock-worker mode, and compatibility handoff routes.
- Gateway API types are generated from the FastAPI schema into `apps/web/src/api/generated/`; `GatewayApiPaths` is the shared frontend import seam, and strict CI drift checks are intentionally deferred until contracts stabilize.
- The shared job/run schema is defined in `docs/WEB_APP_JOB_RUN_SCHEMA.md`; Phase 8 should implement the durable local adapter and executor without migrating RPG narration out of `runtime_state`.
- The shared job/run system exists at `src/app/jobs/` with SQLite persistence, resource-aware claim/lease scheduling, a local async executor seam, TTS/image compatibility submission adapters, gateway job endpoints, named job event records, and generated TypeScript API coverage.
- The provider/model facade exists at `src/app/providers/facade.py` and exposes existing LLM/audio/image/RPG visual registry metadata through `/api/providers` and `/api/models`. Live model refresh remains a later diagnostics operation; Phase 9 does not instantiate heavy providers during listing.
- The shared asset library exists at `src/app/assets/` with a platform asset model, manifest-backed shared store, image-manifest dry-run/import compatibility path, missing-file diagnostics, gateway asset endpoints, and generated TypeScript API coverage. Existing image manifests and files remain in place.
- The shared prompt/template helpers exist at `src/app/prompts/` with strict rendering, prompt metadata, replay hashes, safety/grounding metadata, and a typed gateway render endpoint. RPG prompt builders still own RPG-specific instructions and grounding semantics.
- Shared replay/persistence wrappers exist at `src/app/replay/` with an RPG delegate adapter for deterministic state hashes, checkpoint envelopes, session inventory, and replay primitive metadata. RPG replay/session/checkpoint internals remain the source of truth.
- Phase 13 contract hardening is implemented: typed settings, reports, and diagnostics gateway endpoints exist, representative gateway contract tests cover the platform API surface, generated API files are refreshed, and `api:check` passes.
- TanStack Router now owns the web shell route tree. The canonical module routes live in `apps/web/src/app/router.tsx`, root navigation redirects into the RPG module, and the module nav uses typed router links instead of hand-rolled `window.history.pushState`.
- Mantine and Omnix design tokens now back the web shell. Shared primitives live in `apps/web/src/design/primitives.tsx` and cover the shell, navigation, status, workspace panels, progress/logs, transcripts, audio controls, asset cards, and diagnostics rows.
- The platform module workspaces now exist under `apps/web/src/features/platform/`. Providers, Models, Jobs, Assets, Reports, Settings, and Diagnostics consume typed gateway helpers and render core empty/error states, including mocked Playwright coverage for platform navigation.
- Phase 17 feature migration is implemented. Chatbot now lives under `apps/web/src/features/chatbot/`, uses provider/model registry data, React Hook Form state, shared transcript primitives, backend-owned `/api/chat/sessions*` history, and shared `chat.generate` jobs rather than direct provider calls. Voice / TTS now lives under `apps/web/src/features/voice/`, queues `tts.synthesize` through `/api/jobs`, and reads shared voice jobs/audio assets without calling TTS workers directly. STT now lives under `apps/web/src/features/stt/`, queues `stt.transcribe`, and reads shared audio/transcript assets. Image Generation now lives under `apps/web/src/features/image-generation/`, queues `image.generate`, and reads shared image jobs/assets. Storyteller now lives under `apps/web/src/features/storyteller/`, queues `story.generate`, and reads shared story/export assets. Podcast now lives under `apps/web/src/features/podcast/`, queues multi-stage `podcast.generate`, and reads shared podcast script/audio/export assets. Voice Cloning now lives under `apps/web/src/features/voice-cloning/`, queues `voice-cloning.train`, and reads shared voice sample/profile assets. RPG now lives under `apps/web/src/features/rpg/`, reads shared replay inventory, jobs, reports, and checkpoint assets, and queues replay-preserving `rpg.turn` jobs without moving RPG deterministic internals.
- The classic browser UI is retired. `src/run_app.py` now exposes backend status and compatibility routes rather than the old template/static shell; `apps/web` is the supported browser app; the retired static/template tree has been physically removed.
- The backend is not greenfield: job queues, provider registries, asset handling, prompt builders, and RPG replay/persistence already exist in different forms.
- Heavy model work must remain outside the gateway process because local GPU/VRAM residency is the core runtime constraint.
- Existing on-disk user data, including RPG saves/checkpoints, settings, generated reports, voice assets, image assets, and local artifacts, must remain readable or migrate safely.

## Target Architecture Summary

Omnix is one platform with many modules:

```text
Omnix Web Platform
├── RPG
├── Chatbot
├── Storyteller
├── Podcast Generator
├── Voice / TTS
├── Voice Cloning
├── STT / Transcription
├── Image Generation
├── Providers
├── Model Manager
├── Jobs / Runs
├── Assets / Artifacts
├── Reports
├── Settings
└── Diagnostics
```

Chosen platform standards:

```text
Frontend runtime: React + TypeScript + Vite
Routing:          TanStack Router
Server state:     TanStack Query
Local UI state:   Zustand
Forms:            React Hook Form
API typing:       openapi-typescript generated from FastAPI /openapi.json
Validation:       Zod at trust boundaries only
Design system:    Mantine + Omnix theme tokens
Realtime:         Shared SSE-first event client, WebSocket only when needed
Backend:          FastAPI gateway / orchestrator
Workers:          Separate model/inference services behind the gateway
Jobs:             Shared resource-aware job/run system
Assets:           Shared artifact library
Testing:          Vitest + Playwright + backend deterministic/replay gates
```

## Implementation Principles

1. **Docs first, code second.** Every major platform decision should be captured before implementation.
2. **No third implementation.** When duplicate systems already exist, consolidate them; do not add another parallel queue, registry, asset store, or prompt system.
3. **Small auditable slices.** Each phase should land in narrow changes with clear acceptance criteria.
4. **Gateway, not monolith.** FastAPI exposes one API surface, but model inference stays in worker processes.
5. **Typed contracts early.** The FastAPI gateway and OpenAPI type generator must exist before large backend contracts are consumed by the web app.
6. **Resource-aware jobs from the start.** GPU/VRAM scheduling must be part of the job interface, not bolted on later.
7. **Preserve existing data.** Existing saves, settings, voice assets, reports, generated files, and checkpoints must migrate or remain readable through compatibility shims.
8. **Preserve RPG determinism.** Existing RPG replay, state hashing, checkpoints, and session behavior are treated as reference implementations and must not be broken by extraction.
9. **Feature modules consume platform services.** No module may create its own app shell, provider selection, job queue, artifact store, prompt convention, or diagnostics channel.

## Phase 0 — Architecture Design Hardening

Purpose: make the design precise enough to guide implementation.

Tasks:

- Expand `docs/WEB_APP_INFRASTRUCTURE.md` with the current target architecture:
  - deployment scope and identity assumptions;
  - FastAPI gateway plus model worker topology;
  - gateway-to-worker contract;
  - GPU/model residency scheduling;
  - canonical 15-module list;
  - TanStack Router decision;
  - `openapi-typescript` decision;
  - Mantine design-system decision;
  - resource-aware job/run semantics;
  - shared prompt/template system;
  - RPG replay/persistence as reference implementation;
  - consolidation-first backend strategy;
  - data/back-compat requirements for existing local files.
- Keep `docs/WEB_APP_REDESIGN_ROADMAP.md` updated as implementation progresses.
- Decide whether Omnix is permanently single-user or only single-user for now.
- If not permanently single-user, reserve an owner boundary for sessions, jobs, assets, saves, settings, and reports.

Acceptance criteria:

- The infrastructure doc clearly distinguishes as-built reality from target architecture.
- The doc states that one API surface does not mean one process.
- The doc names the chosen router, design-system base, API type generator, and job-system expectations.
- The doc states the data preservation requirement before any schema migration begins.
- Known branch drift is listed explicitly.

## Phase 1 — Tiny Frontend Alignment Patch

Purpose: remove obvious inconsistencies without introducing heavy infrastructure.

Tasks:

- Update `apps/web/src/app/modules.ts` to match the canonical 15-module list.
- Add `models` and `reports` module definitions.
- Keep module definitions simple: `id`, `label`, `summary`, `route`.
- Add or update tests that validate the module registry contains all canonical modules.

Acceptance criteria:

- `OmnixModuleId` includes all 15 platform modules.
- `omnixModules` includes all 15 modules in canonical order.
- Navigation can render placeholder workspaces for every module.
- No new router/design-system/typegen dependencies are introduced in this phase.

## Phase 2 — Event Client Hardening

Purpose: make the shared realtime transport safe enough for all modules to depend on.

Tasks:

- Upgrade the shared event client to own:
  - one multiplexed SSE connection;
  - named-event subscriptions;
  - connection status reporting;
  - reconnection with exponential backoff and jitter;
  - listener re-binding after reconnect;
  - clean close semantics;
  - pending reconnect cancellation when all subscribers unsubscribe;
  - an `eventSourceFactory` seam for tests and future auth-aware transports.
- Add tests for:
  - subscribe/unsubscribe behavior;
  - multiple listeners per event;
  - malformed JSON handling;
  - reconnect scheduling;
  - closing without reconnect;
  - no reconnect after the final subscriber unsubscribes.

Acceptance criteria:

- Feature modules do not instantiate their own `EventSource` objects.
- The client exposes connection status for diagnostics.
- Reconnect timers cannot leak after all subscribers unsubscribe.
- The design avoids query-string tokens for future auth.

## Phase 3 — Backend Reality Inventory and Feasibility Notes

Purpose: create an accurate map of the systems that must be consolidated before changing them.

Tasks:

- Inventory existing job queues:
  - TTS queue;
  - image claim/lease queue;
  - RPG visual queue wrappers;
  - any autoplay/report/background worker queues.
- Inventory existing provider registries:
  - LLM provider registry;
  - audio provider registry;
  - any image/provider-specific dispatch code.
- Inventory asset stores:
  - RPG visual asset store;
  - report artifacts;
  - audio artifacts;
  - voice clone/profile files;
  - session/checkpoint storage;
  - settings files.
- Inventory prompt/template builders:
  - RPG prompting;
  - dialogue prompts;
  - narration/presentation prompts;
  - campaign templates;
  - any chat/story/podcast prompts.
- Inventory replay/persistence:
  - LLM recording;
  - orchestration capture/replay;
  - state hashing;
  - replay validation;
  - checkpoints;
  - durable session stores;
  - existing migrators such as save or persistence migration managers.
- Write a consolidation feasibility note for each category under `docs/`.
- For each duplicate system, identify:
  - likely reference implementation;
  - incompatible assumptions;
  - data migration requirements;
  - tests needed before consolidation;
  - rollback path.

Acceptance criteria:

- Every existing implementation is listed with path, owner module, current behavior, and likely consolidation target.
- Each category has a feasibility note, not just an inventory list.
- The roadmap can identify which system becomes the reference implementation for jobs, providers, assets, prompts, and replay.
- Any blocking incompatibility between existing queues, registries, or stores is surfaced before implementation begins.
- No implementation changes are required in this phase beyond docs.

## Phase 4 — FastAPI Gateway Cutover Foundation

Purpose: make the gateway real before later phases depend on `/api/*` and `/openapi.json`.

Tasks:

- Stand up a thin FastAPI gateway application if the current active browser/API path is still Flask-oriented.
- Keep the existing Flask UI available during migration.
- Add initial gateway routes for:
  - health;
  - runtime status;
  - worker health aggregation placeholder;
  - OpenAPI schema exposure;
  - compatibility handoff to existing backend/domain services.
- Keep domain logic in existing service modules; do not rewrite RPG or provider internals in this phase.
- Add startup docs that explain the temporary coexistence of legacy Flask UI and the new gateway.

Acceptance criteria:

- A FastAPI gateway can start independently of the legacy UI path.
- `/openapi.json` is available from the gateway.
- Gateway health can be tested without real model workers.
- Existing legacy UI workflows are not removed or broken.
- This phase does not migrate feature UI or consolidate backend systems.

## Phase 5 — Gateway and Worker Contract

Purpose: formalize how the web/API gateway talks to model workers.

Tasks:

- Define a standard worker discovery contract:
  - worker URLs come from env vars;
  - no hardcoded worker ports in feature modules;
  - gateway is the only browser-facing caller.
- Define a standard worker health envelope:

```json
{
  "ok": true,
  "status": "ready",
  "details": {},
  "error": null
}
```

- Define unreachable-worker behavior:
  - status becomes `unreachable`;
  - gateway does not crash;
  - diagnostics report the failure.
- Define worker payload policy:
  - small payloads may be JSON;
  - large generated artifacts should be written to the shared asset store and returned by reference;
  - base64 audio/image payloads are acceptable only as a transitional path.
- Add mock-worker mode for CI and local tests.

Acceptance criteria:

- Gateway can aggregate worker health into one runtime-status response.
- CI can exercise gateway/job/event flows without GPU-backed workers.
- Worker failures produce diagnostics rather than process crashes.
- Feature modules never call workers directly.

## Phase 6 — Minimal API Contract and Type Generation

Purpose: move OpenAPI type generation early so later backend phases do not hand-write frontend contracts.

Tasks:

- Add `openapi-typescript` to the web toolchain.
- Generate TypeScript API types from the current gateway `/openapi.json`.
- Add a minimal generated-types output path and import convention.
- Document that Zod remains for forms, uploads, URL/search params, and SSE payloads only.
- Add a lightweight script to regenerate types locally.
- Defer strict CI drift enforcement until contracts stabilize later in the roadmap.

Acceptance criteria:

- Frontend code can import generated API types from the gateway schema.
- New `/api/*` contracts added in later phases can generate types immediately.
- No duplicate hand-maintained interfaces are introduced for new gateway response/request models.
- CI drift checking is explicitly deferred, not forgotten.

## Phase 7 — Resource-Aware Job Schema and Scheduler Design

Purpose: design the job model and scheduler before consolidating queues.

Tasks:

- Define the shared job fields:
  - id;
  - owner/reserved owner seam;
  - module;
  - type;
  - status;
  - resource class;
  - priority;
  - stage list;
  - progress;
  - logs;
  - input payload reference;
  - output asset references;
  - error details;
  - created/updated timestamps;
  - cancellation state.
- Define resource classes:

```text
cpu
gpu:llm
gpu:tts
gpu:stt
gpu:image
network
```

- Define default scheduling rules:
  - GPU-bound jobs are exclusive by default;
  - cloud/network jobs are not serialized behind local GPU work;
  - CPU jobs can run concurrently within configured limits;
  - model load/evict transitions are visible job stages.
- Define the first scheduler behavior explicitly:
  - single local GPU lock as the safe default;
  - resource class recorded for every job;
  - network jobs bypass the GPU lock;
  - future VRAM-aware co-residency left as an explicit later upgrade.
- Define stage semantics:
  - stages have independent status and progress;
  - completed stages can checkpoint outputs;
  - retries resume from safe checkpoints when possible;
  - cancellation during model inference is best-effort.

Acceptance criteria:

- The job interface includes resource class from day one.
- Multi-stage jobs can represent podcast, voice cloning, RPG autoplay, image generation, and STT alignment.
- The initial scheduler design can enforce a safe single-GPU-job default.
- Full VRAM-aware co-residency is not implied unless implemented and tested.
- Job cancellation semantics are documented honestly.
- The schema is compatible with a future broker even if the first executor is local.

## Phase 8 — Shared Job/Run System Consolidation

Purpose: converge duplicate queues into one job system.

Tasks:

- Use the claim/lease model as the reference queue pattern confirmed by Phase 3, while replacing the current in-memory storage with a durable adapter.
- Add a SQLite-backed job table or adapter.
- Add an in-process asyncio worker executor for local-first single-user mode.
- Implement the safe default scheduler:
  - one local GPU job at a time;
  - network jobs are not blocked by local GPU jobs;
  - CPU jobs are bounded by configured concurrency.
- Wrap existing TTS queue behavior behind the shared job interface.
- Wrap existing image queue behavior behind the shared job interface.
- Preserve image claim/lease safety properties.
- Preserve TTS chunk ordering/reassembly behavior as stage/checkpoint behavior.
- Add job events to the shared event stream.
- Add job diagnostics and logs.
- Add compatibility handling for existing queued/generated artifacts where applicable.

Acceptance criteria:

- New modules can enqueue jobs through one interface.
- TTS and image workflows no longer require separate public queue APIs for new work.
- Jobs survive browser reloads.
- Restart durability is either implemented or explicitly marked as not yet supported.
- Safe single-GPU-job exclusivity is enforced for local workers.
- Network/cloud jobs are not serialized behind local GPU work.
- Job progress emits named SSE events.
- Existing TTS/image outputs are not orphaned by the queue transition.

Implementation note 2026-06-14: the durable shared job core, typed gateway API,
local executor seam, and TTS/image compatibility submission adapters are
implemented. Existing feature queues remain intact behind compatibility
adapters so current output locations and behavior are not removed during this
phase.

## Phase 9 — Provider and Model Registry Consolidation

Purpose: expose one provider/model facade across all modules.

Tasks:

- Define provider capabilities:
  - chat;
  - completion;
  - embedding;
  - TTS;
  - STT;
  - image;
  - voice cloning;
  - diagnostics;
  - model discovery.
- Build a shared provider facade over existing LLM and audio registries.
- Avoid creating a third registry.
- Normalize provider health and capability reporting.
- Add model-manager API concepts:
  - installed/local models;
  - remote/cloud models;
  - model capabilities;
  - memory/VRAM hints where known;
  - default model selection per capability.
- Update modules to consume the facade instead of direct registries.

Acceptance criteria:

- Providers and Models modules can list capabilities and health through one API.
- Feature modules request capabilities rather than concrete provider classes.
- Existing LLM and audio provider behavior remains compatible.
- No new feature module instantiates providers directly.

Implementation note 2026-06-14: Phase 9 adds a read-only facade over the
existing registries rather than creating a new discovery registry. The facade
publishes capabilities, normalized provider families, status metadata, and
settings-derived model hints without live provider instantiation. Live model
refresh and active health probes should remain explicit diagnostics calls.

## Phase 10 — Shared Asset and Artifact Library with Data Migration

Purpose: make generated files a platform concept without orphaning existing local data.

Tasks:

- Define the shared asset model:
  - id;
  - owner/reserved owner seam;
  - module;
  - type;
  - mime type;
  - storage path;
  - metadata;
  - source job;
  - parent/derived assets;
  - created timestamp.
- Generalize RPG visual asset storage into a platform asset service.
- Define how existing files are handled:
  - compatibility read-through for existing stores;
  - one-time migration where safe;
  - dry-run migration mode;
  - rollback strategy;
  - missing-file diagnostics.
- Cover existing categories:
  - audio;
  - voice sample;
  - voice profile;
  - image;
  - transcript;
  - story;
  - podcast script;
  - report;
  - RPG checkpoint;
  - run log;
  - export;
  - settings-backed artifacts.
- Update jobs to return output asset references.
- Add asset lifecycle decisions:
  - retention;
  - deletion;
  - export;
  - thumbnail/preview generation;
  - metadata indexing.

Acceptance criteria:

- Image, audio, transcript, report, checkpoint, and voice-profile outputs can be represented by one asset model.
- Existing generated files and saves are either migrated or readable through compatibility paths.
- No data loss occurs for existing saves, voice assets, settings, reports, or generated media.
- Feature modules do not create module-local asset stores for new work.
- Jobs publish output assets instead of large inline payloads where practical.
- Assets are inspectable from the Assets module.

Implementation note 2026-06-14: Phase 10 adds the shared asset model, a JSON
manifest-backed platform store, and image-manifest compatibility dry-run/import
without deleting or moving legacy files. Broader audio/report/checkpoint
migrations should use the same preview/import pattern before changing storage.

## Phase 11 — Prompt and Template System

Purpose: prevent each AI module from inventing its own prompt conventions.

Tasks:

- Inventory existing prompt builders and templates.
- Define shared prompt/template concepts:
  - template id;
  - version;
  - module;
  - variables;
  - provider payload format;
  - rendering metadata;
  - safety/grounding metadata;
  - replay recording metadata.
- Extract common rendering and variable-substitution helpers.
- Keep RPG-specific prompt semantics inside RPG where appropriate.
- Add versioning so replay can identify which prompt template produced a run.
- Add a prompt diagnostics surface for rendered prompt inspection.

Acceptance criteria:

- Chatbot, storyteller, podcast, and RPG can share prompt rendering primitives.
- Prompt template version is recorded for replay/debugging.
- Provider payload construction is centralized where practical.
- RPG prompt behavior remains deterministic and compatible.

Implementation note 2026-06-14: Phase 11 adds prompt metadata and rendering
helpers only. Existing feature prompt builders should wrap this renderer where
useful, but RPG-specific system instructions, grounding rules, and replay
contracts stay in their current RPG modules until golden/replay tests authorize
changes.

## Phase 12 — Replay and Persistence Platformization

Purpose: generalize RPG's deterministic patterns without breaking RPG.

Tasks:

- Document current RPG replay/persistence entrypoints.
- Identify generic primitives:
  - nondeterministic input recording;
  - provider request/response recording;
  - state snapshot hashing;
  - replay comparison;
  - divergence errors;
  - checkpoint storage;
  - run artifact capture.
- Wrap existing RPG replay APIs instead of moving them immediately.
- Add shared interfaces that RPG can implement first.
- Add parity tests around RPG before any extraction.
- Gradually move only generic pieces after tests prove compatibility.
- Integrate with existing migration managers where save/session schemas change.

Acceptance criteria:

- RPG replay behavior is unchanged.
- Replay parity tests pass before and after any shared extraction.
- Existing RPG saves/checkpoints remain readable or migrate safely.
- Shared replay primitives can be reused by long-running non-RPG workflows.
- RPG-specific simulation state, validators, and semantics remain inside RPG.

Implementation note 2026-06-14: Phase 12 adds typed platform wrappers and
gateway diagnostics around RPG replay/persistence primitives. It does not move
RPG saved files, replay validators, state hash semantics, checkpoint checksum
logic, or migration managers. Future extraction must be preceded by RPG parity
and save/checkpoint compatibility tests.

## Phase 13 — API Contract Hardening and Typegen Drift Checks

Purpose: make generated contracts enforceable after the core gateway APIs exist.

Tasks:

- Expand generated API types to cover jobs, providers, assets, prompts, replay, settings, reports, and diagnostics.
- Replace any transitional hand-mirrored response interfaces with generated types.
- Add CI checks to ensure generated types are current.
- Add contract tests for representative gateway endpoints.
- Keep Zod for forms, uploads, URL/search params, and SSE payloads only.

Acceptance criteria:

- API response/request types are generated from backend OpenAPI.
- No duplicate hand-maintained interfaces mirror server models.
- Frontend build or CI fails when generated types drift.
- Zod usage is limited to runtime trust boundaries.

Implementation note 2026-06-14: representative platform contracts now cover
jobs, providers, assets, prompts, replay, settings, reports, and diagnostics.
The `api:check` script regenerates the gateway schema/types and fails when
checked-in generated API files drift.

## Phase 14 — Router Migration

Purpose: replace temporary shell routing with the chosen router.

Tasks:

- Add TanStack Router dependency.
- Replace hand-rolled `window.history.pushState` routing.
- Create app-level route tree.
- Add feature route registration pattern.
- Add placeholder routes for all 15 modules.
- Preserve module navigation behavior.
- Add Playwright coverage for navigation.

Acceptance criteria:

- No hand-rolled top-level history manipulation remains.
- Every canonical module has a route.
- Route params/search state are typed.
- Navigation tests cover module entrypoints.

Implementation note 2026-06-14: Phase 14 replaces the temporary shell routing
with TanStack Router while preserving the existing shared shell and placeholder
module workspaces. The root path redirects to `/rpg`; all canonical modules have
registered routes and Playwright coverage.

## Phase 15 — Design System Foundation

Purpose: prevent module-by-module UI drift.

Tasks:

- Add Mantine dependencies.
- Define Omnix theme tokens:
  - color;
  - spacing;
  - typography;
  - radius;
  - elevation;
  - status/accent treatment;
  - density.
- Build shared primitives:
  - app shell;
  - sidebar navigation;
  - top status bar;
  - workspace layout;
  - panel/card;
  - status pill;
  - progress/log viewer;
  - transcript/message view;
  - audio controls;
  - asset card;
  - diagnostics view.
- Keep React Hook Form as the form-state standard, with Mantine inputs wrapped as needed.
- Add visual and interaction tests for core primitives.

Acceptance criteria:

- Feature modules use shared layout and primitives.
- Mantine theme plus Omnix tokens becomes the styling contract.
- No feature creates competing app-shell or primitive systems.
- Dark-first workstation presentation is consistent across modules.

Implementation note 2026-06-14: Phase 15 introduces Mantine, the Omnix theme,
and shared workstation primitives while keeping the existing visual language and
TanStack Router shell. Feature modules should consume these primitives instead
of creating local app-shell, panel, status, log, transcript, audio, asset, or
diagnostics components.

## Phase 16 — Platform Modules First

Purpose: build the modules that all feature modules depend on.

Tasks:

- Providers module:
  - provider health;
  - capabilities;
  - latency/errors;
  - configuration diagnostics.
- Models module:
  - model list;
  - capability mapping;
  - selected defaults;
  - local/cloud distinction;
  - VRAM hints where available.
- Jobs module:
  - queue view;
  - stages;
  - logs;
  - progress;
  - cancellation;
  - resource locks.
- Assets module:
  - asset browser;
  - previews;
  - metadata;
  - source job links;
  - migrated/compatibility asset indicators where needed.
- Reports module:
  - run reports;
  - RPG autoplay reports;
  - generated document exports.
- Settings module:
  - global app settings;
  - provider settings;
  - worker URLs;
  - local service toggles.
- Diagnostics module:
  - gateway health;
  - worker health;
  - event stream status;
  - logs;
  - troubleshooting surfaces.

Acceptance criteria:

- Platform modules work with stubbed/mock data first, then real APIs.
- Feature modules can depend on provider/job/asset/diagnostics surfaces.
- Playwright covers platform-module navigation and core empty states.

Implementation note 2026-06-14: Phase 16 adds typed frontend API helpers for
the core platform endpoints and routes the seven platform modules through
`PlatformModuleWorkspace`. The views use gateway contracts for providers,
models, jobs, assets, reports, settings, and diagnostics, while unit and
Playwright tests provide mocked payloads and empty-state coverage so the web app
does not require local model workers for platform-module validation.

## Phase 17 — Feature Module Migration

Purpose: migrate user-facing feature behavior into the shared shell.

Recommended order:

1. Chatbot — simplest provider/session/message surface.
2. Voice / TTS — exercises jobs, audio assets, provider diagnostics.
3. STT — exercises asset ingestion and transcription jobs.
4. Image Generation — exercises GPU scheduling and image assets.
5. Storyteller — exercises prompt templates, jobs, text assets.
6. Podcast — exercises multi-stage jobs and generated audio/script assets.
7. Voice Cloning — exercises sample ingestion, profile metadata, and long jobs.
8. RPG — migrate after shared jobs/assets/providers/replay contracts are stable, because RPG is the most complex and must preserve determinism.

Acceptance criteria for each module:

- The module lives under `apps/web/src/features/<module>`.
- The module uses shared routing, API client, event client, Query hooks, design primitives, jobs, providers, and assets.
- The module does not call workers directly.
- The module preserves or migrates existing user data for that feature.
- The module has unit or Playwright coverage for the main entrypoint.
- Legacy UI behavior remains available until parity is reached.

Implementation note 2026-06-14: the Chatbot slice adds a lightweight
backend-owned chat session contract in `src/app/chat/` and gateway routes under
`/api/chat/sessions*`. The web workspace uses shared provider/model data,
React Hook Form, shared transcript rendering, and queues `chat.generate` through
the shared job API instead of invoking providers directly. Actual assistant
generation remains a future worker/executor attachment point.

Implementation note 2026-06-14: the Voice / TTS slice adds
`apps/web/src/features/voice/VoiceWorkspace.tsx`. The workspace uses shared TTS
provider data, React Hook Form, shared audio controls, shared job and asset
queries, and submits `tts.synthesize` jobs to `/api/jobs` with explicit
GPU-TTS/CPU stages. It does not call legacy TTS HTTP routes or model workers
from the browser.

Implementation note 2026-06-14: the STT / Transcription slice adds
`apps/web/src/features/stt/SttWorkspace.tsx`. The workspace uses shared STT
provider data, React Hook Form, shared audio/transcript asset references, shared
job queries, and submits `stt.transcribe` jobs to `/api/jobs` with explicit
GPU-STT and CPU alignment/storage stages.

Implementation note 2026-06-14: the Image Generation slice adds
`apps/web/src/features/image-generation/ImageGenerationWorkspace.tsx`. The
workspace uses shared image provider data, React Hook Form, shared job and image
asset queries, and submits `image.generate` jobs to `/api/jobs` with explicit
GPU-image generation and CPU asset-storage stages.

Implementation note 2026-06-14: the Storyteller slice adds
`apps/web/src/features/storyteller/StorytellerWorkspace.tsx` with shared LLM
provider data, React Hook Form, shared job/story asset queries, and
`story.generate` submission through `/api/jobs`. Focused Vitest, typecheck, and
Playwright coverage verify the workspace and mocked shared job handoff.

Implementation note 2026-06-14: the Podcast slice adds
`apps/web/src/features/podcast/PodcastWorkspace.tsx`. The workspace uses shared
LLM and TTS provider data, React Hook Form, shared audio controls, shared job
and podcast asset queries, and submits multi-stage `podcast.generate` jobs to
`/api/jobs` for planning, scripting, voice synthesis, mixing, and export.

Implementation note 2026-06-14: the Voice Cloning slice adds
`apps/web/src/features/voice-cloning/VoiceCloningWorkspace.tsx`. The workspace
uses shared TTS/voice-cloning provider data, React Hook Form, shared audio
controls, shared voice sample/profile assets, and submits `voice-cloning.train`
jobs to `/api/jobs` with sample ingest, profile build, preview, and storage
stages. The route shell now prefers exact/longest route matches so
`/voice-cloning` no longer collides with `/voice`.

Implementation note 2026-06-14: the RPG slice adds
`apps/web/src/features/rpg/RpgWorkspace.tsx`. The workspace uses shared replay
persistence inventory, job, report, and asset APIs, reads existing RPG session
and checkpoint metadata through platform contracts, and submits
replay-preserving `rpg.turn` jobs to `/api/jobs` with load-session, apply-turn,
narration, and checkpoint stages. It does not move RPG simulation, replay,
state hashing, or checkpoint internals.

## Phase 18 — Legacy UI Retirement

Purpose: remove old frontend paths after parity and data safety are proven.

Tasks:

- Confirm every active browser-facing feature has a shared-shell equivalent.
- Confirm existing on-disk data remains readable or has migrated successfully.
- Freeze legacy UI changes.
- Add redirects or clear startup docs pointing to the new web app.
- Remove or archive legacy templates/static entrypoints when safe.
- Update README and developer startup docs.
- Remove dead scripts only after verification.

Acceptance criteria:

- `apps/web` is the supported browser UI.
- Legacy UI is no longer needed for active workflows.
- Existing saves, settings, voice assets, reports, checkpoints, and generated media are not orphaned.
- Documentation points to the new startup path.
- No active tests depend on removed legacy frontend files.

Implementation note 2026-06-14: Phase 18 cannot safely remove legacy browser
files yet. `docs/WEB_APP_LEGACY_UI_RETIREMENT_READINESS.md` records the active
`src/run_app.py`, `src/templates`, `src/static`, Flask client, and static JS
test anchors that still block retirement. Startup docs now point new browser
work at `apps/web` plus the FastAPI gateway on port `8000`, while
`src/run_app.py` remains compatibility-only.

Implementation note 2026-06-15: the first Phase 18 parity slice bridges
`/api/settings` through the shared gateway. `GET /api/settings` remains the
sanitized platform summary consumed by `apps/web`, adds a legacy-compatible
`{ success, settings }` envelope with masked API keys, and `POST /api/settings`
preserves the legacy settings/secrets split. Remaining blockers include legacy
session routes, selected RPG routes, static JS test anchors, and representative
data-compatibility tests.

Implementation note 2026-06-15: the second Phase 18 parity slice bridges
legacy `/api/sessions` CRUD and `/api/sessions/generate-title` fallback through
the shared gateway. The routes preserve legacy response envelopes, file-backed
session semantics, newest-first session ordering, update/delete behavior, and a
safe title fallback without pulling provider calls into the gateway.

Implementation note 2026-06-15: the third Phase 18 parity slice bridges
low-risk RPG adventure-builder routes through the shared gateway:
`GET /api/rpg/adventure/templates`, `POST /api/rpg/adventure/validate`, and
`POST /api/rpg/adventure/preview`. These routes delegate to deterministic
creator preview helpers and intentionally avoid adventure start, regeneration,
live turn, replay mutation, and model-backed flows.

Implementation note 2026-06-15: the fourth Phase 18 parity slice adds backend
gateway compatibility for RPG session inspection routes:
`POST /api/rpg/session/list` and `POST /api/rpg/session/get`. The bridge
preserves the legacy list, missing-session-id, missing-session, and frontend
bootstrap envelopes without mounting the full RPG routers or live turn mutation
paths. Backend gateway tests pass for this slice; frontend OpenAPI/type
generation and the shared generated route smoke test cover these routes.

Implementation note 2026-06-15: the fifth Phase 18 parity slice adds backend
gateway compatibility for deterministic RPG inspector read routes:
`POST /api/rpg/inspect/timeline`,
`POST /api/rpg/inspect/timeline_tick`,
`POST /api/rpg/inspect/tick_diff`,
`POST /api/rpg/inspect/npc_reasoning`, and
`POST /api/rpg/inspect/world_events`. These routes delegate to analytics helper
functions and intentionally exclude GM force/debug mutation routes. Backend
gateway tests pass for this slice; frontend OpenAPI/type generation and the
shared generated route smoke test cover these routes.

Implementation note 2026-06-15: the sixth Phase 18 parity slice adds backend
gateway compatibility for deterministic RPG player-facing read routes:
`POST /api/rpg/player/state`, `POST /api/rpg/player/journal`,
`POST /api/rpg/player/codex`, `POST /api/rpg/player/objectives`, and
`POST /api/rpg/player/encounter`. These routes delegate to player state and
encounter view helpers and intentionally exclude dialogue transitions,
inventory mutations, equipment changes, progression allocation, and session
persistence. Backend gateway tests pass for this slice; frontend OpenAPI/type
generation and the shared generated route smoke test cover these routes.

Implementation note 2026-06-15: the seventh Phase 18 parity slice adds backend
gateway compatibility for deterministic RPG adventure-builder diagnostic
routes: `POST /api/rpg/adventure/inspect-world`,
`POST /api/rpg/adventure/inspect-world-snapshot`,
`POST /api/rpg/adventure/compare-world`,
`POST /api/rpg/adventure/compare-entity`,
`POST /api/rpg/adventure/simulate-step`, and
`POST /api/rpg/adventure/simulation-state`. These routes delegate to world
inspection/simulation helpers and intentionally exclude adventure start,
regeneration, generated package application, scene narration, and LLM-backed NPC
filling. Backend gateway tests pass for this slice; frontend OpenAPI/type
generation and the shared generated route smoke test cover these routes.

Implementation note 2026-06-15: the eighth Phase 18 slice retires the classic
browser serving path. `src/run_app.py` now returns backend status JSON from
`GET /`, no longer mounts `/static/*` or `/logo/*`, and keeps
`/generated-images/*` only as generated user/runtime data. Gateway
compatibility metadata reports `legacy_ui_status: retired`. Retired static
source-inspection tests are skipped by default through `src/tests/conftest.py`
with `OMNIX_RUN_RETIRED_LEGACY_UI_TESTS=1` as an explicit archive-audit escape
hatch. The retired `src/templates` and `src/static` tree has been deleted.

## Phase 19 — Hardening and Release Readiness

Purpose: make the redesigned platform reliable for long local sessions.

Tasks:

- Add end-to-end smoke tests:
  - app shell loads;
  - module navigation;
  - provider diagnostics;
  - mock job lifecycle;
  - mock asset lifecycle;
  - event stream reconnect.
- Add backend integration tests with mock workers.
- Add migration/back-compat tests for representative existing data.
- Add long-running local tests for GPU scheduling where available.
- Add failure-mode tests:
  - worker down;
  - job failure;
  - malformed event;
  - cancellation;
  - restart behavior;
  - provider timeout;
  - missing legacy asset;
  - migration dry-run failure.
- Add developer docs:
  - local process mode;
  - optional compose mode;
  - worker setup;
  - mock-worker testing;
  - GPU scheduling expectations;
  - data migration and rollback.

Acceptance criteria:

- Core flows run without real model workers in CI.
- Local GPU/manual tests are documented separately.
- Failure modes surface actionable diagnostics.
- Long sessions do not leak event connections or orphan jobs.
- Existing data compatibility is verified before legacy retirement.

Implementation note 2026-06-15: the first Phase 19 hardening slice adds backend
release-readiness contracts that run without real model workers. Gateway tests
now prove `/api/runtime/status` reports CI mock workers, leased job cancellation
is observable without losing the active lease, failed jobs preserve retryable
diagnostics, and job SSE output includes terminal failure and cancellation
events. Remaining Phase 19 work should continue with E2E smoke coverage,
representative data compatibility tests, broader failure-mode tests, and
developer release/runbook docs.

Implementation note 2026-06-15: the final Phase 19 slice adds CI-safe web and
data-compatibility coverage plus release documentation. The Playwright app-shell
smoke now covers diagnostics, job cancellation, assets, reports, module
navigation, and feature job submissions with mocked gateway payloads. Backend
tests verify generated media remains served as runtime data after classic UI
deletion, missing generated media returns structured diagnostics, and shared
asset imports preserve missing legacy asset references in migration diagnostics.
`docs/WEB_APP_RELEASE_READINESS.md` records local process mode, mock workers,
worker setup, optional compose boundaries, GPU scheduling expectations, data
migration/rollback, and CI-safe release validation commands.

## Slice Checklist Template

Every implementation slice should include:

```text
Scope:
- What is changing?
- What is explicitly not changing?

Files:
- Expected files touched.

Acceptance:
- Observable outcome.
- Tests or manual checks.

Risk:
- Determinism risk?
- GPU/resource risk?
- Legacy compatibility risk?
- Data migration/back-compat risk?

Rollback:
- How to revert safely.
- How to restore or continue reading existing user data.
```

## Initial Suggested Slice Order

Use this order for the next work items:

1. Done 2026-06-14: Harden `docs/WEB_APP_INFRASTRUCTURE.md` with the complete design.
2. Done 2026-06-14: Add `models` and `reports` to `modules.ts`.
3. Done 2026-06-14: Upgrade the shared event client and tests.
4. Done 2026-06-14: Add backend inventory and feasibility docs for jobs/providers/assets/prompts/replay/data.
5. Done 2026-06-14: Stand up the thin FastAPI gateway foundation and `/openapi.json`.
6. Done 2026-06-14: Define the worker health contract and mock-worker mode.
7. Done 2026-06-14: Add minimal OpenAPI type generation.
8. Done 2026-06-14: Define the resource-aware job schema and safe scheduler behavior.
9. Done 2026-06-14: Consolidate job queues behind the shared interface with a durable job store, safe scheduler, local executor seam, gateway job API, named job event records, generated API types, and TTS/image compatibility submission adapters.
10. Done 2026-06-14: Consolidate provider registries behind one facade.
11. Done 2026-06-14: Generalize the asset store with data migration/back-compat.
12. Done 2026-06-14: Generalize prompt/template utilities.
13. Done 2026-06-14: Wrap and gradually platformize replay/persistence primitives.
14. Done 2026-06-14: Harden API contract/typegen drift checks.
15. Done 2026-06-14: Migrate to TanStack Router.
16. Done 2026-06-14: Add Mantine and Omnix design tokens.
17. Done 2026-06-14: Build platform modules.
18. Done 2026-06-14: Migrate feature modules. Chatbot, Voice / TTS, STT / Transcription, Image Generation, Storyteller, Podcast, Voice Cloning, and RPG are now shared-shell workspaces.
19. Done 2026-06-15: Retired the classic UI. Readiness ledger added; `/api/settings`, `/api/sessions`, low-risk RPG adventure preview/diagnostic routes, RPG session inspection routes, RPG inspector read routes, RPG player read routes, and RPG adventure diagnostics are covered with regenerated frontend API types; `src/run_app.py` no longer serves the classic browser shell; retired static-source tests are skipped by default; `src/templates` and `src/static` were deleted.
20. Done 2026-06-15: Hardening and release readiness. Backend readiness covers mock-worker runtime status, worker-down diagnostics, leased-job cancellation, failed-job diagnostic/event contracts, generated-media compatibility, and image migration diagnostics. Web E2E smoke covers app shell, navigation, diagnostics, mock job cancellation, assets, reports, and feature job submissions without GPU/model workers. Release runbook added.

## Stop Conditions

Pause implementation and update the design before continuing if any of these happen:

- A feature module needs to call a worker directly.
- A new job queue, provider registry, asset store, or prompt system is proposed.
- Existing queues/providers/assets cannot be consolidated as planned.
- GPU-bound jobs can run concurrently without a scheduler decision.
- A generated artifact cannot be represented by the shared asset model.
- Existing user data would become unreadable or orphaned.
- RPG replay parity changes unexpectedly.
- API types must be hand-maintained because OpenAPI generation is insufficient.
- A UI module needs styling primitives outside the shared design system.
- A workflow cannot be tested without a real GPU worker.

## Definition of Done for the Redesign

The redesign is complete when:

- `apps/web` is the only supported browser app.
- All 15 modules have routes and workspaces.
- Platform modules expose providers, models, jobs, assets, reports, settings, and diagnostics.
- Feature modules use shared platform services rather than direct worker or provider access.
- The job system is resource-aware and represents multi-stage workflows.
- The gateway degrades gracefully when workers are unavailable.
- Generated files flow through the shared asset library.
- Existing saves, voice assets, settings, reports, checkpoints, and generated media remain readable or are migrated safely.
- API types are generated from the backend contract.
- RPG determinism, replay, and save/load behavior remain intact.
- CI can run meaningful gateway/web tests without GPU-backed model workers.
