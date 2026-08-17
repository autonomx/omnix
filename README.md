# Omnix

Omnix is a modular local-first AI workstation by Autonomx. It brings chat, RPG simulation, storytelling, podcast generation, text-to-speech, speech-to-text, voice cloning, image generation, provider management, jobs, assets, settings, and diagnostics into one shared application platform.

<img src="resources/logo/omnix.png" alt="Omnix Logo" width="300">

## Platform Direction

Omnix is no longer treated as a collection of standalone AI demos. All browser-facing features are converging on one shared web app infrastructure under `src/apps/web`.

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

The shared browser app lives in `src/apps/web`.

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

## Optional Hermes Agent sidecar setup

Hermes Agent is optional and runs as a sidecar. Omnix does not install it as an in-process Python dependency.

Windows PowerShell:

```powershell
.\scripts\setup_hermes.ps1
```

Linux, macOS, or WSL2:

```bash
bash scripts/setup_hermes.sh
```

The setup helper installs or refreshes Hermes Agent and writes local Omnix env defaults to `.env.local`. Leave `HERMES_ENABLED=false` until the Hermes sidecar is running and reachable. See [`docs/HERMES_SIDECAR_SETUP.md`](docs/HERMES_SIDECAR_SETUP.md).

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

Start the gateway used by the shared web app:

```bash
PYTHONPATH=src python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

The classic `src/templates` and `src/static` browser UI is retired in favor of `src/apps/web`. `src/run_app.py` may still host backend compatibility routes and generated media, but it is no longer the supported browser app. See [`docs/WEB_APP_LEGACY_UI_RETIREMENT_READINESS.md`](docs/WEB_APP_LEGACY_UI_RETIREMENT_READINESS.md).

Release and validation guidance lives in [`docs/WEB_APP_RELEASE_READINESS.md`](docs/WEB_APP_RELEASE_READINESS.md).

Useful web commands:

```bash
npm run web:typecheck
npm run web:test
npm run web:test:e2e
npm run web:build
npm run web:preview
```

## Development Rules

1. All new browser UI must live under `src/apps/web`.
2. Feature modules must use the shared API client.
3. Streaming/progress must use the shared event client.
4. Long-running work must use the shared job/run model.
5. Generated audio, images, transcripts, reports, checkpoints, and exports must use the shared asset/artifact model.
6. Provider and model selection must go through the shared provider/model registry.
7. Frontend code may render backend truth but must not invent authoritative state.
8. Classic UI entrypoints are retired; new behavior must not be added to legacy frontend files or routes.

## Project Structure Target

```text
omnix/
├── src/
│   ├── app/
│   ├── apps/
│   │   └── web/
│   │       ├── package.json
│   │       ├── vite.config.ts
│   │       ├── src/
│   │       │   ├── app/
│   │       │   ├── api/
│   │       │   ├── components/
│   │       │   ├── design-system/
│   │       │   ├── events/
│   │       │   ├── features/
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
