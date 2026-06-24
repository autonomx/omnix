# RPG AI RPG Parity Phase 18 — Narration Prompt Runtime

Phase 18 wires narration quality and prompt-profile metadata into runtime-facing report artifacts without mutating simulation state.

## Landed

- Added `src/app/rpg/narration_prompt_runtime.py`.
- Added deterministic runtime metadata for narration quality, rewrite recommendation, and selected prompt profiles.
- Added an autoplay summary wrapper fragment that persists Phase 18 metadata into summary and transcript JSON artifacts.
- Added a smoke test for the runtime adapter.

## Guardrails

- The adapter is presentation-only.
- Rewrite contracts remain advisory and cannot mutate state.
- Prompt-profile metadata is deterministic and report-facing.

## Verification

Pending GitHub Actions for the Phase 18 PR.
