# Phase 13.45 — diagnostic artifact contract

## Context

The autoplay diagnostics have repeatedly failed by silently omitting expected JSON artifacts. This makes each run ambiguous: a missing file can mean the writer did not run, did not have an output directory, failed internally, or the mirror did not include it.

## Change

This slice makes `probe_source_map.py` the final diagnostic artifact guard at process exit. After attempting to write the generated source map, it creates placeholders for any expected diagnostic JSON files that are still absent and writes `autoplay-diagnostic-artifact-manifest.json`.

Expected diagnostics now covered by the contract:

- `autoplay-runtime-probe-source-map.json`
- `autoplay-runtime-turn-results.json`
- `autoplay-stream-turn-error-events.json`
- `autoplay-exception-tracebacks.json`
- `autoplay-runtime-turn-result-payloads.json`

The contract preserves real files and only creates placeholders for absent files. Each placeholder explains that the writer did not produce the artifact.

## Verification target

Future operator ZIPs should always include the manifest and every expected diagnostic JSON name. Missing diagnostics should show up as placeholder JSON with a reason instead of disappearing silently.

This is diagnostics infrastructure only; it does not claim the runtime recursion issue is fixed.
