# Omnix Documentation

Omnix is a modular, local-first AI workstation. The application combines conversational AI, governed tools and agents, deterministic RPG simulation, long-form writing, podcast and speech production, transcription, image generation, trading research, model/provider management, shared jobs and artifacts, settings, and diagnostics in one browser application backed by FastAPI services.

This directory documents the application that is currently implemented on `main`. When a design document and the running source disagree, the current source code defines shipped behavior while [`../SPEC.md`](../SPEC.md) remains the authority for platform architecture rules and invariants.

## Start here

| Document | Use it for |
| --- | --- |
| [FEATURES.md](FEATURES.md) | Complete feature and workspace catalog, including cross-cutting assistant and agent capabilities |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Frontend, gateway, jobs, assets, providers, persistence, agent runtime, workers, events, and trust boundaries |
| [SETUP.md](SETUP.md) | Local installation, PostgreSQL, gateway/web startup, optional model services, Hermes, testing, and troubleshooting |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Contribution rules, module/API patterns, settings, jobs/assets/events, generated API types, and validation |
| [OPERATIONS.md](OPERATIONS.md) | Service topology, health checks, incident triage, recovery, assets, secrets, and runtime safety |
| [HERMES_SIDECAR_SETUP.md](HERMES_SIDECAR_SETUP.md) | Optional Hermes Agent sidecar installation and configuration |
| [OPENAI_COMPATIBILITY.md](OPENAI_COMPATIBILITY.md) | Standalone `/v1` compatibility server, governed agent-model routes, upstream provider configuration, SDK examples, and limitations |
| [index.html](index.html) | Self-contained browsable HTML version of the documentation overview |

## Application map

The supported browser UI lives under `src/apps/web`. `/` redirects to `/chatbot`.

| Route | Workspace | What it provides |
| --- | --- | --- |
| `/chatbot` | Chat | Sessions, streaming responses, attachments, live voice, characters, memory, tools, research, artifacts, and agent/coding runs |
| `/rpg` | RPG | Deterministic RPG sessions, narrative turns, campaign creation, player/world rails, inventory, quests, combat, journal, replay/checkpoints, Hermes-assisted flows, jobs, and reports |
| `/storyteller` | Storyteller | Drafting, continuation, rewrite/expand/dialogue/summarize actions, story mode, outline/library workflows, assets, and exports |
| `/podcast` | Podcast | Podcast planning, speaker profiles, generated scripts, voice assignment, TTS previews, mixing/stitching, and audio output |
| `/voice` | Voice Studio | Single- and multi-speaker TTS, voice assignments, playback, output tuning, audio effects, profile previews, and voice-profile creation workflows |
| `/voice-cloning` | Voice Cloning | Sample-based voice-profile jobs, reference text, language/quality controls, previews, and profile assets |
| `/stt` | Speech to Text | Audio/voice-sample transcription jobs, provider/language controls, progress, and transcript assets |
| `/image-generation` | Image Generation | Local image-model discovery/status, explicit download/load/unload, generation jobs, retry/cancel, latest result, and asset gallery |
| `/trading` | Trading | Multi-chart market research, provider bindings, instruments/formulas, intervals, indicators, drawings, alerts, scanner, replay, strategies, paper simulation, and workspace persistence/export |
| `/providers` | Providers | Shared provider registry, health/capabilities/latency/error summaries, and refresh |
| `/models` | Models | Installed/remote model inventory, capability/location/VRAM hints, defaults, and refresh |
| `/jobs` | Jobs / Runs | Shared queue, status, stages, progress, resource class, logs, live event state, and cancellation |
| `/assets` | Assets | Shared generated audio, images, transcripts, reports, checkpoints, exports, and related metadata |
| `/reports` | Reports | Generated run/report artifacts, including RPG and diagnostics-oriented output |
| `/settings` | Settings | Appearance/accessibility, providers, trading data, models/runtime, assistant, voice, narrative, RPG, image/STT, integrations, operations, and developer settings |
| `/diagnostics` | Diagnostics | Runtime/service health, event-stream state, logs, and troubleshooting information |

The primary mode switcher exposes Chat, RPG, Storyteller, Podcast, Voice, Image Generation, and Trading. Some lower-level platform workspaces remain directly routable without being shown in the primary sidebar.

## Platform at a glance

