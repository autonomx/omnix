# RPG AI RPG Parity Phase 26 — Autoplay Verification Gate

Phase 26 adds deterministic verification metadata for 100-turn autoplay-style summaries.

## Landed

- Added `src/app/rpg/autoplay_verification_gate.py`.
- Checks completed-turn target, report-surface coverage, required runtime sections, and latency evidence.
- Adds an autoplay wrapper fragment to attach the verification gate to generated summaries.
- Adds a smoke test for missing coverage validation.

## Verification

Pending GitHub Actions for the Phase 26 PR.
