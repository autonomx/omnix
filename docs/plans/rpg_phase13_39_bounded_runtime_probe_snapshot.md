# Phase 13.39 — bounded runtime probe snapshot

## Context

Phase 13.38 proved source instrumentation landed, but the latest operator run still did not produce `autoplay-runtime-turn-result-payloads.json`. The likely cause is that the injected call passed full `locals()` through the bounded payload walker, which can encounter very large or recursive runtime state and add overhead while being swallowed by defensive capture.

## Change

This slice replaces broad local capture with a tiny direct snapshot at the runtime-result probe:

- turn index
- runtime error value summary
- top-level turn result type, keys, and simple scalar items

The snapshot writer avoids walking authoritative state, trace lists, or arbitrary local objects. It writes directly to `autoplay-runtime-turn-result-payloads.json` with source `autoplay_runtime_probe_payload_capture_v4`.

## Verification target

The next operator run should produce the payload artifact without noticeably increasing blocking turn time. The artifact should reveal whether `turn_result` at the probe contains `error`, `traceback`, or only the trace-summary keys seen in the flattened console line.

This is evidence capture only; it does not claim the runtime issue is fixed.