```text
Browser
  └─ Omnix Web — React + TypeScript + Vite
       ├─ TanStack Router / Query
       ├─ Zustand local UI state
       ├─ React Hook Form + Zod
       ├─ shared design system
       ├─ typed API client
       └─ shared event client
              │
              ▼
FastAPI Web Gateway
  ├─ chat / assistant context
  ├─ RPG and replay projections
  ├─ provider + model facade
  ├─ shared jobs / runs
  ├─ shared assets / reports
  ├─ settings + diagnostics
  ├─ agent runtime + governed capabilities
  └─ SSE event stream
       │
       ├─ PostgreSQL authoritative structured persistence
       ├─ local artifact/blob storage
       └─ local or remote services
            ├─ LLM providers (for example LM Studio / OpenAI-compatible)
            ├─ TTS
            ├─ STT
            ├─ image generation
            ├─ Hermes sidecar when enabled
            ├─ market-data providers
            └─ governed integrations such as browser, GitHub, Google, and Kasa
```

The architectural rule is simple: feature modules share the same web shell, API/event boundaries, provider registry, job/run model, asset system, settings infrastructure, and diagnostics. Backend services own authoritative domain state; the browser owns presentation and transient UI state.

```omnix-diagram documentation-pipeline
```

## Documentation workflow

Use the guides in this order when working on a change:

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) to identify the layer that owns the behavior.
2. Read [FEATURES.md](FEATURES.md) to understand the affected user-facing workspace and shared concepts.
3. Use [SETUP.md](SETUP.md) to reproduce the relevant local service topology.
4. Use [DEVELOPMENT.md](DEVELOPMENT.md) for implementation patterns, tests, migrations, and the PR checklist.
5. Use [OPERATIONS.md](OPERATIONS.md) to diagnose runtime failures or preserve recovery context.

The browsable [index.html](index.html) mirrors this workflow with search, route cards, architecture boundaries, quick-start commands, triage guidance, and a FAQ. Keep it aligned when a new top-level workspace, service, or shared platform concept is introduced.

## HTML guide pages

The Markdown files are the editable documentation sources. Browser-facing HTML counterparts are generated for every referenced guide so local links do not open raw Markdown in Chrome:

- `docs/README.html`, `FEATURES.html`, `ARCHITECTURE.html`, `SETUP.html`, `DEVELOPMENT.html`, `OPERATIONS.html`, `HERMES_SIDECAR_SETUP.html`, and `OPENAI_COMPATIBILITY.html`.
- `README.html` and `SPEC.html` at the repository root for the root-level guides linked from the portal.

After changing a Markdown source, regenerate the HTML pages from the repository root:

```bash
python docs/render_docs.py
```

The renderer is dependency-free and rewrites internal `.md` links to their `.html` counterparts. Do not edit generated guide pages directly; update the Markdown source and regenerate them.

Images should be committed under `docs/images` and referenced from a guide with a relative path such as `![Trading workspace](images/trading.png)`. The renderer turns standalone Markdown images into responsive, captioned HTML figures. Use the `omnix-diagram` fenced markers for native HTML/CSS diagrams that should appear in the generated guide pages.

## Quick local development

The full setup, including PostgreSQL and optional workers, is in [SETUP.md](SETUP.md). The shortest development path is:

```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
npm install

# Start the FastAPI web gateway
PYTHONPATH=src python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000

# In another terminal, start the browser app
npm run web:dev
```

The Vite development server listens on port `5173` and proxies `/api` and `/events` to the gateway on `127.0.0.1:8000`. A PostgreSQL instance and `OMNIX_DATABASE_URL` are required for code paths that use authoritative structured persistence; see [SETUP.md](SETUP.md).

## Useful validation commands

```bash
npm run web:typecheck
npm run web:test
npm run web:test:e2e
npm run web:build
pytest
```

For generated frontend API contracts:

```bash
npm --workspace @omnix/web run api:generate
npm --workspace @omnix/web run api:check
```

## Source-of-truth locations

- `src/apps/web/src/app/modules.ts` — routed application module catalog.
- `src/apps/web/src/features/` — browser feature workspaces and shared assistant UI.
- `src/app/gateway/` — browser-facing FastAPI gateway and compatibility handoff.
- `src/app/agent_runtime/` — generalized agent planning, routing, execution, evidence, review, workspaces, and recovery.
- `src/app/assistant_tools/` — governed assistant-tool adapters and policy projection.
- `src/app/providers/` — provider/model integration layer.
- `src/app/jobs/` — shared job/run contracts and stores.
- `src/app/assets/` — shared asset/artifact system.
- `src/app/rpg/` — deterministic RPG domain and APIs.
- `src/app/trading/` — trading data, research, replay, alerts, strategies, execution simulation, and related APIs.
- `src/app/persistence/` — PostgreSQL persistence contracts and transaction policy.
- `resources/` — models, data, logs, and generated/runtime resources.
- `../SPEC.md` — platform architecture rules.

## Compatibility boundary

The classic `src/templates` and `src/static` browser UI is retired. `src/run_app.py` and older feature routes can still exist as backend compatibility surfaces while contracts migrate, but new browser behavior belongs in `src/apps/web` and should use the shared gateway, jobs, assets, providers, events, and design system.
