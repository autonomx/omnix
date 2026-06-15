# Omnix Web Gateway Startup

Last updated: 2026-06-15

This document explains the gateway used by the redesigned web app. The gateway
started as the Phase 4 additive foundation and is now the browser-facing API
surface for `apps/web`; service-specific FastAPI apps and backend compatibility
routers may still exist behind or alongside it.

## Purpose

The gateway gives later redesign phases a small browser-facing API surface that
can expose `/openapi.json` early, before backend consolidation work begins. It
can start without model workers, GPU providers, TTS, STT, image generation, or
the retired classic browser UI.

## Run Locally

From the repository root, use port `8000` when running the shared web app
because `apps/web/vite.config.ts` proxies `/api` and `/events` there:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

Useful URLs:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/api/runtime/status`
- `http://127.0.0.1:8000/api/workers/health`
- `http://127.0.0.1:8000/api/workers/payload-policy`
- `http://127.0.0.1:8000/api/compatibility/legacy`
- `http://127.0.0.1:8000/openapi.json`

Then start the shared browser app in another terminal:

```powershell
npm.cmd run web:dev
```

## Runtime Compatibility

`apps/web` is the supported browser UI. `src/run_app.py` may still be useful for
backend compatibility routes, generated-media serving, and older local scripts,
but it no longer serves the classic template/static browser shell. Legacy UI
retirement readiness is tracked in
`docs/WEB_APP_LEGACY_UI_RETIREMENT_READINESS.md`. The gateway publishes a
compatibility handoff endpoint that records which existing services still own
domain behavior that has not moved into typed gateway contracts.

Temporary ownership:

- `/api/rpg`: current `run_app:app` and `app.rpg.api` routers.
- `/api/image`: current `app.image.api` routes and optional image service.
- `/api/voice`, `/api/tts`, `/api/stt`: current main app plus TTS/STT services.
- `/generated-images`: current main app static generated-image route.

Later phases should migrate one typed contract at a time into the gateway,
using existing domain/service modules as delegates. Feature logic should not be
rewritten as part of the gateway cutover foundation.

## Worker Contract

Worker URLs are configured through environment variables. Browser code should
call the gateway only; it should not call model workers directly.

New worker discovery variables:

- `OMNIX_GATEWAY_WORKERS`: comma-separated worker IDs, for example
  `tts,stt,image`.
- `OMNIX_WORKER_<ID>_URL`: base URL for a configured worker.
- `OMNIX_WORKER_<ID>_CAPABILITIES`: optional comma-separated capability list.

Compatibility variables also feed worker discovery when present:

- `OMNIX_TTS_URL`
- `OMNIX_STT_URL`
- `OMNIX_IMAGE_URL`

Every worker health response uses this envelope:

```json
{
  "id": "tts",
  "ok": true,
  "status": "ready",
  "details": {},
  "error": null,
  "url": "http://127.0.0.1:5101",
  "capabilities": ["tts"],
  "source_env": "OMNIX_WORKER_TTS_URL",
  "mocked": false
}
```

Unreachable workers do not crash the gateway. They return `ok: false`,
`status: "unreachable"`, and a `worker_unreachable` diagnostic from
`/api/workers/health` and `/api/runtime/status`.

## Mock Worker Mode

CI and local contract tests can exercise worker-aware gateway paths without
GPU-backed workers:

```powershell
$env:OMNIX_GATEWAY_MOCK_WORKERS = "1"
$env:OMNIX_GATEWAY_MOCK_WORKERS_LIST = "tts,stt,image"
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

Mock workers return `status: "ready"`, `mocked: true`, and `mock://...` URLs.

## Payload Policy

`/api/workers/payload-policy` records the Phase 5 payload rules:

- small request and response bodies may be JSON;
- generated audio, image, transcript, checkpoint, and report outputs should be
  returned by asset reference;
- base64 media payloads are transitional only;
- worker URLs are gateway-facing only and forbidden for browser callers.

When no workers are configured, `/api/workers/health` returns:

```json
{
  "ok": true,
  "status": "not_configured",
  "format_version": "omnix_gateway_foundation_v1",
  "contract_version": "omnix_worker_health_contract_v1",
  "workers": [],
  "summary": {
    "configured": 0,
    "reachable": 0,
    "unreachable": 0,
    "mocked": 0
  },
  "diagnostics": []
}
```
