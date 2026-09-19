# Omnix Audiobook V1 implementation review

This is the final audit against `OMNIX_AUDIOBOOK_ROADMAP.md` and its V1 definition
of done. The implementation branch is `agent/audiobook-v1`. The feature uses
Omnix PostgreSQL jobs and local immutable blobs; Alexandria is a design reference,
not a runtime dependency. No Alexandria source code was copied.

## V1 definition of done

| Roadmap items | Status | Evidence |
| --- | --- | --- |
| 1–3. EPUB import, exact chapter reconstruction, LLM source safety | Implemented; tested | `extraction.py`, `spans.py`, `integrity.py`, `annotation.py`; source integrity unit tests and golden EPUB integration |
| 4–5. Stable speaker IDs and evidenced review | Implemented; tested | `annotation.py`, `review_repository.py`, `service.py`; annotation and PostgreSQL integration tests |
| 6–7. Existing voice casting and auditable pronunciation | Implemented; tested | `service.py`, `speech_plan.py`, Audiobook workspace; render identity and UI tests |
| 8–9. Leased offline GPU jobs and realtime/preview yield | Implemented; tested | `render_service.py`, `tts_priority.py`, gateway worker registration; priority and provider tests |
| 10–11. Process death resume and cache reuse | Implemented; tested | Render checkpoint and immutable key lookup; golden test kills subprocesses before and after the first checkpoint |
| 12–13. Selective invalidation and immutable audio | Implemented; tested | `render_keys.py`, `render_cache.py`, `render_service.py`; render identity, corruption, and integration tests |
| 14. Pause policy and chapter mastering | Implemented; tested | `assembly.py`, `assembly_service.py`; assembly unit and export integration tests |
| 15–16. Frozen M4B/FLAC/WAV/MP3 exports and M4B metadata | Implemented; tested | `export.py`, `export_service.py`; FFmpeg probe and all four format integration tests |
| 17. Browser reload and reconnect state | Implemented; tested | TanStack Query reads persisted project/job state; workspace remount test |
| 18. Integrity and provenance report | Implemented; tested | `report.py`, report route; golden export integration test |
| 19–20. Required tests and golden restart render | Implemented; tested | Unit/property, PostgreSQL integration, 300-span endurance, provider, and web suites; golden EPUB render uses deterministic test TTS audio to make recovery assertions |

## UI acceptance review

| Roadmap criteria | Status | Evidence |
| --- | --- | --- |
| 1–4. Module, shell, rails, and two modes | Implemented; tested | `modules.ts`, `ModuleWorkspace.tsx`, `AudiobookWorkspace.tsx`, CSS, web tests; desktop and mobile browser inspection |
| 5–6. Read-only source and actionable review | Implemented; tested | Span overlays, selected-span controls, persisted issue queue; UI and integration tests |
| 7. Casting and audition | Implemented; tested | Voice profile list, assignment, revision hash, cross-chapter span location, preview jobs; UI test |
| 8–10. Durable progress, distinguishable job outcomes, frozen exports | Implemented; tested | Project/job API, render counts, retry/cancel, export manifest; UI and integration tests |
| 11–12. Lifecycle and responsive states | Implemented; tested | Empty/loading, ingest/analyze progress, review, ready, rendering, failure, export states; stage-first mobile layout with library/outline panels, browser inspection and web tests |
| 13–15. Theme, keyboard names, backend authority | Implemented; tested | Shared shell theme tokens, focus styles, accessible controls, TanStack Query, reload test; no audiobook localStorage authority |

The desktop visual review covered the empty workspace; populated layout is covered
by component tests and CSS review. The mobile browser review found and fixed a
shared header overlap at 390 px. A manual production browser walkthrough with a
long imported book remains useful before rollout. The final mobile panel
behavior was checked at 390 px by opening and closing the library over the
stage-first workspace.

## Mandatory test matrix

- **Source and typography:** reconstruction, gaps, overlap, duplicate/order
  rejection, stable hashes, quote conventions and malformed punctuation are in
  `src/tests/unit/audiobook/test_source_integrity.py`.
- **Identity and classifier failures:** same-name ambiguity, alias confirmation,
  malformed/refused/timeout results, targeted retry, and narrator fallback are in
  `test_annotation.py` and the PostgreSQL integration suite.
