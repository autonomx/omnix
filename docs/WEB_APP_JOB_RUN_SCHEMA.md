# Omnix Job and Run Schema

Last updated: 2026-06-14

Scope: Phase 7 of `docs/WEB_APP_REDESIGN_ROADMAP.md`.

This document defines the shared job/run contract before queue consolidation
begins. It is design-only: it does not replace the existing TTS, image, RPG
visual, or RPG narration queues.

## Design Anchors

- Use the image queue's claim/lease ownership pattern as the concurrency
  reference, but replace its in-memory storage in Phase 8.
- Preserve TTS chunk ordering and reassembly as stage checkpoint behavior.
- Treat RPG narration jobs as projections of `runtime_state` until replay gates
  prove that migration is deterministic.
- Preserve RPG visual side effects: visual jobs may update durable RPG sessions
  as part of successful completion.
- Keep cloud/network work independent from local GPU scheduling.

## Job Schema

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | yes | Stable job id. Prefer `job:<uuid>` for generated jobs. |
| `owner_id` | string or null | yes | Reserved owner seam. `null` means local single-user default. |
| `module` | string | yes | Canonical module id such as `voice`, `image`, `rpg`, or `podcast`. |
| `type` | string | yes | Module-owned job type, for example `tts.synthesize`, `image.generate`, or `rpg.autoplay`. |
| `status` | string | yes | One of the shared job statuses below. |
| `resource_class` | string | yes | One resource class from the shared list below. |
| `priority` | integer | yes | Higher number runs first within the same runnable resource lane. Default `0`. |
| `stages` | array | yes | Ordered stage records. Empty only for very short transitional jobs. |
| `progress` | object | yes | Aggregate progress derived from stages. |
| `logs` | array | yes | Structured log references or inline lightweight log entries. |
| `input_ref` | object or null | yes | Asset, file, or payload reference for large inputs. |
| `input_payload` | object or null | yes | Small JSON input. Large binary data must not live here. |
| `output_refs` | array | yes | Shared asset references produced by completed stages. |
| `error` | object or null | yes | Normalized error code, message, retryability, and details. |
| `lease` | object or null | yes | Claim token, worker id, and expiry for active work. |
| `created_at` | string | yes | ISO-8601 timestamp. |
| `updated_at` | string | yes | ISO-8601 timestamp. |
| `started_at` | string or null | yes | First execution timestamp. |
| `completed_at` | string or null | yes | Terminal timestamp for completed, failed, canceled, or stale jobs. |
| `cancel` | object | yes | Cancellation request and acknowledgement state. |
| `compat` | object | yes | Transitional source ids and legacy payload hints. Empty object when unused. |

## Status Values

```text
queued
leased
running
waiting
retrying
completed
failed
cancel_requested
canceled
stale
```

`leased` means a worker owns the job but has not necessarily started the heavy
operation. `running` means at least one stage is actively executing. `waiting`
means the job is blocked by a resource, dependency, or external worker. `stale`
is reserved for compatibility cases such as RPG visual or narration requests
that are no longer relevant to the current authoritative session state.

## Resource Classes

```text
cpu
gpu:llm
gpu:tts
gpu:stt
gpu:image
network
```

Every job must declare exactly one primary `resource_class`. A future phase may
add secondary resource hints, but Phase 8 scheduling must make decisions from
this single primary value.

Default mappings:

| Workflow | Resource class |
| --- | --- |
| Local LLM chat, story, RPG narration, RPG autoplay | `gpu:llm` |
| Local TTS synthesis or voice preview | `gpu:tts` |
| Local STT transcription or alignment | `gpu:stt` |
| Local image generation or RPG visual generation | `gpu:image` |
| Report formatting, manifest cleanup, small metadata jobs | `cpu` |
| Cloud provider calls, downloads, remote hosted inference | `network` |

## Scheduler Rules

The first scheduler is intentionally conservative:

- One local GPU job may run at a time across all `gpu:*` resource classes.
- `network` jobs bypass the local GPU lock.
- `cpu` jobs run concurrently up to a configured local limit.
- Within each runnable lane, higher `priority` runs first, then older
  `created_at`.
