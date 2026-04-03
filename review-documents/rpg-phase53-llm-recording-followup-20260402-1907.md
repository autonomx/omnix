# RPG Phase 5.3 — LLM Recording Follow-up Patches

**Date:** 2026-04-02 19:07 UTC-7  
**Status:** Implemented and Tested  
**Tests:** 20 passed (8 unit, 3 functional, 9 regression)

---

## What This Patch Fixes

After the initial Phase 5.3 implementation, five remaining issues were identified:

1. **`GameLoop.set_llm_recorder()` did not propagate** — recorder was stored locally but never forwarded to subsystems
2. **LLM recorder keys lacked call config** — `complete()`, `chat()`, `generate()` with same prompt/context would collide
3. **`DeterministicLLMClient` did not pass method/model** — recordings for different methods or models could overwrite each other
4. **No regression test for config-sensitive keying** — no proof that different method/model configs produce different keys
5. **No functional test proving replay reuse without inner LLM calls** — replay path was not strongly tested

---

## Changes Summary

### 1. `src/app/rpg/core/llm_recording.py`

#### 1.1 `LLMRecorder.make_key()` — Added `config` parameter

```python
def make_key(
    self,
    prompt: Any,
    context: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,  # NEW
) -> str:
```

Keys now include `config` (method name, model identifier, etc.) so that:
- `complete("prompt")` and `chat("prompt")` hash to different keys
- Same prompt with different models produce separate recordings

#### 1.2 `LLMRecorder.record()` and `replay()` — Thread `config` through

Both methods now accept and pass the optional `config` parameter to `make_key()`.

#### 1.3-1.5 `DeterministicLLMClient.complete/chat/generate()` — Build and use config

Each method now constructs a `call_config` dictionary:

```python
call_config = {"method": "complete"}  # or "chat" / "generate"
if getattr(self.inner, "model", None) is not None:
    call_config["model"] = self.inner.model
```

This config is passed through `record()` and `replay()` for proper key isolation.

### 2. `src/app/rpg/core/game_loop.py`

#### 2.1 `GameLoop.set_llm_recorder()` — Propagate to subsystems

```python
for system_name in ("world", "npc_system", "story_director", "scene_renderer"):
    system = getattr(self, system_name, None)
    if system is not None and hasattr(system, "set_llm_recorder"):
        system.set_llm_recorder(recorder)
```

Now attaching an LLM recorder to the game loop actually makes it available to any subsystems that support it.

### 3. `src/tests/regression/test_phase53_llm_recording_regression.py`

#### New tests:
- **`test_record_key_depends_on_config`** — Proves same prompt/context with different method/model configs produce different keys
- **`test_wrapper_uses_method_and_model_in_key`** — Proves `DeterministicLLMClient` records and replays with config-aware keys, confirming end-to-end flow

#### Updated `_DummyLLM`:
- Added `self.model = "dummy-model-v1"` so the wrapper includes model in config

### 4. `src/tests/functional/test_phase53_llm_recording_functional.py`

#### New test:
- **`test_replay_mode_uses_recorded_outputs_only`** — Records in live mode, replays in replay mode, and proves that replay path produces identical score with zero inner LLM calls

### 5. `src/tests/unit/rpg/test_phase53_llm_recording.py`

#### Fixed:
- **`test_deterministic_llm_replays_without_calling_inner`** — Was recording without config, then replaying with config-aware key (key mismatch). Now records in live mode first, then replays from the same recorder, ensuring key match.

---

## Test Results

```
20 passed in 0.14s
```

| Suite | Tests | Status |
|-------|-------|--------|
| Unit | 8 | All pass |
| Functional | 3 | All pass |
| Regression | 9 | All pass |

---

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Backward compatibility (record/replay without config) | Low | `config` parameter defaults to `None` → `{}` in key, existing code continues to work |
| Hash collision across methods | Fixed | Method is now part of key |
| Model overwrite | Fixed | Model is now part of key |
| Subsystem propagation | Fixed | GameLoop propagates recorder to any system with `set_llm_recorder()` |

---

## Files Modified

1. `src/app/rpg/core/llm_recording.py` — Core recording/replay with config support
2. `src/app/rpg/core/game_loop.py` — Recorder propagation
3. `src/tests/unit/rpg/test_phase53_llm_recording.py` — Unit tests (fixed + updated)
4. `src/tests/functional/test_phase53_llm_recording_functional.py` — Functional tests (new test)
5. `src/tests/regression/test_phase53_llm_recording_regression.py` — Regression tests (new tests)

---

## Design Principle

**Recording keys must be fully qualified.** A recording of `complete("prompt")` must not collide with `chat("prompt")` or `complete("prompt")` from a different model. This ensures replay-mode isolation across all LLM call paths.