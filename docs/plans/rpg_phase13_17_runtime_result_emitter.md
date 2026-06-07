# RPG Phase 13.17 Runtime Turn Result Emitter Capture

Phase 13.17 addresses the rerun after Phase 13.16.

Latest source-of-truth SHA before this Phase 13.17 slice:

- `c60cc7984852252cf6dce47fd9ad25903078921e`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(9).zip`

The evidence showed:

- report-size hardening remains fixed;
- per-run performance output remains present;
- diagnostics now split runtime and generic events;
- runtime result events were still false positives from source labels;
- the actual runtime result payload was only visible through the console probe line `event=runtime_turn_execution.result`.

## Bounded target

Phase 13.17 selects this bounded target:

- capture the runtime-turn result emitter channel directly and persist runtime result emission evidence before it is lost to flattened console text.

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/runtime_turn_result_capture_hook.py`
- `src/tests/rpg/test_ci_phase13_17_runtime_result_emitter.py`
- `docs/plans/rpg_phase13_17_runtime_result_emitter.md`
- `docs/plans/rpg_phase13_17_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `src/tests/rpg/autoplay/result_path_diagnostics.py`
- `src/tests/rpg/autoplay/live_performance_bridge.py`
- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Runtime-result emission capture

The loader now installs a stdout/stderr write hook before generated runtime fragments load. Lines containing:

- `event=runtime_turn_execution.result`

are written to:

- `autoplay-runtime-turn-results.json`

Each captured event includes:

- original line;
- parsed tokens;
- parsed turn index when available;
- `ok` value when available;
- emitted result keys;
- detected trace keys.

## Diagnostics integration

`result_path_diagnostics.py` now consumes `autoplay-runtime-turn-results.json` and exposes those records as `runtime_result_events` in `autoplay-turn-error-diagnostics.json`.

The runtime-result classifier was also tightened:

- actual trace keys or `runtime_name` can mark a runtime event;
- source text containing `runtime` is no longer sufficient.

## Performance bridge

The live timing bridge now accepts runtime result emission keys as a bridge source when timing summaries are still unavailable. This preserves the fact that runtime trace fields were emitted, even if their values are not present in saved JSON yet.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- runtime result probe lines are parsed into structured events;
- stdout/stderr writes create `autoplay-runtime-turn-results.json`;
- source text alone no longer creates false-positive runtime events;
- runtime emission events populate `runtime_result_events`;
- the post-run hook reports observed runtime result rows;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Diagnostics and timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.17, continue with:

- Phase 13.18 — rerun 100-turn evidence review after runtime result emitter capture.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect:

- `autoplay-runtime-turn-results.json`
- `autoplay-turn-error-diagnostics.json`
- `autoplay-performance-summary.json`
