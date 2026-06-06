# RPG Phase 13.11 Report Materialization Guard and Manual-Turn Metrics

Phase 13.11 addresses the remaining 100-turn artifact-size issue and adds the manual-turn blocking breakdown needed to understand the approximately 13 second human-playable blocking time.

Latest source-of-truth SHA before this Phase 13.11 slice:

- `0c42263ffd6d7998458bb93c41b66603b79eca54`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(3).zip`

The evidence showed:

- the 100-turn run completed functionally;
- `autoplay-campaign-report.json` was still far too large;
- `autoplay-report-size-guard-summary.json` was still missing;
- the remaining size guard needed to happen at report materialization, not only at finalization;
- human-playable blocking averaged about 13 seconds and needed a stage breakdown.

## Bounded targets

Phase 13.11 selects two bounded targets:

1. Force report-size capping when report artifacts are materialized through file writes, copies, or ZIP writes.
2. Add advisory manual-turn breakdown metrics to the performance summary surface.

## Implementation

This slice adds:

- `src/app/rpg/autoplay_report_materialization_guard.py`
- `src/tests/rpg/test_ci_phase13_11_report_materialization_guard.py`
- `src/tests/rpg/test_ci_phase13_11_manual_turn_metrics.py`
- `docs/plans/rpg_phase13_11_report_materialization_and_manual_metrics.md`
- `docs/plans/rpg_phase13_11_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `src/app/rpg/autoplay_performance_artifacts.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Report materialization guard

The loader now installs a report materialization guard before the generated autoplay runtime starts.

The guard caps oversized report artifacts at the moment they are materialized through:

- `Path.write_text`
- `Path.write_bytes`
- `shutil.copyfile`
- `shutil.copy2`
- `zipfile.ZipFile.write`
- `zipfile.ZipFile.writestr`

The guard still uses the Phase 13.8 limits and compact manifests, and emits `autoplay-report-size-guard-summary.json` as soon as a cap happens.

## Manual-turn breakdown metrics

`autoplay-performance-summary.json` now includes `manual_turn_breakdown` when rows include timing fields for:

- `manual_turn_ms`
- `pre_runtime_intent_llm_ms`
- `deterministic_runtime_apply_ms`
- `grounding_validation_ms`
- `repair_ms`
- `state_snapshot_ms`
- `deferred_enqueue_ms`

These metrics are advisory-only and are intended to identify which blocking stage is responsible for human-playable latency.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- oversized report bytes are capped before writing;
- oversized report files written with `Path.write_text` are capped;
- report copies are capped when the destination is a report artifact;
- oversized report ZIP members are capped while unrelated members are preserved;
- manual-turn sub-stage metrics are summarized;
- alias keys such as `first_call_llm_ms`, `runtime_apply_ms`, and `background_enqueue_ms` are mapped into the canonical breakdown.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Report-size and timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.11, continue with:

- Phase 13.12 — rerun 100-turn evidence review after materialization guard and manual-turn metrics.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and verify that `autoplay-report-size-guard-summary.json` is present, report artifacts are capped, and `autoplay-performance-summary.json` includes `manual_turn_breakdown`.
