# RPG AI RPG Parity Phase 24 — Benchmark Replay Gate

Phase 24 adds deterministic benchmark proof and replay-gate metadata for 100-turn style runs.

## Landed

- Added `src/app/rpg/benchmark_replay_runtime.py`.
- Reports requested/completed turns, transcript row counts, turn-target status, and latency evidence.
- Compares expected/actual replay snapshot hashes with the Phase 13 replay contracts.
- Surfaces replay validation issues and snapshot hash mismatches.
- Adds tests that run under the existing deterministic PR gates, providing a lightweight replay CI gate.

## Verification

Pending GitHub Actions for the Phase 24 PR.
