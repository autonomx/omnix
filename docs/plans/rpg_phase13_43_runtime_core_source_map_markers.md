# Phase 13.43 — runtime core source map markers

## Context

ZIP 31 narrowed the normalized failure path to the span after `runtime_checkpoint_before_companion_systems` and before or at `runtime_core_before_apply_turn_authoritative`. The existing source map did not include those marker strings, so it could not show the generated source context around the failing runtime core boundary.

## Change

This slice bumps the probe source map to `autoplay_probe_source_map_v3` and adds runtime-core marker strings:

- `runtime_checkpoint_before_companion_systems`
- `runtime_core_before_apply_turn_authoritative`
- `runtime_checkpoint_after_companion_systems`
- `runtime_core_after_apply_turn_authoritative`

It also widens context from 24 to 36 lines and function context from 220 to 320 lines.

## Verification target

The next operator artifact should include source-map matches for the runtime core checkpoint/apply markers. That should reveal the exact helper calls between the checkpoint and authoritative application so the next slice can patch the root path instead of adding broader diagnostics.

This is evidence capture only; it does not claim the runtime issue is fixed.
