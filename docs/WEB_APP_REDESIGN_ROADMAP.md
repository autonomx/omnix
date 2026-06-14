# Omnix Web App Redesign Roadmap

This roadmap turns the Omnix-wide web app architecture into an implementation sequence. The goal is to move Omnix from a legacy single-page local UI plus separate model services into a coherent local-first AI workstation platform.

The roadmap is intentionally ordered to avoid the biggest risk: creating third implementations of systems that already exist in more than one form. Shared systems such as jobs, providers, assets, prompts, replay, diagnostics, and worker health should be consolidated from existing code before new feature modules depend on them.

This roadmap is also ordered to avoid a second risk: building backend contracts before the type-generation path exists. A minimal FastAPI gateway and OpenAPI type generation must land early enough that later backend consolidation phases can publish typed contracts as they are built.

## Implementation Status

Last updated: 2026-06-14

| Phase | Status | Evidence |
| --- | --- | --- |
| Phase 0 - Architecture Design Hardening | Implemented | `docs/WEB_APP_INFRASTRUCTURE.md` now records as-built drift, target stack decisions, the FastAPI gateway/worker split, single-user-for-now owner seams, resource-aware jobs, and data preservation requirements. |
| Phase 1 - Tiny Frontend Alignment Patch | Implemented | `apps/web/src/app/modules.ts` now includes all 15 canonical modules in order, including `models` and `reports`; app shell, registry, and Playwright entrypoint tests cover the new modules. |
| Phase 2 - Event Client Hardening | Implemented | `apps/web/src/events/eventClient.ts` now owns one multiplexed SSE connection, named-event subscriptions, connection status, reconnect backoff, listener rebinding, clean close behavior, pending reconnect cancellation, and an `eventSourceFactory` seam with focused Vitest coverage. |
| Phase 3 - Backend Reality Inventory and Feasibility Notes | Next | Inventory existing jobs, providers, assets, prompts, replay, and persistence before any consolidation implementation. |

## Current Branch Baseline

The `rpg` branch already contains an early `apps/web` React/Vite scaffold and a legacy Python/Flask-oriented application. The current architecture standard is documented in `docs/WEB_APP_INFRASTRUCTURE.md`, but the branch still has known drift:

- The module registry now includes the canonical 15 modules, but the module workspaces are still placeholders.
- Routing is still hand-rolled in the web shell rather than using the chosen router.
- The event client now owns reconnect, status, listener rebinding, and a test/future auth-aware transport seam.
- The browser UI still has legacy Flask/static entrypoints.
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

- Choose the claim/lease model as the reference queue pattern if Phase 3 feasibility confirms it.
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
4. Next: Add backend inventory and feasibility docs for jobs/providers/assets/prompts/replay/data.
5. Stand up the thin FastAPI gateway foundation and `/openapi.json`.
6. Define the worker health contract and mock-worker mode.
7. Add minimal OpenAPI type generation.
8. Define the resource-aware job schema and safe scheduler behavior.
9. Consolidate job queues behind the shared interface.
10. Consolidate provider registries behind one facade.
11. Generalize the asset store with data migration/back-compat.
12. Generalize prompt/template utilities.
13. Wrap and gradually platformize replay/persistence primitives.
14. Harden API contract/typegen drift checks.
15. Migrate to TanStack Router.
16. Add Mantine and Omnix design tokens.
17. Build platform modules.
18. Migrate feature modules.
19. Retire legacy UI only after data safety is verified.

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
