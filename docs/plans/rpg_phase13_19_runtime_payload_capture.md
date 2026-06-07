# RPG Phase 13.19 Runtime Result Payload Capture

Phase 13.19 addresses the rerun after Phase 13.18.

Latest source-of-truth SHA before this Phase 13.19 slice:

- `1b8aed45748fd2f84f90e626918d9c7e2526adf7`

## Accepted evidence

Accepted evidence source:

- `autoplay-100-n82-travel-location-progression(11).zip`

The evidence showed:

- report-size hardening remains fixed;
- per-run performance output remains present;
- `autoplay-runtime-turn-results.json` is present;
- runtime result emissions were captured from `console-log.txt`;
- the captured artifact still only contains flattened probe line fields and result keys;
- full runtime result payload values and traceback are still not persisted.

## Bounded target

Phase 13.19 selects this bounded target:

- capture bounded runtime result payload context before the generated runtime flattens the result into a probe line.

## Implementation

This slice adds:

- `src/tests/rpg/autoplay/runtime_probe_payload_capture.py`
- `src/tests/rpg/test_ci_phase13_19_runtime_payload_capture.py`
- `docs/plans/rpg_phase13_19_runtime_payload_capture.md`
- `docs/plans/rpg_phase13_19_completion_note.md`

This slice updates:

- `src/tests/rpg/autoplay_llm_campaign.py`
- `src/tests/rpg/autoplay/result_path_diagnostics.py`
- `src/tests/rpg/autoplay/survival_report_writer_hook.py`
- `docs/plans/rpg_production_readiness_plan.md`

## Payload capture strategy

The loader now applies two bounded capture layers:

1. Source instrumentation before the generated runtime is compiled. Lines containing the runtime result probe event are preceded by a guarded `locals()` capture.
2. Post-load wrapping of probe-like helper functions. If a wrapped function receives the runtime result event in args or kwargs, bounded call payloads are persisted.

Captured payload evidence is written to:

- `autoplay-runtime-turn-result-payloads.json`

Each captured event can include:

- turn index when available;
- selected local variables;
- runtime result dictionaries when present;
- manual harness/stage traces when present;
- provider trace when present;
- turn contract when present;
- turn performance trace/summary when present;
- bounded stack tail.

## Diagnostics and performance integration

`result_path_diagnostics.py` now consumes `autoplay-runtime-turn-result-payloads.json` and prioritizes payload-capture events above flattened emission events.

The post-run hook loads payload rows and includes them in performance summary generation so trace summaries can be bridged when payload values are available.

## Acceptance criteria

The implementation is accepted when deterministic tests prove:

- generated source containing the runtime result event is instrumented;
- local payload capture writes `autoplay-runtime-turn-result-payloads.json`;
- probe-like function wrapping records runtime result event calls;
- diagnostics prioritize payload-capture events;
- the post-run hook counts payload rows;
- runtime authority and gameplay semantics remain unchanged.

## Boundary confirmation

This slice does not add provider calls, LLM calls, network calls, live endurance execution in CI, gameplay mutation, UI authority changes, package building in CI, or production readiness claims.

Simulation/runtime remains authoritative. Diagnostics and timing labels are advisory artifact surfaces only and do not decide gameplay truth.

## Recommended next slice

After Phase 13.19, continue with:

- Phase 13.20 — rerun 100-turn evidence review after runtime payload capture.

The immediate operator follow-up is to pull latest `rpg`, rerun the same 100-turn command, and inspect:

- `autoplay-runtime-turn-result-payloads.json`
- `autoplay-runtime-turn-results.json`
- `autoplay-turn-error-diagnostics.json`
- `autoplay-performance-summary.json`
