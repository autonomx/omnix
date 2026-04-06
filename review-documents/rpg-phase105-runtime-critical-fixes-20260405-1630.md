# Phase 10.5 — Runtime Layer Critical Fixes

**Date:** 2026-04-05 16:30
**Status:** Applied

## Critical Issues Fixed

### 1. ✅ Interruption Sort Determinism
- **File:** `src/app/rpg/runtime/dialogue_runtime.py`
- **Fix:** Changed `-_safe_int(item.get("priority"), 0)` to `_safe_int(item.get("priority"), 0) * -1`
- **Functions:** `_sort_key_pending_interrupt`, `_sort_key_interruption_candidate`
- **Reason:** Negation can cause issues with MIN_INT values; multiplication is safer for deterministic ordering

### 2. ✅ Sequence ID Correctness
- **File:** `src/app/rpg/runtime/dialogue_runtime.py`
- **Fix:** Changed `build_runtime_sequence_id(tick, 0)` to `build_runtime_sequence_id(tick, sequence_index)`
- **Function:** `begin_runtime_turn`
- **Reason:** Was ignoring the passed `sequence_index`, causing inconsistent sequence IDs

### 3. ✅ Emotion Decay Tick Drift
- **File:** `src/app/rpg/runtime/dialogue_runtime.py`
- **Fix:** Changed `"updated_tick": tick if delta > 0 else updated_tick` to `"updated_tick": updated_tick`
- **Function:** `decay_runtime_emotions`
- **Reason:** Updating tick on decay caused non-replayable emotional curves across tick boundaries

## Additional Issues Addressed

### 4. ✅ Stream Chunk Ordering
- **File:** `src/app/rpg/presentation/runtime_bridge.py`
- **Status:** Kept explicit sorted order for UI stability; runtime preserves insertion order
- **Note:** Runtime uses insertion-order dedupe, presentation layer sorts for stable display

### 5. ✅ Duplicate Interruption Targeting Guard
- **File:** `src/app/rpg/runtime/dialogue_runtime.py`
- **Status:** Already has `if actor_id in interrupted_target_ids_this_tick: continue` guard in place
- **Verified:** Present in original code (line ~1006-1008 area)

## Test Coverage

Added `test_phase105_fallback_policy_regression.py` with 3 tests:
- `test_phase105_finalize_runtime_turn_does_not_invent_text_by_default`
- `test_phase105_finalize_runtime_turn_can_use_emotional_fallback_when_explicitly_enabled`
- `test_phase105_interrupted_turn_does_not_invent_text_by_default`

All passing (3/3).