- Claim/lease ownership is required before a worker executes a job.
- Expired leases return a non-terminal job to the runnable queue unless the
  stage says it is unsafe to retry automatically.
- Model load and model eviction must be visible stages for local GPU jobs.
- Future VRAM-aware co-residency is a later scheduler upgrade, not an implied
  feature of this schema.

The safe default intentionally serializes `gpu:llm`, `gpu:tts`, `gpu:stt`, and
`gpu:image` together. This avoids accidental local VRAM contention until model
residency and co-residency can be measured and tested.

## Stage Schema

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | yes | Stable within the job, for example `chunk:0003` or `generate-image`. |
| `label` | string | yes | Human-readable label for the Jobs UI. |
| `status` | string | yes | Same status vocabulary as jobs, scoped to the stage. |
| `resource_class` | string | yes | Usually matches the job; may be `cpu` for preparation/finalization stages. |
| `progress` | object | yes | `current`, `total`, and optional `message`. |
| `checkpoint_ref` | object or null | yes | Asset/file/state reference for resumable output. |
| `output_refs` | array | yes | Assets emitted by this stage. |
| `error` | object or null | yes | Stage-local error details. |
| `started_at` | string or null | yes | Stage start timestamp. |
| `completed_at` | string or null | yes | Stage terminal timestamp. |
| `retry` | object | yes | Attempts, max attempts, and retry policy. |

Stage semantics:

- Stages have independent status and progress.
- Completed stages may publish checkpoint references.
- Retries resume from safe checkpoints when the adapter can prove the checkpoint
  is valid.
- TTS chunk jobs use one stage per chunk plus a final reassembly stage.
- Podcast jobs use stages for planning, script, speaker assignment, TTS stems,
  mixing, metadata, and export.
- RPG autoplay/report jobs use stages for run setup, turns/batches, checkpoint
  materialization, report generation, and archive/export.

## Cancellation

Cancellation is cooperative:

```json
{
  "requested": false,
  "requested_at": null,
  "acknowledged_at": null,
  "reason": null
}
```

Pending jobs can be canceled before lease. Leased or running jobs move through
`cancel_requested`; the worker acknowledges when it reaches a safe interruption
point. Cancellation during model inference is best-effort because local model
libraries and remote provider calls may not expose immediate interruption.

Canceled jobs keep completed stage outputs and logs. Adapters must mark whether
partial outputs are safe to expose as assets.

## Event Contract

Job lifecycle events should use named SSE events through the shared event
client:

```text
job.created
job.updated
job.stage.updated
job.log.appended
job.completed
job.failed
job.canceled
```

Events carry ids and lightweight state. Large logs, reports, images, audio,
transcripts, checkpoints, and archives must be returned as asset references.

## Compatibility Mapping

| Existing system | Shared job mapping |
| --- | --- |
| `src/app/image/job_queue.py` | Durable job records with claim/lease fields, `gpu:image` resource class, image output asset references. |
| `src/app/rpg/visual/job_queue.py` | Compatibility adapter preserving `session_id`, `request_id`, stale-request behavior, and session update side effects. |
| `src/app/job_queue.py` | `gpu:tts` jobs with chunk stages, ordered stage outputs, and final reassembly checkpoint. |
| `src/app/rpg/session/narration_worker.py` | Read-only shared job projection first; `runtime_state` remains authoritative until replay gates pass. |
| RPG autoplay/manual harnesses | Report/run jobs once browser-facing run APIs exist; current operator artifacts remain readable. |

## Phase 8 Implementation Boundaries

Phase 8 should implement the minimum durable local job adapter that satisfies
this contract:

- SQLite-backed storage for job, stage, lease, log, and output-reference state.
- In-process asyncio executor for local-first single-user mode.
- One local GPU lock across all `gpu:*` jobs.
- Bounded CPU executor.
- Network lane that does not wait for the GPU lock.
- Adapters for existing image and TTS queues before replacing their public
  surfaces.
- Job event emission through the shared SSE client path.

Phase 8 should not migrate RPG narration out of `runtime_state` or promise
VRAM-aware co-residency.
