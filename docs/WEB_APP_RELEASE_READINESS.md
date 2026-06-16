# Omnix Web App Release Readiness

Last updated: 2026-06-15

This runbook covers the redesigned web app after classic UI retirement. The
supported browser UI is `apps/web`; backend compatibility routes remain only for
domain/data continuity.

## Local Process Mode

Start the gateway:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

Start the web app in a second terminal:

```powershell
npm.cmd run web:dev
```

The Vite app runs on `http://127.0.0.1:5173` and proxies `/api` and `/events`
to `http://127.0.0.1:8000`.

## Mock Worker Testing

Use mock workers for CI and local contract checks that must not require GPU,
TTS, STT, image, or LLM services:

```powershell
$env:PYTHONPATH = "src"
$env:OMNIX_GATEWAY_MOCK_WORKERS = "1"
$env:OMNIX_GATEWAY_MOCK_WORKERS_LIST = "tts,stt,image"
python -m uvicorn app.gateway.main:app --host 127.0.0.1 --port 8000
```

Expected health signals:

- `/api/runtime/status` reports worker `status: ready`.
- `/api/workers/health` reports `mocked: 3`.
- Browser modules can render diagnostics without contacting real model workers.

## Worker Setup

Real workers are configured through environment variables:

```powershell
$env:OMNIX_GATEWAY_WORKERS = "tts,stt,image"
$env:OMNIX_WORKER_TTS_URL = "http://127.0.0.1:5101"
$env:OMNIX_WORKER_STT_URL = "http://127.0.0.1:5201"
$env:OMNIX_WORKER_IMAGE_URL = "http://127.0.0.1:5301"
```

Each worker should expose `/health`. Unreachable workers must not crash the
gateway; they appear as degraded diagnostics in `/api/runtime/status` and
`/api/workers/health`.

## Optional Compose Mode

There is no required compose topology for local CI. If a compose file is added,
it should preserve the same process boundaries:

- `omnix-web` for `apps/web`;
- `omnix-api` for `app.gateway.main:app`;
- separate worker services for model-heavy work;
- mounted `resources/data` for user data and generated artifacts.

## GPU Scheduling Expectations

GPU-bound jobs must go through `/api/jobs`; browser modules must not call model
workers directly. The shared scheduler permits only one active GPU job by
default while allowing network jobs to bypass the GPU lock. Long GPU/manual
validation should be recorded separately from CI because CI uses mock workers.

## Optional Live Worker Endurance

Use the opt-in endurance collector only after real worker URLs are configured.
The script refuses to run without `--allow-live` so it cannot be mistaken for a
provider-free CI gate.

```powershell
$env:PYTHONPATH = "src"
$env:OMNIX_GATEWAY_WORKERS = "tts,stt,image"
$env:OMNIX_WORKER_TTS_URL = "http://127.0.0.1:5101"
$env:OMNIX_WORKER_STT_URL = "http://127.0.0.1:5201"
$env:OMNIX_WORKER_IMAGE_URL = "http://127.0.0.1:5301"
python scripts/live_worker_endurance.py --allow-live --iterations 60 --interval-seconds 10 --min-reachable 3
```

The collector writes JSON evidence under
`resources/data/test-results/web-platform-live-worker-endurance/` with worker
health samples, diagnostics, timestamps, and the minimum reachable worker count.
Attach that artifact when claiming live-worker endurance readiness.

## Data Migration And Rollback

Migration checks should be dry-run first and copy-first when storage changes are
needed.

- Image asset migration: run `/api/assets/migrations/image/dry-run` before
  `/api/assets/migrations/image/import`.
- Missing files must be reported in `missing_files`; do not silently drop
  legacy asset references.
- Generated images remain served from `/generated-images/*` as runtime/user
  data, even though the classic UI is deleted.
- RPG sessions, checkpoints, reports, settings, voice assets, and generated
  media must remain readable through their existing compatibility adapters until
  a copy-first migration with rollback is implemented.

Rollback for a failed migration is to keep the original source files/manifests
unchanged, discard the new shared manifest or database created during the failed
run, and rerun the dry-run diagnostics before attempting import again.

## Backup And Restore

Back up user/runtime data before migration or long endurance runs:

- `resources/data`
- `resources/voice_clones`
- `resources/models` metadata or local model manifests, when present
- shared asset manifest paths such as `resources/data/assets/manifest.json`
- legacy image/audio/document manifests still used by read-through adapters
- settings and secrets files, especially `resources/data/settings.json` and
  `resources/data/secrets.json`

Restore is copy-first:

1. Stop gateway, web, and worker processes.
2. Move the current target directory aside instead of deleting it.
3. Copy the backed-up directory or file back into place.
4. Run `python scripts/smoke_web_platform.py --skip-web`.
5. Run asset dry-runs before any import operation.

Never treat shared-asset imports as a delete/move operation. Legacy files remain
the rollback source until an explicit copy-first migration proves otherwise.

## Troubleshooting

Useful local checks:

- Gateway schema drift: `npm.cmd --workspace @omnix/web run api:check`
- Gateway contracts: `python -m pytest src/tests/api/gateway -q`
- Legacy compatibility guard:
  `python -m pytest src/tests/api/test_legacy_ui_retirement.py -q`
- Web contracts: `npm.cmd --workspace @omnix/web run typecheck` and
  `npm.cmd --workspace @omnix/web run test`

Diagnostics to inspect:

- `/api/diagnostics` for worker health, event-stream status, model residency,
  and provider/model cache status.
- `/api/workers/health` for mock, reachable, and unreachable worker summaries.
- `/api/jobs/events` for bounded job event history and resume cursor checks.
- gateway logs and worker logs for provider timeouts or model download errors.
- provider/model cache diagnostics for missing local model directories or stale
  configured paths.

## Release Validation

Run the CI-safe checks before calling a build ready:

```powershell
python scripts/smoke_web_platform.py --web-build
python -m pytest src/tests/api/gateway src/tests/api/test_legacy_ui_retirement.py -q
npm.cmd --workspace @omnix/web run typecheck
npm.cmd --workspace @omnix/web run test
npm.cmd --workspace @omnix/web run test:e2e
npm.cmd --workspace @omnix/web run api:check
```

Use `python scripts/smoke_web_platform.py --skip-web` for a fast backend-only
smoke that checks gateway health, mock-worker health, event-stream route
registration, diagnostics, and checked-in OpenAPI drift without invoking npm.

Manual GPU/provider checks are separate from the CI-safe gate and should record
the worker URLs, model/provider versions, and job IDs used for reproduction.
