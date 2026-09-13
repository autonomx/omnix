# Omnix Architecture

This document describes the architecture implemented by the current Omnix application and the invariants new work must preserve. [`../SPEC.md`](../SPEC.md) is the authority for platform-level design rules; this document connects those rules to the current source tree.

## Architecture goals

Omnix is a single local-first application platform, not a collection of unrelated demos. The architecture is designed around several constraints:

1. One browser application and one shared app shell.
2. Backend-owned authoritative domain state.
3. Typed frontend/backend contracts.
4. One provider/model abstraction shared by every feature.
5. One long-running job/run model.
6. One asset/artifact model.
7. One event-stream model.
8. Governed capabilities for assistants and agents.
9. Local services can be split into separate processes/environments when model dependencies conflict.
10. PostgreSQL is the authoritative structured-data runtime database.
11. Legacy browser surfaces are retired; compatibility backend routes may remain during migration.

## System overview

```text
┌────────────────────────────────────────────────────────────────────┐
│ Browser                                                            │
│                                                                    │
│  Omnix Web — React / TypeScript / Vite                             │
│  ├─ app shell + TanStack Router                                    │
│  ├─ feature workspaces                                             │
│  ├─ TanStack Query server-state cache                              │
│  ├─ Zustand view/workspace state                                   │
│  ├─ React Hook Form + validation                                   │
│  ├─ typed API client                                               │
│  ├─ SSE/WebSocket event consumers                                  │
│  └─ shared design system                                           │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ /api + /events
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ FastAPI Web Gateway                                                │
│  ├─ chat / assistant context                                       │
│  ├─ platform settings + diagnostics                                │
│  ├─ provider/model facade                                          │
│  ├─ jobs / model residency                                         │
│  ├─ assets / reports                                               │
│  ├─ RPG / replay projections and migrated routes                   │
│  ├─ story / media orchestration                                    │
│  ├─ agent-runtime APIs                                             │
│  └─ shared SSE job event stream                                    │
└────────────┬──────────────────┬───────────────────┬─────────────────┘
             │                  │                   │
             ▼                  ▼                   ▼
       PostgreSQL         Artifact/blob       External/local
       authoritative      storage             services
       structured data                         ├─ LLM
                                               ├─ TTS
                                               ├─ STT
                                               ├─ image
                                               ├─ Hermes
                                               ├─ market data
                                               └─ governed integrations
```

## Browser application

The supported browser app is `src/apps/web`.

### Runtime and libraries

The current web package uses:

- React 19.
- TypeScript 5.
- Vite 7.
- TanStack Router for route ownership.
- TanStack Query for server-owned state.
- Zustand for local workspace/view state where appropriate.
- React Hook Form for form state.
- Zod for validation/schema work.
- Mantine plus Omnix design primitives for shared UI.
- Lightweight Charts for trading visualization.
- Pixi.js/Live2D support for character surfaces.
- Vitest for frontend tests.
- Playwright for browser/e2e tests.
- OpenAPI-generated TypeScript types where practical.

### Route/module ownership

`src/apps/web/src/app/modules.ts` is the routed module catalog. `ModuleWorkspace.tsx` dispatches module definitions to specialized workspaces such as Chat, RPG, Storyteller, Podcast, Voice, STT, Image Generation, Trading, Settings, and platform views.

Feature code belongs under `src/apps/web/src/features/<feature>`. A feature should not introduce a second React app, a Flask template UI, Streamlit, a standalone vanilla-JS shell, or another framework-specific frontend.

### State ownership

Use server state for data whose truth lives in the backend:

- chat sessions/messages;
- RPG simulation/session/replay state;
- providers and models;
- jobs/runs and their progress;
- assets and reports;
- runtime/worker diagnostics;
- server-persisted settings;
- agent runs and acceptance/review state.

Use browser/local state for presentation:

- active route, tab, panel, and selection;
- collapsed/expanded UI;
- unsaved form input;
- playback position;
- temporary modals;
- trading chart layout/view state before persistence;
- appearance preferences that are intentionally browser-owned.

Feature code must not manufacture authoritative domain truth in the browser simply because the UI can calculate a plausible value.

