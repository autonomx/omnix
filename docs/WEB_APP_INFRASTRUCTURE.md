# Omnix Web App Infrastructure

Omnix uses one shared browser application infrastructure for every user-facing feature. RPG, chatbot, storyteller, podcast generation, voice, voice cloning, STT, TTS, image generation, providers, jobs, assets, settings, and diagnostics must be implemented as modules inside the same web app shell.

## Required Stack

```text
Frontend runtime: React + TypeScript + Vite
Server state:     TanStack Query
Local UI state:   Zustand
Forms:            React Hook Form
Validation:       Zod
Styling:          Shared Omnix design system
Testing:          Vitest + Playwright
Realtime:         Shared SSE/WebSocket event client
Backend:          FastAPI + Pydantic
```

## Non-Negotiable Rules

1. All new browser-facing work must live under `apps/web`.
2. No feature module may introduce a separate frontend framework, standalone vanilla JS app, Flask template UI, Streamlit UI, or one-off browser shell.
3. Feature modules must use the shared API client for backend communication.
4. Feature modules must use the shared event client for streaming, progress, narration, job status, provider health, and diagnostics.
5. Server-owned data must be read through TanStack Query hooks or generated wrappers around them.
6. Local UI state must stay view-only and must not duplicate backend truth.
7. Long-running feature work must use the shared job/run model.
8. Generated files, reports, transcripts, checkpoints, images, and audio must use the shared asset/artifact model.
9. Provider and model selection must go through the shared provider/model registry.
10. Shared design-system primitives must be used for layout, navigation, forms, panels, progress, logs, transcript views, audio controls, and diagnostics.

## Module Layout

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
├── jobs/
├── assets/
├── settings/
└── diagnostics/
```

Each feature module may own feature-specific components, schemas, hooks, and routes, but it may not own platform infrastructure.

Recommended module shape:

```text
features/<module>/
├── api.ts
├── components/
├── hooks.ts
├── routes.tsx
├── schemas.ts
└── tests/
```

## Shared Frontend Layers

```text
apps/web/src/
├── app/             Application shell, routing, providers, and module registry
├── api/             Shared API client and endpoint helpers
├── components/      Shared app-level components
├── design-system/   Shared UI primitives and design tokens
├── events/          Shared SSE/WebSocket event client
├── features/        Feature modules
└── state/           Shared local UI state utilities
```

## Backend Contract

The backend must expose coherent API namespaces and typed response contracts.

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

## State Ownership

Backend-owned state includes provider execution, model state, jobs, assets, reports, diagnostics, persisted sessions, generated files, and deterministic RPG truth.

Frontend-owned state is limited to view state such as active route, selected panel, expanded sections, focused input, selected asset, filters, local draft input, playback UI state, and transient dialogs.

The frontend may render backend truth, but it must not invent authoritative truth.

## Realtime Standard

Use Server-Sent Events first for one-way backend-to-frontend updates:

- job progress
- streaming text
- RPG narration/background work
- report generation
- provider health
- diagnostics
- asset generation progress

Use WebSockets only where bidirectional realtime behavior is necessary, such as live voice conversation.

## Migration Policy

1. Establish the shared app shell under `apps/web`.
2. Add module entrypoints for every existing feature.
3. Move existing browser behavior into feature modules incrementally.
4. Keep legacy UI only as temporary compatibility.
5. Do not add new behavior to legacy frontend entrypoints.
6. Remove legacy frontend files after parity is reached.

## Acceptance Criteria

- `apps/web` is the only supported browser app.
- Navigation includes RPG, Chatbot, Storyteller, Podcast, Voice, Voice Cloning, STT, Image Generation, Providers, Jobs, Assets, Settings, and Diagnostics.
- Shared API and event clients exist.
- Shared design-system primitives exist.
- Each module has a route and placeholder workspace before feature migration begins.
- Playwright covers app shell navigation and module entrypoints.
