# Phase 13.31 — runtime recursion targeted tests

## Context

The high human-playable blocking time is now isolated to the runtime turn path. Full 100-turn live/provider reruns are useful but too expensive for every hypothesis. We need provider-free targeted tests that exercise the suspected recursive diagnostic/result payload shapes directly.

## Change

This slice adds `runtime_recursion_perf_probe`, a small provider-free probe that builds a late-turn runtime-result-shaped payload with cyclic diagnostic references and measures the relevant operations independently:

- `copy.deepcopy`
- bounded JSON-safe structural clone
- JSON serialization of the bounded clone
- exception traceback formatting

It writes `autoplay-runtime-recursion-perf-probe.json` when given an output directory. CI coverage verifies the bounded clone handles cycles, the operation breakdown is written, and the probe runs under the installed turn-error/deepcopy diagnostics hooks.

## Verification target

Use the probe to distinguish whether the live runtime slowdown is dominated by copying recursive payloads, JSON/report-safe walking, or exception formatting. The next runtime fix should target the slow or failed operation identified by this probe and by live `autoplay-exception-tracebacks.json` evidence.

This slice adds targeted evidence tooling only; it does not claim the runtime RecursionError is fixed.
