# Omnix

Omnix is a modular local-first AI workstation by Autonomx. It brings chat, RPG simulation, storytelling, podcast generation, text-to-speech, speech-to-text, voice cloning, image generation, provider management, jobs, assets, settings, and diagnostics into one shared application platform.

<img src="resources/logo/omnix.png" alt="Omnix Logo" width="300">

## Platform Direction

Omnix is no longer treated as a collection of standalone AI demos. All browser-facing features are converging on one shared web app infrastructure under `apps/web`.

```text
Omnix Platform
├── Shared React/TypeScript/Vite Web App
├── FastAPI Backend
├── Shared Provider and Model Registry
├── Shared Job / Run System
├── Shared Asset / Artifact System
├── Shared Event Stream
└── Local or Cloud-Compatible Model Services
```

See [`SPEC.md`](SPEC.md) and [`docs/WEB_APP_INFRASTRUCTURE.md`](docs/WEB_APP_INFRASTRUCTURE.md) for the authoritative architecture rules.

## Feature Modules

- **RPG**: deterministic AI role-playing engine, turn contracts, simulation state, journal, party, combat, autoplay, and reports.
- **Chatbot**: provider-backed text chat with shared transcript and streaming infrastructure.
- **Storyteller**: long-form generation, outlines, branching story drafts, and exports.
- **Podcast Generator**: script planning, speaker assignment, TTS generation, mixing, and final audio export.
- **Voice / TTS**: text-to-speech generation, previews, playback, and diagnostics.
- **Voice Cloning**: source sample ingestion, voice profiles, preview generation, and profile metadata.
- **STT / Transcription**: audio ingestion, transcription jobs, transcript assets, and alignment.
- **Image Generation**: portraits, scenes, covers, generated image assets, and visual provider diagnostics.
- **Providers / Models**: LM Studio, llama.cpp, OpenRouter, Cerebras, OpenAI-compatible providers, TTS/STT/image services, model discovery, health, and capability reporting.
- **Jobs / Assets / Diagnostics**: shared run history, progress, logs, generated artifacts, settings, and troubleshooting.

## Web App Infrastructure

The shared browser app lives in `apps/web`.

```text
Frontend runtime: React + TypeScript + Vite
Server state:     TanStack Query
Local UI state:   Zustand
Forms:            React Hook Form
Validation:       Zod
Testing:          Vitest + Playwright
Realtime:         Shared SSE/WebSocket event client
```

All new browser-facing features must be implemented as modules inside this shared app shell. No feature should introduce a separate frontend framework, standalone vanilla JS app, Flask template UI, Streamlit UI, or one-off browser shell.

## Backend Infrastructure

The backend standard is Python with FastAPI, Pydantic, Uvicorn, and async-compatible service boundaries. Heavy model services may run as separate local processes, Conda environments, or containers because LLM, TTS, STT, image, GPU, and PyTorch dependencies often conflict.

Recommended local topology:

```text
omnix-web        Vite development server or built frontend
omnix-api        FastAPI backend
omnix-worker     Background jobs and long-running workflows
omnix-llm        Local LLM provider or proxy, such as LM Studio or llama.cpp
omnix-tts        TTS service
omnix-stt        STT service
omnix-image      Image generation service
```

## Prerequisites

- Python 3.8 or higher
- Node.js and npm for the shared web app
- LM Studio or another configured LLM provider for local text generation
- Optional local TTS, STT, and image services depending on enabled modules
- Optional NVIDIA GPU support for local accelerated model services

## Python Setup

```bash
pip install -r requirements.txt
```

Legacy setup scripts may still exist while the migration is in progress, but new browser-facing development should target the shared web app.

## Web App Setup

Install frontend dependencies:

```bash
npm install
```

Start the shared web app:

```bash
npm run web:dev
```

The Vite app runs on port `5173` and proxies `/api` and `/events` to the FastAPI backend on `http://localhost:8000`.

Useful web commands:

```bash
npm run web:typecheck
npm run web:test
npm run web:test:e2e
npm run web:build
npm run web:preview
```

## Development Rules

1. All new browser UI must live under `apps/web`.
2. Feature modules must use the shared API client.
3. Streaming/progress must use the shared event client.
4. Long-running work must use the shared job/run model.
5. Generated audio, images, transcripts, reports, checkpoints, and exports must use the shared asset/artifact model.
6. Provider and model selection must go through the shared provider/model registry.
7. Frontend code may render backend truth but must not invent authoritative state.
8. Legacy UI may remain temporarily during migration, but new behavior must not be added to legacy frontend entrypoints.

## Project Structure Target

```text
omnix/
├── apps/
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       ├── src/
│       │   ├── app/
│       │   ├── api/
│       │   ├── components/
│       │   ├── design-system/
│       │   ├── events/
│       │   ├── features/
│       │   └── state/
│       └── tests/
├── src/
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
