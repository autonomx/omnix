# Phase 5.5 — State Boundaries Fixes Review Document

**Date:** 2026-04-02  
**Hour:** 20:21  
**Status:** All 42 tests passing (unit + functional + regression)

---

## Summary

This fix addresses all critical issues identified in `rpg-design.txt` for Phase 5.5 State Boundaries:

1. **snapshot_manager.py**: Missing `timeline_state` and `rng_state` restoration
2. **effects.py**: Missing `is_allowed()` method for guard-style checks
3. **sandbox.py**: Awkward control flow (return + else) and missing try/finally for mode restoration
4. **Tests**: Shallow coverage — now expanded to 42 comprehensive tests

---

## Changes by File

### 1. `src/app/rpg/core/effects.py`

**Added:** `is_allowed(effect_type: str) -> bool` method to `EffectManager`.

**Before:** Systems had to call `check()` and accept exceptions.

**After:** Systems can either:
- Call `check()` to hard-fail (existing behavior)
- Call `is_allowed()` to branch cleanly

```python
def is_allowed(self, effect_type: str) -> bool:
    return {
        "log": self.policy.allow_logs,
        "metric": self.policy.allow_metrics,
        "network": self.policy.allow_network,
        "disk_write": self.policy.allow_disk_write,
        "live_llm": self.policy.allow_live_llm,
        "tool_call": self.policy.allow_tool_calls,
    }.get(effect_type, False)
```

---

### 2. `src/app/rpg/core/snapshot_manager.py`

**Fixed:** `load_snapshot()` was missing restoration of `timeline_state` and `rng_state`.

**Changes in `load_snapshot()`:**
- Added `timeline_state` deserialization
- Added `rng_state` restoration via `loop.rng.setstate()`
- Ensured ordering matches `save_snapshot()` exactly

```python
# PHASE 5.5: Restore additional state
if snapshot.director_state and hasattr(loop, "story_director"):
    loop.story_director.deserialize_state(snapshot.director_state)

if snapshot.timeline_state and hasattr(loop, "event_bus") and hasattr(loop.event_bus, "timeline"):
    timeline = loop.event_bus.timeline
    if hasattr(timeline, "deserialize_state"):
        timeline.deserialize_state(snapshot.timeline_state)

if snapshot.rng_state and hasattr(loop, "rng") and hasattr(loop.rng, "setstate"):
    loop.rng.setstate(snapshot.rng_state["state"])
```

**Note:** The serialization side was already complete. Only loading was missing.

---

### 3. `src/app/rpg/simulation/sandbox.py`

**Fixed:** Three issues:

#### Issue 1: `_replay_events()` return before else
```python
# BEFORE (awkward control flow):
if hasattr(loop, "replay_to_tick"):
    loop.replay_to_tick(...)
    return    # <-- Unnecessary return changes control flow
else:
    for event in events:
        ...

# AFTER (clean if/else):
if not events:
    return  # Skip empty event lists

if hasattr(loop, "replay_to_tick"):
    loop.replay_to_tick(...)
else:
    for event in events:
        ...
```

#### Issue 2: Mode not guaranteed to restore on failure
```python
# BEFORE: mode restored only on success path
for event in future_events:
    loop.event_bus.emit(event)
for _ in range(max_ticks):
    loop.tick("")

if hasattr(loop, "set_mode"):
    loop.set_mode("live")

# AFTER: try/finally guarantees restoration
try:
    for event in future_events:
        loop.event_bus.emit(event)
    for _ in range(max_ticks):
        if hasattr(loop, "tick"):
            loop.tick("")
        ticks_simulated += 1
finally:
    if hasattr(loop, "set_mode"):
        loop.set_mode("live")
```

#### Issue 3: Empty events list crashes replay
Added early return in `_replay_events()` when events list is empty.

---

## Test Results

### Unit Tests: 22 tests
| Class | Tests |
|-------|-------|
| `TestPhase55EffectManagerPolicies` | 4 |
| `TestPhase55IsAllowed` | 6 |
| `TestPhase55EffectManagerSerialization` | 4 |
| `TestPhase55StateBoundaryValidator` | 2 |
| `TestPhase55SnapshotManager` | 2 |
| `TestPhase55EffectManagerSetPolicy` | 2 |
| `TestPhase55ModePolicyCorrectness` | 2 |

### Functional Tests: 8 tests
| Class | Tests |
|-------|-------|
| `TestPhase55StateBoundariesFunctional` | 5 |
| `TestPhase55SandboxModeRestoration` | 2 |
| `TestPhase55EffectPolicyIntegration` | 2 |

### Regression Tests: 12 tests
| Class | Tests |
|-------|-------|
| `TestPhase55StateBoundariesRegression` | 8 |
| `TestPhase55NoStateLeak` | 3 |

**Total: 42 tests — ALL PASSED**

---

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `src/app/rpg/core/effects.py` | +18 | Added `is_allowed()` method |
| `src/app/rpg/core/snapshot_manager.py` | +21 | Added timeline/rng restoration |
| `src/app/rpg/simulation/sandbox.py` | +15/-6 | try/finally mode restore, empty event guard |
| `src/tests/unit/rpg/test_phase55_state_boundaries.py` | rewritten | 22 comprehensive unit tests |
| `src/tests/functional/test_phase55_state_boundaries_functional.py` | rewritten | 8 functional tests |
| `src/tests/regression/test_phase55_state_boundaries_regression.py` | rewritten | 12 regression tests |

---

## Design Document Compliance

| Requirement | Status |
|-------------|--------|
| 1. snapshot_manager.py full implementation | ✅ Done (was already mostly done, added missing parts) |
| 2. game_loop.py set_mode() completeness | ✅ Already complete (no changes needed) |
| 3. sandbox.py awkward control flow | ✅ Fixed |
| 4. replay_engine state-boundary enforcement | ✅ Already complete |
| 5. Tests comprehensive | ✅ Expanded from ~10 to 42 tests |
| Add is_allowed() to EffectManager | ✅ Done |
| Snapshot roundtrip including effect state | ✅ Tested |
| Effect manager injected into subsystems | ✅ Tested |
| Sandbox restores mode on failure | ✅ Tested |