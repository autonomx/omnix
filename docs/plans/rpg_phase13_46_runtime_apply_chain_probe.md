# Phase 13.46 — runtime apply-chain probe

## Context

ZIP 34 confirmed the diagnostic artifact contract works. It also confirmed the current source-map approach cannot locate the runtime checkpoint/apply markers because those marker names are emitted by timing wrappers rather than literal generated-source strings.

The useful runtime evidence is now:

- normalized failure: `RecursionError: maximum recursion depth exceeded`
- previous marker: `runtime_checkpoint_before_companion_systems`
- last marker: `runtime_core_before_apply_turn_authoritative`

## Change

This slice adds a targeted runtime apply-chain probe in `live_manual_turn_timing.py`.

When the autoplay harness installs live timing, it also wraps the runtime facade and `runtime_part01` through `runtime_part27` apply functions. The wrappers preserve behavior and record:

- module name
- function name
- elapsed time
- ok/failed
- exception type and tail when raised

The artifact is:

- `autoplay-runtime-apply-chain-probe.json`

## Verification target

The next operator run should identify which runtime part actually raises the recursion failure. That should allow a narrow fix instead of more broad diagnostics.

This is evidence capture only; it does not claim the runtime issue is fixed.
