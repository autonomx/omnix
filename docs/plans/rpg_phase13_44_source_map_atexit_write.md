# Phase 13.44 — source map atexit write

## Context

ZIP 33 confirmed the Phase 13.42 runtime-result primitive fields were present, but the expected source-map artifact was absent. The loader configures the source-map helper before loading the generated combined source, but no explicit writer runs after the combined source has been placed in `linecache`.

## Change

This slice moves the write trigger into `tests.rpg.autoplay.probe_source_map` itself:

- bumps source to `autoplay_probe_source_map_v4`
- registers a single `atexit` writer during source-map configuration
- keeps the existing v3 marker set for the runtime checkpoint/apply boundary

The loader already calls `configure_probe_source_map_from_argv`, so no loader change is needed.

## Verification target

The next operator run should include `autoplay-runtime-probe-source-map.json` with source `autoplay_probe_source_map_v4`, including matches for the runtime checkpoint/apply markers.
