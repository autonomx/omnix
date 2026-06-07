# RPG Phase 13.20 Live Timing and Probe Source Map

Phase 13.20 combines two evidence targets requested after the Phase 13.19 follow-up.

Latest source-of-truth SHA before this slice:

- `7e145174c1f5db8b19e6957abd7b8cccac7786e3`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(12).zip`

The evidence showed:

- the Phase 13.19 wrapper regression is fixed;
- the run completes 100/100 turns again;
- console-log backfill still captures flattened runtime-result events;
- full payload capture remains empty;
- the performance summary still only has coarse manual timing plus state snapshot and deferred enqueue timing;
- the requested live substages are still missing.

## Bounded targets

Phase 13.20 selects two bounded targets:

1. Add live manual-turn substage timing for:
   - `pre_runtime_intent_llm_ms`
   - `deterministic_runtime_apply_ms`
   - `grounding_validation_ms`
   - `repair_ms`
2. Add a non-invasive generated probe source map:
   - `autoplay-runtime-probe-source-map.json`

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/live_manual_turn_timing.py`
- `src/tests/rpg/autoplay/probe_source_map.py`
- `src/tests/rpg/test_ci_phase13_20_live_timing_probe_map.py`
- `docs/plans/rpg_phase13_20_live_timing_probe_source_map.md`
- `docs/plans/rpg_phase13_20_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `src/tests/rpg/autoplay/live_performance_bridge.py`
- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Live substage timing

The loader configures and installs a bounded helper-function timing wrapper after generated runtime load. It avoids runner, main, facade, manifest, assertion, report, artifact, and zip functions.

The timing artifact is:

- `autoplay-live-manual-turn-substage-timing.json`

It records function name, stage name, elapsed milliseconds, optional turn index, and a stage summary.

The performance bridge now forwards the four missing fields into `autoplay-performance-summary.json` when the live timing artifact contains them.

## Probe source map

The source map reads the generated combined source from `linecache`; it does not mutate generated source.

The source map artifact is:

- `autoplay-runtime-probe-source-map.json`

For each occurrence of the runtime result probe text, it records:

- line number;
- enclosing function name;
- nearby source context;
- simple helper-call names on the line;
- referenced local names on the line.

This is meant to identify the exact generated probe site without broad wrapping.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Timing and source-map artifacts are advisory diagnostics only.

## Recommended next slice

After Phase 13.20, continue with:

- Phase 13.21 — rerun 100-turn evidence review after live timing and source map.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect:

- `autoplay-live-manual-turn-substage-timing.json`
- `autoplay-runtime-probe-source-map.json`
- `autoplay-performance-summary.json`
- `autoplay-turn-error-diagnostics.json`
