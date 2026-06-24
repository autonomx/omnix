# Phase 2 — Prompt and Model Profiles Progress

## Status

Implemented as a pure backend foundation on 2026-06-24.

## Added

- `RpgPromptProfile` contract for per-task provider/model settings.
- Default prompt profile registry covering intent classification, narration, NPC dialogue, combat narration, memory summaries, journal recaps, quality rewrites, grounding audits, and image prompts.
- Override support for model, provider, temperature, timeout, token budget, retry count, streaming, and blocking/background execution.
- Report/debug-friendly profile payloads with latency and status fields.
- Registry validation helper for missing or mismatched task profiles.
- Regression tests for default coverage, overrides, invalid override rejection, debug payloads, and missing-profile validation.

## Determinism Boundary

Prompt profiles configure LLM calls only. They do not resolve game outcomes, mutate simulation state, or bypass the Turn Contract. Background profile tasks are explicitly marked so failures can remain presentation/report concerns instead of blocking deterministic turn resolution.

## Verification

Pending GitHub Actions for this phase PR.
