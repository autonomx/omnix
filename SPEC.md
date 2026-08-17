# Omnix - Platform Specification

## Project Overview

- **Project Name**: Omnix
- **Company**: Autonomx
- **Type**: Modular local-first AI workstation platform
- **Core Functionality**: A unified AI application suite for chat, role-playing, storytelling, voice, speech-to-text, text-to-speech, voice cloning, podcast generation, image generation, provider management, diagnostics, and long-running AI workflows.
- **Target Users**: Users who want one consistent local or hybrid AI workstation for text, voice, image, storytelling, RPG simulation, and automation workflows.

## Product Architecture

Omnix is a single platform with multiple feature modules. Feature modules must not introduce isolated web stacks, one-off frontend frameworks, or separate browser apps.

```text
Omnix Platform
├── Web App Shell
│   ├── RPG
│   ├── Chatbot
│   ├── Storyteller
│   ├── Podcast Generator
│   ├── Voice / TTS
│   ├── Voice Cloning
│   ├── STT / Transcription
│   ├── Image Generation
│   ├── Provider Console
│   ├── Model Manager
│   ├── Jobs / Runs
│   ├── Assets / Artifacts
│   ├── Reports
│   ├── Settings
│   └── Diagnostics
├── FastAPI Backend
├── Shared Provider Registry
├── Shared Job / Run System
├── Shared Asset Library
├── Shared Event Stream
└── External or Local Model Services
```

## Architecture Principles

1. **One app infrastructure**: All browser-facing features must use the shared Omnix web app infrastructure.
2. **One app shell**: RPG, chatbot, podcast, voice, storyteller, image, providers, diagnostics, and future modules live under the same web shell.
3. **No feature-specific frontend stacks**: No new standalone vanilla JS apps, Flask template UIs, Streamlit tools, or one-off web frontends for individual features.
4. **Backend owns authoritative state**: Simulation, provider execution, jobs, artifacts, model state, and long-running workflows are backend-owned.
5. **Frontend renders and controls**: The frontend owns layout, user input, local panel state, playback controls, visualization, and optimistic UI only.
6. **Typed boundaries**: Frontend/backend communication must flow through typed API contracts.
7. **Shared providers**: All modules use the shared provider registry rather than implementing provider selection independently.
8. **Shared jobs**: Long-running work, including podcast generation, voice cloning, image generation, RPG autoplay, and report generation, must use a shared job/run model.
9. **Shared artifacts**: Generated audio, images, transcripts, reports, checkpoints, and exports must use one asset/artifact system.
10. **Local-first, cloud-capable**: Omnix must support local providers such as LM Studio, local TTS/STT/image services, and cloud-compatible providers through the same provider abstractions.

## Target Web App Infrastructure

The current frontend package is a placeholder. The target application infrastructure is:

```text
Frontend runtime: React + TypeScript + Vite
Server state:     TanStack Query
Local UI state:   Zustand
Forms:            React Hook Form
Validation:       Zod
API typing:       OpenAPI-generated TypeScript types where practical
Styling:          One shared design system
Testing:          Vitest + Playwright
Realtime:         Shared SSE/WebSocket event client
```

### Frontend Responsibilities

The frontend must provide:

- A unified Omnix app shell with global navigation.
- Feature workspaces for RPG, chat, voice, podcast, storyteller, image generation, providers, settings, and diagnostics.
- Shared layout primitives, panels, buttons, inputs, cards, dialogs, logs, status indicators, and progress views.
- A shared typed API client.
- A shared event client for job progress, streaming responses, narration, provider status, and diagnostics.
- Shared asset browsing and playback controls for audio, images, reports, and transcripts.
- Shared error, loading, retry, and empty states.

### Frontend State Rules

Use server-state tools for data owned by the backend:

```text
session data
chat messages persisted by backend
RPG turn/state/journal data
provider status
job status
asset metadata
report metadata
model registry data
settings loaded from backend
```

Use local UI state only for view concerns:

```text
active route
selected panel
expanded/collapsed sections
local draft input
currently selected asset
audio playback UI state
transient modals
local filters and sorting
```

## Backend Infrastructure

The backend standard is Python with FastAPI, Pydantic, Uvicorn, and async-compatible service boundaries. The backend coordinates feature modules, providers, jobs, assets, event streaming, diagnostics, and persistence.