- **Render and recovery:** deterministic keys, selective invalidation, corrupt
  blob rejection, model and voice revision binding, two real process deaths,
  lease reclamation, cancellation, retries, and 300 spans are covered by the
  render unit and persistence suites. Cross-process priority signal cleanup and
  model residency changes have provider tests.
- **Audio and export:** assembly pauses, chapter gain, timeline and M4B commands
  have unit tests; the PostgreSQL suite probes finished M4B, FLAC, WAV, and MP3
  files with FFmpeg and verifies manifest/report references.

The real RTX 4090 provider benchmark is in
`OMNIX_AUDIOBOOK_GPU_BASELINE_2026-09-19.md`. It found sequential batch behavior,
so production checkpoints one span at a time. The golden recovery test replaces
TTS with deterministic audio; it validates durable orchestration and encoding,
while the provider smoke suite separately loads the installed model on CPU.

## Post-review corrections closed

A second completeness/correctness pass found and closed the following V1 release
blockers and usability gaps:

- **Canonical source resubmission is idempotent.** Re-uploading identical source
  bytes reuses the deterministic source revision instead of colliding on the new
  immutable source-asset ID. If the prior analysis attempt is terminal, the
  resubmission creates a new analysis job while preserving the canonical revision.
- **Terminal pipeline stages are recoverable without mutating history.** Failed,
  canceled, or stale ingest/analyze/assembly work is retried as a new durable job;
  the old attempt is marked with `superseded_by`. Analysis and assembly retries
  fail closed when their source revision/render run is stale. An old ingest cannot
  be retried after a canonical source already exists, preventing accidental source
  rewind.
- **Mastering completion is retry-safe.** Project readiness is based on a completed
  assembly for every rendered chapter in the active render run, not on every
  historical assembly job being completed.
- **Render cache identity includes effective provider defaults.** FasterQwen3
  resolves sparse overrides into the complete generation-affecting parameter map,
  including a generation-strategy revision, before Audiobook computes cache keys.
  Render provenance separately records the parameters actually used after provider
  fallback/retry behavior.
- **Confirmed speaker aliases reconcile interpretation state.** Alias confirmation
  appends new annotation revisions only for matching unresolved classifier
  candidates in the current source, resolves their review issues, preserves
  explicit user decisions, and invalidates stale active render/master work.
- **Project operations are complete in the workspace.** Title/author edits now have
  a Save Project path; project detail exposes word count plus estimated/actual
  runtime; pipeline failures expose stage, chapter, attempt counts, retryability,
  diagnostics, and an explicit retry action.
- **Generated API contracts are synchronized.** The project PATCH and pipeline-job
  retry routes are present in both the checked-in OpenAPI schema and generated
  TypeScript contract.

Regression coverage for these corrections lives in
`test_audiobook_ingest_integration.py`,
`test_render_identity_and_speech.py`,
`test_qwen3_tts_smoke.py`, and
`AudiobookWorkspace.test.tsx`.

## Intentional scope decisions

- **Deferred after V1:** automatic VoiceDesign/persona assistance and migration of
  other Omnix long-form workflows to this worker are explicitly in roadmap
  sections 25 and 27. No V1 authority depends on them.
- **Not applicable:** DRM removal, Alexandria's server and JSON persistence, and
  one job per span are expressly excluded by the roadmap.
- **Operational limit:** cooperative priority yields between spans; it cannot
  interrupt an active CUDA generation call. Separate local TTS processes must
  share `OMNIX_BLOB_ROOT` for the marker signal.

## Review searches

Reviewed Audiobook and adjacent provider, job, asset, and web code for source
rewrites, `localStorage` authority, synchronous `voice_inline.py` use, per-span
jobs, mutable audio IDs, fuzzy automatic speaker merges, and Alexandria runtime
dependencies. None is present in the Audiobook implementation. The final code
review also checked persisted state transitions, lease renewal, cache blob
validation, model/voice revision checks, report reconstruction, and API ownership.

## Final validation record

The earlier implementation baseline was green for the focused Audiobook/provider
matrix, PostgreSQL integration suite, full web suite, TypeScript build, generated
API contract check, Ruff, and diff checks before the post-review corrections above.

Those counts are intentionally not repeated as final-head evidence because the
correction pass added backend, provider, persistence, route, generated-contract,
and web-test changes. The authoritative final validation is the GitHub Actions run
for the exact pull-request head after this review update. Any failure from that run
must be reconciled before this document is treated as merge-ready evidence.
