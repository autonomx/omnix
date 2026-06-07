# RPG Phase 13.19 Runner Wrapper Regression Fix

This is a narrow follow-up to Phase 13.19.

## Trigger

After Phase 13.19 merged, the operator 100-turn command failed before turn execution with:

```text
RuntimeError: real_autoplay_runner_too_small:bytecode_bytes=278
```

The failure indicates that the post-load payload capture wrapper wrapped a function that the runtime runner presence guard expects to remain the real runner implementation.

## Root cause

The Phase 13.19 wrapper selector was too broad. It allowed generic names containing `trace` or `stage`, and functions whose bytecode referenced probe-related names. In the generated harness this could replace important runtime/facade functions with small `functools.wraps` wrappers.

## Fix

The payload capture wrapper is now restricted to explicit probe-emission helper names only:

- `emit_probe`
- `probe_emit`
- `probe_event`
- `write_probe`
- `record_probe`
- `log_probe`
- `autoplay_probe`
- `debug_probe`

It now explicitly excludes names containing:

- `main`
- `runner`
- `autoplay_runner`
- `run_autoplay`
- `assert`
- `facade`
- `manifest`
- `wrapper`
- `runtime_turn`
- `call_turn_runtime`
- `manual_turn`

The source instrumentation helper remains present for compatibility, but returns source unchanged because generated runtime source is manifest-guarded.

## Regression tests

The Phase 13.19 test now verifies:

- generated runtime source is preserved unchanged;
- explicit probe-emission helpers are still wrapped;
- `_run_real_autoplay` is not wrapped;
- `_assert_real_autoplay_runner_present` is not wrapped;
- runtime facade manifest helpers are not wrapped;
- `_call_turn_runtime` is not wrapped.

## Boundary confirmation

This fix does not add LLM calls, provider calls, gameplay changes, or production-readiness claims. It only narrows diagnostic wrapper selection so the real autoplay runner remains intact.
