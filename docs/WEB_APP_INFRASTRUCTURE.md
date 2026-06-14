# Omnix Web App Infrastructure

Omnix is a modular local-first AI workstation. It must behave like one coherent application, not a collection of unrelated AI demos. This document defines the shared web-app architecture that every browser-facing Omnix feature must converge on.

This is a documentation-only architecture decision. It defines the target platform standard and migration rules; it does not imply that the infrastructure has already been implemented.

## Scope

The shared infrastructure applies to the entire Omnix application, including:

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
├── Provider Console
├── Model Manager
├── Jobs / Runs
├── Assets / Artifacts
├── Reports
├── Settings
└── Diagnostics
```

No feature is allowed to become its own independent web application. Each feature may own feature-specific screens, workflows, contracts, and components, but all features must share the same platform shell, frontend stack, API boundary, event model, state rules, design system, and testing expectations.

## Architecture Decision

All user-facing browser UI must converge on one shared web app infrastructure.

Target standard:

```text
Frontend runtime: React + TypeScript + Vite
Server state:     TanStack Query
Local UI state:   Zustand
Forms:            React Hook Form
Validation:       Zod
API typing:       OpenAPI-generated TypeScript types where practical
Styling:          Shared Omnix design system
Testing:          Vitest + Playwright
Realtime:         Shared SSE/WebSocket event client
Backend:          FastAPI + Pydantic
```

The existing legacy UI may remain temporarily during migration. New browser-facing work should be designed for the shared web app, not for legacy standalone entrypoints.

## Non-Negotiable Rules

1. All browser-facing features must use the shared Omnix app shell once it exists.
2. No feature module may introduce a separate frontend framework, standalone vanilla JS app, Flask template UI, Streamlit UI, or one-off browser shell.
3. Feature modules must communicate with the backend through the shared typed API client.
4. Feature modules must use the shared event client for streaming, progress, narration, job status, provider health, diagnostics, and asset generation events.
5. Backend-owned data must be read through TanStack Query hooks or generated wrappers around them.
6. Local UI state must stay view-only and must not duplicate backend truth.
7. Long-running feature work must use the shared job/run model.
8. Generated files, reports, transcripts, checkpoints, images, and audio must use the shared asset/artifact model.
9. Provider and model selection must go through the shared provider/model registry.
10. Shared design-system primitives must be used for layout, navigation, forms, panels, progress, logs, transcript views, audio controls, and diagnostics.
11. Feature modules may add specialized components only when shared components are not sufficient.
12. Shared infrastructure changes must be made deliberately at the platform layer, not hidden inside a feature module.

## Platform Shell

The target web app shell owns global application structure:

```text
OmnixAppShell
├── Global navigation
├── Feature routing
├── Provider/model status
├── Job/run status
├── Asset/artifact access
├── Settings access
├── Diagnostics access
├── Shared notifications
├── Shared error/loading states
└── Active feature workspace
```

Feature modules render inside the active workspace. They do not define their own top-level app lifecycle.

## Module Layout Target

```text
apps/web/src/features/
├── rpg/
├── chatbot/
├── storyteller/
├── podcast/
├── voice/
├── voice-cloning/
├── stt/
├── image-generation/
├── providers/
├── models/
├── jobs/
├── assets/
├── reports/
├── settings/
└── diagnostics/
```

Recommended module shape:

```text
features/<module>/
├── api.ts          Feature-specific endpoint wrappers around the shared API client
├── components/    Feature-specific UI components
├── hooks.ts       Feature-specific TanStack Query and UI hooks
├── routes.tsx     Feature workspace route registration
├── schemas.ts     Zod schemas or generated type adapters
└── tests/         Unit and UI tests for module behavior
```

Feature modules may own behavior. They may not own platform infrastructure.

## Shared Frontend Layers

```text
apps/web/src/
├── app/             Application shell, routing, providers, and module registry
├── api/             Shared API client and endpoint helpers
├── components/      Shared app-level components
├── design-system/   Shared UI primitives and design tokens
├── events/          Shared SSE/WebSocket event client
├── features/        Feature modules
├── state/           Shared local UI state utilities
└── test/            Shared test setup and helpers
```

## Backend API Contract

The backend should expose coherent API namespaces and typed response contracts.

```text
/api/chat
/api/rpg
/api/storyteller
/api/podcast
/api/voice
/api/voice-cloning
/api/stt
/api/tts
/api/image
/api/providers
/api/models
/api/jobs
/api/assets
/api/reports
/api/settings
/api/diagnostics
/events
```

The API must preserve a clean ownership boundary:

- The backend owns persisted state, generated artifacts, provider execution, deterministic RPG state, jobs, model status, diagnostics, and long-running workflow truth.
- The frontend owns rendering, input, local layout, selected panels, playback UI state, filters, transient dialogs, optimistic loading states, and visualization.

The frontend may display backend truth, but it must not invent authoritative truth.

## Shared State Rules

Use server-state infrastructure for data owned by the backend:

```text
sessions
messages
RPG turns and state views
provider health
model registry
jobs and runs
asset metadata
report metadata
settings loaded from backend
diagnostics events
```

Use local UI state only for view concerns:

```text
active route
selected panel
expanded/collapsed sections
focused input
selected asset
local draft input
filters and sorting
audio playback UI state
transient modals
```

Never mirror backend truth in local state unless the mirror is temporary, clearly scoped, and reconciled through the shared API layer.

## Realtime Standard

Use Server-Sent Events first for one-way backend-to-frontend updates:

- Job progress
- Streaming text
- RPG narration and background work
- Report generation
- Provider health
- Diagnostics
- Asset generation progress
- Long-running audio, image, podcast, and voice-cloning workflows

Use WebSockets only where bidirectional realtime behavior is necessary, such as live voice conversation.

Feature modules must not create incompatible custom realtime transports.

## Shared Systems

### Provider and Model Registry

All modules must use one provider/model registry for local and cloud-compatible providers.

Examples:

```text
LM Studio
llama.cpp
OpenAI-compatible APIs
OpenRouter
Cerebras
TTS services
STT services
Image generation services
Future adapters
```

Feature modules may request capabilities such as chat, embedding, TTS, STT, image, or voice cloning, but provider selection and health reporting must be centralized.

### Job and Run System

Long-running work must use the shared job/run system.

Examples:

```text
RPG autoplay
RPG report generation
podcast script generation
podcast audio generation and mixing
voice cloning preprocessing/training/preview
STT transcription and alignment
image generation
story generation
batch diagnostics
```

Jobs should expose status, progress, logs, errors, output assets, and cancellation where practical.

### Asset and Artifact System

Generated and uploaded files must use the shared asset/artifact model.

Examples:

```text
audio files
voice samples
voice profiles
images
transcripts
stories
podcast scripts
reports
RPG checkpoints
RPG autoplay outputs
logs
exports
```

Feature modules may define specialized metadata, but storage, browsing, preview, and lifecycle behavior should be shared.

### Design System

Omnix uses one design system across modules.

Required primitives:

- App shell
- Sidebar navigation
- Top status bar
- Workspace layout
- Panel/card layout
- Buttons
- Form controls
- Tabs
- Dialogs
- Toasts/notifications
- Progress indicators
- Log viewers
- Transcript/message views
- Audio controls
- Asset cards
- Diagnostics views

Visual direction:

- Dark-first workstation UI
- High information density without hiding critical state
- Consistent status and accent treatment
- Keyboard-accessible controls
- Clear module navigation
- Desktop-first layout with graceful smaller-screen behavior

## Feature Module Requirements

### RPG

The RPG module must keep deterministic simulation truth backend-owned.

Backend-owned:

- Simulation state
- Player state
- Party state
- NPC state and memory
- Location and travel state
- Inventory and economy state
- Combat state
- Quest and story arc state
- XP and leveling
- Save/load and replay truth
- Autoplay runs and reports

Frontend-owned:

- RPG workstation layout
- Command input
- Scene rendering
- Transcript rendering
- Journal display
- Party/inventory/combat panels
- Report visualization
- Local panel expansion and focus state

### Chatbot

The chatbot module must use the shared provider/model selector, shared chat API contract, shared streaming/event behavior, backend-owned conversation history, and shared transcript/message components.

### Storyteller

The storyteller module must use shared providers, prompt templates, jobs for long-running generation, shared story/outlines/exports as assets, and shared editor/report components.

### Voice / TTS

The TTS module must use shared providers, jobs for non-trivial generation, shared audio assets, and shared playback/progress/diagnostics components.

### Voice Cloning

The voice cloning module must use shared asset ingestion for source samples, jobs for preprocessing/training/preview, backend-owned voice profile metadata, and shared forms/progress/asset/diagnostics components.

### STT / Transcription

The STT module must use shared asset ingestion for uploaded or recorded audio, jobs for transcription and alignment, transcript assets, and shared transcript/diagnostics components.

### Podcast

The podcast module must use shared jobs for planning, script generation, speaker assignment, TTS generation, mixing, and export. Scripts, stems, final audio, metadata, and reports must be assets.

### Image Generation

The image module must use shared providers, jobs for generation, image assets with metadata, and shared prompt/progress/asset/diagnostics components.

### Providers, Models, Settings, and Diagnostics

These are platform modules. They must not be duplicated inside feature modules.

## Migration Policy

1. Keep this document as the architecture standard until the implementation catches up.
2. Establish the shared app shell before migrating feature-specific UI in depth.
3. Add feature module entrypoints for existing Omnix features.
4. Move existing browser behavior into modules incrementally.
5. Keep legacy UI only as temporary compatibility.
6. Do not add new feature work to legacy browser entrypoints once the shared app shell exists.
7. Remove legacy frontend files after parity is reached.
8. Treat deviations from this standard as architecture exceptions that must be documented.

## Acceptance Criteria

- `apps/web` is the only supported browser app after migration.
- Navigation includes RPG, Chatbot, Storyteller, Podcast, Voice, Voice Cloning, STT, Image Generation, Providers, Models, Jobs, Assets, Reports, Settings, and Diagnostics.
- Shared API and event clients exist.
- Shared design-system primitives exist.
- Shared provider/model registry exists.
- Shared job/run system exists.
- Shared asset/artifact system exists.
- Each feature module has a route and workspace before deep feature migration begins.
- Playwright covers app shell navigation and module entrypoints.

## Non-Goals

- Omnix is not a set of independent AI demos.
- Individual features must not own separate app infrastructure.
- The frontend must not duplicate backend simulation, provider, job, or artifact truth.
- Local-first support must not prevent cloud-compatible providers from using the same abstractions.
- Infrastructure should not be rewritten per feature.
