# Phase 10.6 — LLM Orchestration Layer Implementation Review

**Date:** 2026-04-05 17:05  
**Status:** ✅ All tests passing (29/29)  
**Branch:** feat/phase106-llm-orchestration

---

## Summary

Phase 10.6 implements the **LLM Orchestration Layer** that sits on top of the Phase 10.5 runtime layer. It provides explicit LLM request orchestration with deterministic, bounded, and explicit-boundary rules. The orchestration layer never mutates simulation truth directly; it only writes through runtime/orchestration state helpers.

---

## Architecture

### New Package: `src/app/rpg/orchestration/`

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports for all orchestration APIs |
| `state.py` | LLM orchestration state models, normalization, and lifecycle mutators |
| `request_builder.py` | Deterministic LLM request payload builder |
| `provider_interface.py` | Provider boundary helpers (disabled/replay/live/capture modes) |
| `replay.py` | Replay helpers for captured LLM orchestration artifacts |
| `fallback.py` | Deterministic fallback policy helpers |
| `stream_adapter.py` | Provider result to runtime stream adapter |
| `controller.py` | LLM orchestration controller for single turn execution |

### Updated Files

| File | Change |
|------|--------|
| `src/app/rpg/presentation/__init__.py` | Added `build_orchestration_presentation_payload` export |
| `src/app/rpg/presentation/orchestration_bridge.py` | New read-only bridge from orchestration state to presentation payload |
| `src/app/rpg/api/rpg_presentation_routes.py` | Integrated orchestration payload into scene/dialogue/speakers routes |

---

## Key Features

### 1. Bounded State Model
- **Active requests:** capped at 4
- **Completed requests:** capped at 20
- **Stream events per request:** capped at 40
- Deterministic provider modes: `disabled`, `capture`, `replay`, `live`

### 2. Request Lifecycle Mutators
- `begin_llm_request()` — Create or replace an active orchestration request
- `append_llm_stream_event()` — Append structured stream events with deduplication
- `finalize_llm_request()` — Finalize and move to completed history
- `fail_llm_request()` — Mark as failed with error metadata

### 3. Provider Modes (Phase 10.6 Scope)
- **`disabled`** — Deterministic empty result; fallback only when explicitly allowed
- **`replay`** — Uses captured completed request artifacts; fails hard if missing
- **`capture`/`live`** — Not yet implemented (raises `NotImplementedError`)

### 4. Fallback Policy
- Replay mode: **never** allows silent fallback
- Disabled mode: allows fallback only when `allow_emotional_fallback=True`
- Capture/live mode: allows fallback only when explicitly requested

### 5. Integration
- Orchestration payload is now included in all presentation routes:
  - `POST /api/rpg/presentation/scene` → `presentation.orchestration`
  - `POST /api/rpg/presentation/dialogue` → `presentation.orchestration`
  - `POST /api/rpg/presentation/speakers` → top-level `orchestration`

---

## Test Results

```
============================= 29 passed in 0.19s ==============================
```

### Unit Tests (18)
- State creation and normalization
- Deterministic request IDs
- Bounded state enforcement (active/completed/stream caps)
- Request lifecycle (begin, append, finalize, fail)
- Provider mode normalization
- Disabled/replay result building
- Stream event deduplication
- Fallback policy validation
- Request ID counter parsing

### Functional Tests (6)
- Begin request creates pending active request
- Disabled mode finalizes without text by default
- Disabled mode can use fallback
- Replay mode writes stream and output
- Provider result streams and finalizes through runtime
- Request counter increments deterministically

### Regression Tests (5)
- Replay mode never allows silent fallback
- Replay mode missing artifact fails hard
- Request counter deterministic increments
- Request builder determinism (same input → same output)
- Orchestration bridge immutability (no input mutation)

---

## File List

### New Files (11)
1. `src/app/rpg/orchestration/__init__.py`
2. `src/app/rpg/orchestration/state.py`
3. `src/app/rpg/orchestration/request_builder.py`
4. `src/app/rpg/orchestration/provider_interface.py`
5. `src/app/rpg/orchestration/replay.py`
6. `src/app/rpg/orchestration/fallback.py`
7. `src/app/rpg/orchestration/stream_adapter.py`
8. `src/app/rpg/orchestration/controller.py`
9. `src/app/rpg/presentation/orchestration_bridge.py`
10. `src/tests/unit/rpg/test_phase106_orchestration.py`
11. `src/tests/functional/test_phase106_orchestration_functional.py`
12. `src/tests/regression/test_phase106_orchestration_regression.py`

### Modified Files (3)
1. `src/app/rpg/presentation/__init__.py`
2. `src/app/rpg/api/rpg_presentation_routes.py`
3. `rpg-design.txt` (design spec reference)

---

## Outward Shape

```python
presentation_payload = {
    ...existing_phase_10_fields...,
    "runtime": {
        "runtime_dialogue": {...}
    },
    "orchestration": {
        "llm_orchestration": {
            "provider_mode": str,        # "disabled" | "capture" | "replay" | "live"
            "request_counter": int,       # deterministic counter
            "live_execution_supported": False,  # not yet implemented
            "active_requests": [...],     # bounded to 4
            "completed_requests": [...],  # bounded to 20
            "last_error": {
                "request_id": str,
                "error": str,
            },
        }
    }
}
```

---

## Design Principles Preserved

✅ Mutation in runtime + orchestration only  
✅ Rendering in presentation (read-only bridges)  
✅ Explicit LLM boundary  
✅ Replay-safe request artifacts  
✅ No hidden live execution path  
✅ Deterministic request IDs  
✅ Bounded state caps  

---

## Next Steps (Future Phases)

1. **Live provider execution** — Implement `capture` and `live` modes in controller
2. **Provider callback integration** — Wire actual LLM API calls through the orchestration layer
3. **Streaming response handling** — Real-time chunk streaming from providers to runtime
4. **Capture mode persistence** — Save replay artifacts during capture mode for later replay