## Typed API boundary

The web app uses a shared API client under `src/apps/web/src/api`. The web package can export the gateway OpenAPI schema and regenerate TypeScript types:

```bash
npm --workspace @omnix/web run api:schema
npm --workspace @omnix/web run api:types
npm --workspace @omnix/web run api:generate
npm --workspace @omnix/web run api:check
```

When backend API contracts change, generated API artifacts must be refreshed in the same change. New feature code should use the shared client rather than ad-hoc fetch wrappers unless a transport-specific reason is documented.

## FastAPI gateway

The browser-facing gateway lives under `src/app/gateway`. The development entry point is:

```bash
PYTHONPATH=src python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

The gateway currently owns or fronts:

- `/health` and `/api/health`.
- runtime and worker health/status.
- browser-facing chat/session and generation contracts.
- assistant context/tool projections.
- shared jobs/runs.
- shared assets and guarded text-asset reads.
- providers/models and refresh flows.
- settings/diagnostics/reports.
- replay/RPG browser contracts and compatibility handoff.
- story asset persistence helpers.
- model-residency diagnostics.
- shared `/events` streaming.

Gateway startup also performs recovery work such as detecting abandoned chat-generation jobs.

### Compatibility handoff

The gateway explicitly reports the classic browser UI as retired. Older FastAPI/domain routes may remain behind compatibility boundaries while typed gateway contracts are introduced. Compatibility code must delegate to domain/service modules rather than recreate authoritative logic in the web layer.

## Domain services

`src/app` contains the backend domains and platform services. Important areas include:

```text
src/app/
├─ agent_runtime/       planning, routing, capabilities, Pi execution, evidence, review
├─ assets/              shared artifact metadata/storage
├─ assist_core/         assistant core services
├─ assistant_context/   durable assistant context APIs/services
├─ assistant_memory/    assistant memory subsystem
├─ assistant_tools/     governed tool adapters, connections, credentials, policy projection
├─ characters/          character profiles/runtime support
├─ chat/                chat sessions/messages/generation jobs
├─ desktop_companion/   companion support subsystem
├─ gateway/             browser-facing FastAPI gateway
├─ image/               image provider/API domain
├─ jobs/                shared job/run infrastructure
├─ live_speech/         live-speech support
├─ persistence/         PostgreSQL adapters/transaction policy
├─ platform/            settings, diagnostics, reports, compatibility projections
├─ providers/           provider/model abstractions and adapters
├─ replay/              replay/checkpoint primitives
├─ rpg/                 deterministic RPG engine and APIs
└─ trading/             market data, research, replay, alerts, strategy/execution simulation
```

The repository also contains service entry points and compatibility modules outside these directories where needed.

## Shared provider and model layer

Features do not own provider discovery independently. They consume the shared provider/model facade and capability metadata.

A provider can advertise capabilities such as:

- LLM/chat;
- TTS;
- STT;
- voice cloning;
- image generation;
- capability-specific services.

The provider/model surfaces expose health/status, source/family, discovered models, capabilities, resource hints, latency/error metadata, and refresh operations. Settings define global or feature-specific defaults.

This abstraction allows local services such as LM Studio or dedicated GPU workers and cloud/OpenAI-compatible services to participate through the same feature contracts.

## Jobs and runs

Long-running work should enter the shared job/run system instead of blocking request handlers or inventing feature-local queues.

A job can carry:

- module and job type;
- priority;
- resource class;
- structured input references/payload;
- ordered stages;
- queue/execution status;
- progress current/total/message;
- logs;
- output references;
- cancellation/retry information.

Common resource classes include CPU plus GPU classes for LLM, TTS, STT, and image work. Feature workspaces can show filtered job subsets, while `/jobs` exposes the shared operational view.

Representative staged workflows:

```text
Image:       generate image → store image asset
Voice clone: ingest sample → build profile → preview → store profile
Story:       outline/plan → draft/action → store story asset
Podcast:     producer plan → script → speaking turns → mix → renderer
```

## Assets and artifacts

Generated and ingested outputs use the shared asset system. Assets carry identity, type, owning module, MIME type, storage location, metadata, and timestamps/references.

Examples include audio, voice samples/profiles, images, transcripts, stories, exports, checkpoints, and reports.

The gateway supports guarded UTF-8 reads for recognized text asset MIME types and enforces a bounded text-asset size. Binary/media outputs remain referenced by storage/media routes rather than being injected into JSON indiscriminately.

## Eventing and realtime

Omnix uses a shared event model.

### SSE

Server-Sent Events are the preferred transport for one-way server-to-browser changes such as:

- job creation/update/completion/failure/cancellation;
- long-running generation progress;
- provider/model refresh results;
- asset/report refresh triggers;
- diagnostics/status signals.

The gateway event stream emits event IDs and heartbeat comments so clients can maintain connection state and invalidate the appropriate TanStack Query caches.

### WebSockets / bidirectional realtime

WebSockets or equivalent bidirectional transports are reserved for truly interactive workflows such as live voice/conversation. A feature should not create an incompatible realtime protocol merely to avoid the shared event client.

## PostgreSQL persistence

`requirements.txt` declares PostgreSQL as the sole supported structured-data runtime database, using `psycopg` and `psycopg-pool`. `src/app/persistence` defines persistence/transaction policy.

The local compose file provides PostgreSQL 17 and persistent volume storage. Runtime services consume the database through `OMNIX_DATABASE_URL`; the Windows launcher uses a protected credential loader rather than writing the active DSN into general settings.

Structured persistence and artifact storage are intentionally different concerns:

```text
PostgreSQL                        Files/blob storage
──────────                        ──────────────────
records and relationships        generated media
jobs/runs                         large artifacts
sessions/state metadata          models/resources
settings where server-owned      logs/exports
agent/runtime records            referenced binary files
```

Browser `localStorage` is acceptable for intentionally local UI preferences or non-authoritative drafts, but it is not a replacement for server authority.

## Local service topology

Heavy ML dependencies can conflict, so Omnix supports separate processes/Conda environments/containers.

The current Windows operator launcher is configured around this topology:

```text
Web/Vite             : 5173
Launcher dashboard   : 5055
FastAPI gateway      : 8000
Hermes sidecar       : 8642 (when enabled)
TTS service          : 5101
STT service          : 5201
Image service        : 5301 (when enabled)
PostgreSQL           : 5432 by default
```

The exact environment paths in `start_all.bat` are workstation-specific. The architectural contract is the service boundary and environment variables, not those absolute paths.

### Image residency model

The image service is intentionally able to start without preloading heavyweight model weights. The Image Generation page discovers model state and can download, explicitly load, and unload weights. This keeps service availability separate from GPU residency and lets users reclaim VRAM.

## Generalized agent runtime

`src/app/agent_runtime` implements a generalized execution layer that can be used by multiple models/runtimes. Its purpose is to add authority, isolation, evidence, durability, and review around model-driven work.

### Logical flow

```text
User turn
   │
   ▼
