# Omnix Web App Redesign Completion Cleanup

This note records the final cleanup applied after reviewing the completed redesign phases on the `rpg` branch.

## Event stream alignment

The shared frontend event client defaults to `/events`. The gateway now exposes that route as the browser-facing live SSE stream.

- `/events` stays open, emits heartbeat comments, includes SSE `id:` fields for `Last-Event-ID` resume, and multiplexes named job events such as `job.created`, `job.updated`, `job.completed`, `job.failed`, and `job.canceled`.
- `/api/jobs/events` remains a finite history/compatibility endpoint for tests, diagnostics, and tools that want a bounded event batch.
- The Jobs and Diagnostics platform workspaces subscribe through the shared event client and invalidate TanStack Query data when job lifecycle events arrive.

## Scheduler status

The implemented scheduler is a resource-aware v1 scheduler, not a full VRAM/model-residency planner.

Implemented:

- jobs declare a resource class;
- local `gpu:*` jobs are exclusive by default;
- CPU jobs respect the configured CPU worker limit;
- network/cloud jobs are not blocked behind local GPU work;
- claim/lease scheduling prevents two local GPU jobs from running at the same time.

Not implemented yet:

- VRAM budget accounting;
- per-model residency tracking;
- model load/evict transitions as first-class scheduler states;
- safe GPU co-residency beyond the default one-GPU-job-at-a-time policy.

Future work should extend the scheduler from this safe default rather than weakening GPU exclusivity.

## Legacy status wording

The classic browser UI is retired. The old template/static shell is gone and `apps/web` is the supported browser app.

Some backend compatibility surfaces intentionally remain in `src/run_app.py` and existing service routers while feature-specific typed gateway contracts mature. The accurate status is:

```text
Classic browser UI: retired.
Legacy backend compatibility routes: intentionally retained.
```

## Data migration and compatibility status

Existing local user data must remain readable. Current coverage is mixed by data family:

- Image assets have an explicit shared-asset import path with dry-run diagnostics.
- RPG sessions/checkpoints/replay data remain readable through the replay and persistence adapter surfaces.
- Settings and generated reports remain readable through gateway platform payloads.
- Voice, STT, TTS, podcast, and other generated media should use read-through compatibility until explicit importers are added.

Do not delete or rewrite existing local data as part of frontend migration. Any future importer must support dry-run diagnostics and rollback guidance before becoming the source of truth.
