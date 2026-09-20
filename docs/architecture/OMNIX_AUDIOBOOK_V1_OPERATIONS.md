# Omnix Audiobook V1 operations

The Audiobook workspace is available at `/audiobook` in the Omnix web gateway.
The gateway registers the Audiobook routes and starts separate ingest/analysis,
offline render, and preview worker loops. PostgreSQL jobs and render batches are
the durable queue; the browser is only a view of that state.

## Prerequisites

- Apply all repository PostgreSQL migrations, including the audiobook source
  format expansion in `src/app/persistence/migrations/0090_audiobook_source_format_expansion.sql`.
- Keep `OMNIX_BLOB_ROOT` on persistent storage. Back up that directory and
  PostgreSQL together. Source, voice, render, chapter, cover, and export asset
  records refer to immutable blobs there.
- Point `OMNIX_TTS_MODEL_DIR` (or `OMNIX_QWEN3_TTS_MODEL_DIR`) at a complete
  local Qwen3 TTS model directory. The workspace exposes the SHA-256 revision
  of the installed artifacts and uses it when queueing work. A missing or
  changed model is an error, not an implicit download or a cache hit.
- Install FFmpeg and place it on `PATH`, or set `OMNIX_FFMPEG` to its executable.
  Exports require FFmpeg; M4B also needs an FFmpeg build with AAC encoding.
- Keep voice clone profile files available for every cast speaker. Their
  hashes are pinned in casting revisions and checked when rendering.

## Production flow

1. Create a project and upload a PDF, DRM-free EPUB, DOCX, HTML, TXT, or Markdown source,
   either from the computer or from `resources\data\audiobooks`.
   Ingest and analysis are durable CPU jobs. The original blob, canonical
   chapters, and source spans are immutable.
2. Review open issues and choose a speaker by immutable ID. Add or confirm
   aliases explicitly. Assign an existing Omnix voice to each used speaker.
3. Inspect any span's source text and effective speech plan. Pronunciation
   entries and interpretation changes create new revisions. Preview uses the
   medium-priority GPU class and may be queued before the full cast is ready.
4. Start rendering from Production. One chapter is a leased job, and each
   completed span is checkpointed under an immutable render key. The shared
   provider prioritizes realtime, then preview, then offline generation
   between spans in the gateway process.
5. After chapter assembly and mastering, export M4B, FLAC, WAV, or MP3.
   The export job freezes its source, render, chapter, cover, and setting
   references. Download the file or open its integrity and provenance report.

## Failure and recovery

- A worker process can die after a checkpoint. Its lease expires and a worker
  reclaims the job; verified matching render blobs are reused. Do not remove
  the PostgreSQL job rows or blob directory to force a retry.
- A failed or canceled render can be retried from Production once all its
  chapter jobs have reached terminal states. Existing valid render keys are
  skipped. The job list shows generated and cache-hit counts.
- Use the job cancel control to request cooperative cancellation. An active
  span finishes before the worker acknowledges cancellation.
- If a voice file or model artifact changed, reassign the voice or start a new
  render with the installed model revision. The provider unloads a cached
  model when its local artifact signature changes before subsequent use.
- If export fails, confirm FFmpeg availability and inspect the durable export
  job error. Re-exporting does not require TTS synthesis when the render and
  chapter assembly keys still match.
- Deleting a project removes it from the active library and cancels its queued
  or running jobs. Immutable source, render, and export records remain in
  PostgreSQL and blob storage for audit and retention; deletion does not reclaim
  disk space. Project-specific API routes return 404 after deletion.
- The report endpoint at
  `/api/audiobook/projects/{project_id}/exports/{export_id}/report` checks
  source reconstruction, asset checksums, manifest references, and render
  provenance. Treat a failed check as a corrupted or incomplete export.

## Capacity and diagnostics

The RTX 4090 measurements and the one-span checkpoint decision are recorded
in [the GPU baseline](OMNIX_AUDIOBOOK_GPU_BASELINE_2026-09-19.md). The current
FasterQwen provider's `generate_audio_batch` is sequential. No speedup from
native multi-input batching was measured, so bulk rendering stays at one
span per provider call. Each immutable render records its input length,
generation wall time, audio duration, real-time factor, and available CUDA
memory counters. The export report aggregates duration and generation time.

The provider's process-local gate orders realtime, preview, and offline
requests. High-priority provider calls also hold a lock-backed signal under
`OMNIX_BLOB_ROOT/tts-priority`. The PostgreSQL worker checks these signals and
queued high-priority TTS jobs between spans. A crashed signal owner releases
its operating-system lock, and the next check removes the stale marker. All
local TTS processes need the same blob root for this cross-process yield. This
cooperative policy does not preempt an active GPU generation call; realtime
work may wait for the current offline span to finish.

## Validation

- Audiobook unit and property tests: `venv\Scripts\python.exe -m pytest
  src/tests/unit/audiobook -q --tb=short`
- Provider priority and residency tests: `venv\Scripts\python.exe -m pytest
  src/tests/unit/providers/test_tts_priority.py
  src/tests/unit/providers/test_tts_model_residency.py -q --tb=short`
- PostgreSQL golden-book, worker-death, export, and 300-span endurance tests:
  set `OMNIX_TEST_DATABASE_URL` to an isolated database, set
  `OMNIX_TEST_FFMPEG` to an FFmpeg executable, then run
  `python -m pytest src/tests/persistence/test_audiobook_ingest_integration.py
  -q --tb=short`.
- Web workspace: `npm --prefix src/apps/web run test --
  src/features/audiobook/AudiobookWorkspace.test.tsx` and
  `npm --prefix src/apps/web run build`.