```text
Backend
├── API routes
├── Feature services
├── Provider registry
├── Job/run manager
├── Asset/artifact manager
├── Event stream broker
├── Diagnostics and health checks
├── Persistence adapters
└── External model service adapters
```

### Backend API Surface

The backend should expose one coherent API namespace:

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

### Realtime and Streaming

Use one shared event model across the application.

- **SSE** is preferred for one-way server-to-client updates such as job progress, report generation, streaming text, background narration, provider health, and diagnostics.
- **WebSockets** are reserved for true bidirectional realtime workflows such as live voice conversation or highly interactive sessions.
- Feature modules must not create incompatible custom realtime transports.

## Feature Modules

Each module may have specialized screens and behavior, but it must use the shared app shell, API client, event client, provider registry, job system, asset system, and design system.

### RPG Module

The RPG module is a deterministic AI RPG engine.

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

Critical rule: The UI may display RPG truth, but it must not invent authoritative simulation truth.

### Chatbot Module

The chatbot module provides text conversation over the shared provider registry.

Required behavior:

- Use the shared provider/model selector.
- Use the shared chat API contract.
- Support streaming through the shared event client.
- Store and display conversation history through backend-owned session data.
- Reuse shared message, transcript, prompt, settings, and diagnostics components.

### Storyteller Module

The storyteller module provides long-form generation, branching story drafts, and narrative workflows.

Required behavior:

- Use shared providers and prompt templates.
- Use jobs for long-running generation.
- Save generated stories, outlines, variants, and exports as assets.
- Reuse shared editor, transcript, asset, and report components.

### Voice / TTS Module

The TTS module generates speech from text using local or cloud providers.

Required behavior:

- Use the shared provider registry.
- Use jobs for non-trivial generation.
- Store generated audio as assets.
- Reuse shared audio playback, waveform/progress, logs, and diagnostics components.

### Voice Cloning Module

The voice cloning module creates or manages voice profiles.

Required behavior:

- Use a shared asset pipeline for source samples, generated previews, and trained/derived voice metadata.
- Use jobs for training, embedding, preprocessing, and preview generation.
- Keep voice profile metadata backend-owned.
- Reuse shared forms, progress, asset, and diagnostics components.

### STT / Transcription Module

The STT module converts speech/audio to text.

Required behavior:

- Use shared asset ingestion for uploaded or recorded audio.
- Use jobs for transcription and alignment.
- Save transcripts as assets.
- Reuse shared transcript viewer and diagnostics components.

### Podcast Module

The podcast module generates multi-speaker scripts and audio.

Required behavior:

- Use the shared job system for planning, script generation, speaker assignment, TTS generation, mixing, and export.
- Store scripts, audio stems, final audio, metadata, and reports as assets.
- Use the shared provider registry for script generation and voice synthesis.
- Reuse shared progress, logs, audio playback, and export components.

### Image Generation Module

The image module generates portraits, scenes, covers, and other visual assets.

Required behavior:

- Use the shared provider registry.
- Use jobs for generation.
- Store generated images and metadata as assets.
- Reuse shared asset browsing, prompt, progress, and diagnostics components.

### Provider Console and Model Manager

Provider and model configuration is shared by every feature.

Required behavior:

- One provider registry for LM Studio, llama.cpp, Cerebras, OpenRouter, OpenAI-compatible providers, TTS services, STT services, image services, and future adapters.
- One health/status surface.
- One model discovery surface where supported.
- One diagnostics surface for connection errors, latency, configuration, and capability reporting.

## Local Service Topology

Omnix supports local development and local-first execution. Heavy model services may run as separate processes, Conda environments, or containers because GPU, PyTorch, audio, and model dependencies often conflict.

Recommended service model:

```text
omnix-web        Web app development server or built frontend
omnix-api        FastAPI backend
omnix-worker     Background jobs and long-running workflows
omnix-llm        Local LLM provider or proxy, such as LM Studio or llama.cpp
omnix-tts        TTS service
omnix-stt        STT service
omnix-image      Image generation service
```

The platform must support both:

```text
Local process mode:
- Vite web app
- FastAPI backend
- external LM Studio
- external TTS/STT/image services

Compose mode:
- web service
- api service
- worker service
- optional GPU-backed model services
```

## Repository Structure Target