Semantic classification / routing
   │
   ├─ CHAT / DIRECT
   ├─ WORKFLOW
   └─ AGENT
        │
        ▼
Plan / semantic task / TaskGraph
        │
        ▼
Capability + resource grants
        │
        ▼
Isolated workspace / broker execution
        │
        ▼
Candidate WorkspaceState + RunChangeSet
        │
        ├─ tests / acceptance
        ├─ evidence coverage
        ├─ coding-quality checks
        └─ independent review
                │
                ▼
          revise / recover / finish
```

### Agent-runtime responsibilities

The runtime contains separate modules for:

- semantic classification, normalization, and task parsing;
- routing and chat bridging;
- planning and turn plans;
- TaskGraph compilation/runtime/optimization/revision;
- capabilities and policy;
- workspace isolation and promotion;
- process environment and model gateway/fidelity;
- Pi runtime and broker/guard/provider extensions;
- trusted engineering/review skills;
- repository guidance;
- resource grants and budgets;
- authoritative run-change-set identity;
- acceptance and candidate test validation;
- evidence identity/coverage;
- coding-quality evaluation;
- independent review orchestration/runtime;
- quality recovery;
- subagents/workflows;
- persistence and debug logging.

The model is therefore responsible for reasoning and tool use, while Omnix is responsible for what authority exists, what workspace is in scope, what candidate is being evaluated, what evidence counts, and whether completion gates have actually passed.

## Capability and tool governance

The canonical capability registry lives in `src/app/agent_runtime/capabilities.py`. `src/app/assistant_tools/registry.py` projects assistant-visible tools from that registry.

Each capability includes fields such as:

```text
id / namespace
execution zone
read/create/mutate/delete/execute effect
risk level
scope type
approval policy
network and credential requirements
audited/enabled state
confirmation/destructive flags
provider/category
assistant/Hermes visibility
input/output schema
```

Execution zones separate worker-local operations from broker-mediated network/integration actions and model/context operations. Capability checks are independent from the model's preferences: a model cannot obtain a capability merely by deciding it needs one.

## Assistant integrations

Assistant integration adapters live under `src/app/assistant_tools`. Current code includes governed adapters/support for browser automation, Gmail, Calendar, Contacts, GitHub, Kasa/local home control, trading data, Hermes bridging, connections, credentials, and related capability/status surfaces.

External integrations should enter through this policy layer rather than exposing raw credentials or arbitrary host access to the model.

## RPG authority boundary

RPG is explicitly deterministic at its core. The simulation owns player, NPC, combat, quest, inventory/economy, world, XP, replay, and save/load truth. AI can narrate, propose, classify, or assist, but the UI and model must not invent committed state outside the simulation contract.

Hermes suggestions and sequence review are assistance layers around that authority, not alternate game-state stores.

## Trading authority boundary

Trading combines market-data adapters, analysis, replay, scanners, catalyst/research data, alerts, strategy logic, and paper execution/simulation. AI/Hermes can enrich research or produce analysis, but broker/order mutation authority is not implied by model access. The capability catalog's market quote path is read-only, and deterministic strategy/risk/execution components remain distinct from LLM reasoning.

## Settings architecture

Settings are described by a registry with:

- category and section;
- key/type/default;
- scope (`global`, module, local/browser, environment, status, etc.);
- persistence owner;
- writable/read-only state;
- application timing;
- restart requirements;
- search aliases.

This prevents the UI from pretending an environment-owned value can be mutated live. Environment/status settings are presented as read-only unless an explicit backend mutation contract exists.

## Repository architecture map

```text
omnix/
├─ docs/                         product/developer documentation
├─ resources/                    models, data, logs, generated/runtime resources
├─ scripts/                      setup, schema, launcher, credential helpers
├─ src/
│  ├─ app/                       Python backend domains/platform/runtime
│  │  ├─ agent_runtime/
│  │  ├─ assistant_tools/
│  │  ├─ assets/
│  │  ├─ chat/
│  │  ├─ gateway/
│  │  ├─ jobs/
│  │  ├─ persistence/
│  │  ├─ providers/
│  │  ├─ rpg/
│  │  └─ trading/
│  ├─ apps/web/                  supported React browser application
│  │  ├─ src/app/
│  │  ├─ src/api/
│  │  ├─ src/design/
│  │  ├─ src/events/
│  │  ├─ src/features/
│  │  └─ tests/
│  └─ tests/                     Python/domain/runtime tests
├─ docker-compose.postgres.yml   authoritative local PostgreSQL service
├─ requirements.txt
├─ package.json
├─ README.md
└─ SPEC.md
```

## Architecture invariants for new work

Before adding a new feature, verify that the change preserves these rules:

- Add browser UI to the existing web app.
- Keep authoritative state in backend/domain services.
- Add typed API contracts instead of feature-specific transport hacks.
- Use the shared provider/model registry.
- Use the shared job system for long-running work.
- Store outputs through the shared asset/artifact model.
- Use the shared event transport.
- Register settings in the settings infrastructure with an explicit persistence owner.
- Register agent/tool authority in the canonical capability system.
- Preserve workspace/candidate/evidence identity for agent-generated changes.
- Keep secrets in credential/environment stores, not browser state or committed defaults.
- Do not reintroduce the retired classic browser UI.

See [DEVELOPMENT.md](DEVELOPMENT.md) for the implementation workflow.