```text
omnix/
├── src/
│   ├── app/
│   ├── apps/
│   │   └── web/
│   │       ├── package.json
│   │       ├── vite.config.ts
│   │       ├── tsconfig.json
│   │       ├── src/
│   │       │   ├── app/
│   │       │   ├── api/
│   │       │   ├── components/
│   │       │   ├── design-system/
│   │       │   ├── events/
│   │       │   ├── features/
│   │       │   │   ├── rpg/
│   │       │   │   ├── chatbot/
│   │       │   │   ├── storyteller/
│   │       │   │   ├── podcast/
│   │       │   │   ├── voice/
│   │       │   │   ├── voice-cloning/
│   │       │   │   ├── stt/
│   │       │   │   ├── image-generation/
│   │       │   │   ├── providers/
│   │       │   │   ├── jobs/
│   │       │   │   ├── assets/
│   │       │   │   ├── settings/
│   │       │   │   └── diagnostics/
│   │       │   └── state/
│   │       └── tests/
│   ├── api/
│   ├── services/
│   ├── providers/
│   ├── jobs/
│   ├── assets/
│   ├── rpg/
│   └── tests/
├── resources/
│   ├── data/
│   └── models/
├── docs/
├── docker/
├── docker-compose.yml
├── requirements.txt
├── package.json
└── SPEC.md
```

Until the target structure is fully migrated, legacy files may remain for compatibility, but new browser-facing work must target the shared web app architecture.

## Design System

Omnix uses one shared design system across all modules.

Required shared primitives:

- App shell
- Sidebar navigation
- Top status bar
- Workspace layout
- Panel/card layout
- Form controls
- Buttons
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
- Clear module navigation
- High information density without hiding critical state
- Consistent accent and status colors
- Accessible keyboard and screen-reader behavior
- Responsive layout for desktop-first use with graceful smaller-screen behavior

## Shared Data Models

The following conceptual models should be shared across modules where practical:

```text
Provider
Model
Session
Message
PromptTemplate
Job
Run
Asset
Artifact
Report
DiagnosticEvent
Settings
```

RPG-specific models remain feature-owned but must cross the frontend/backend boundary through typed contracts:

```text
RpgSession
TurnContract
SimulationStateView
NarrationEnvelope
JournalSummary
NpcMemorySummary
PartyState
CombatState
InventoryState
QuestState
AutoplayReport
```

## Testing and Acceptance Criteria

### Platform Acceptance

- [ ] All new browser-facing features live under the shared web app infrastructure.
- [ ] No new standalone frontend framework or vanilla JS mini-app is introduced for a feature module.
- [ ] Shared app shell supports navigation across RPG, chat, voice, podcast, storyteller, image, providers, jobs, assets, settings, and diagnostics.
- [ ] Shared API client is used for backend communication.
- [ ] Shared event client is used for streaming and progress.
- [ ] Shared provider registry is used by all AI modules.
- [ ] Shared job/run system is used for long-running workflows.
- [ ] Shared asset/artifact system stores generated files and metadata.
- [ ] Shared design system components are used across modules.
- [ ] Playwright coverage exists for core navigation and feature entrypoints.

### RPG Acceptance

- [ ] Frontend renders backend-owned RPG state without inventing simulation truth.
- [ ] Command input, transcript, scene, journal, party, inventory, combat, and diagnostics panels use the shared app shell.
- [ ] Autoplay and reports use shared jobs, events, and assets.
- [ ] Save/load and replay remain backend-authoritative.

### Chat Acceptance

- [ ] Chat uses the shared provider selector and model registry.
- [ ] Streaming responses use the shared event client.
- [ ] Conversation history is backend-owned and rendered through shared transcript components.

### Voice, Podcast, STT, and Image Acceptance

- [ ] Long-running work uses shared jobs.
- [ ] Generated files are stored as shared assets.
- [ ] Progress, errors, logs, and diagnostics use shared components.
- [ ] Provider configuration is centralized.

## Migration Policy

1. Establish the shared web app infrastructure first.
2. Add feature modules inside the shared app shell.
3. Move existing UI behavior into modules incrementally.
4. Keep legacy UI only as a temporary compatibility layer.
5. Do not add new features to legacy UI once the shared app shell exists.
6. Remove legacy frontend entrypoints after parity is reached.

## Non-Goals

- Omnix is not a collection of unrelated AI demos.
- Individual features must not own independent app infrastructure.
- Frontend code must not duplicate backend simulation or provider truth.
- Local-only support must not prevent cloud-compatible providers from using the same abstractions.
- Cloud provider support must not break local-first workflows.
