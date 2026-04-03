# Phase 52 — Deterministic Replay Hardening
## Review Document

**Date:** 2026-04-02-1801  
**Branch:** rpg-phase52-deterministic-replay-hardening  
**Status:** Implemented & Tested

---

## Summary

This patch implements deterministic replay hardening fixes from `rpg-design.txt` to make the deterministic core strictly safer.

### What This Patch Achieves

After this patch:

1. **Replay can no longer silently fabricate missing IDs/timestamps** — `EventBus.emit()` now raises `RuntimeError` in replay mode if `event.timestamp` or `event.event_id` is missing.
2. **EventContext becomes fully useful, not half-used** — `EventContext.tick` is now applied alongside `EventContext.parent_id` during `emit()`.
3. **Replay mode cannot remain stuck after failures** — `ReplayEngine.replay()` now wraps the replay loop in `try/finally` to ensure replay mode always resets after exceptions.
4. **load_history() behaves like a real state restore** — `EventBus.load_history()` now clears the pending queue to prevent stale events from prior usage.
5. **The deterministic layer becomes much harder to accidentally break** — Comprehensive unit and regression tests validate all fixes.

---

## Changes

### 1. EventBus — `src/app/rpg/core/event_bus.py`

#### Fix 1: EventContext.tick Applied Alongside parent_id

```python
# BEFORE: Only parent_id was checked/applied
if context is not None and context.parent_id is not None:
    ...

# AFTER: Both parent_id and tick are checked/applied
if context is not None and (context.parent_id is not None or context.tick is not None):
    event = Event(
        ...
        parent_id=context.parent_id if context.parent_id is not None else event.parent_id,
        tick=context.tick if context.tick is not None else event.tick,
    )
```

**Impact:** Events emitted with `EventContext(tick=N)` now correctly propagate the tick value.

#### Fix 2: Strict Replay Mode Enforcement (Timestamp)

```python
# BEFORE: Silently generated new timestamps
event_timestamp = event.timestamp if event.timestamp is not None else self._clock.now()

# AFTER: Raises RuntimeError in replay mode
if self._determinism.replay_mode and event.timestamp is None:
    raise RuntimeError(
        "Replay mode requires recorded event.timestamp; refusing fresh timestamp generation."
    )
event_timestamp = event.timestamp if event.timestamp is not None else self._clock.now()
```

**Impact:** Replay mode now errors if trying to invent timestamps, preventing non-deterministic replay.

#### Fix 3: Strict Replay Mode Enforcement (Event ID)

```python
# BEFORE: Silently generated new event IDs
if event_id is None:
    event_id = compute_deterministic_event_id(...)

# AFTER: Raises RuntimeError in replay mode
if event_id is None:
    if self._determinism.replay_mode:
        raise RuntimeError(
            "Replay mode requires recorded event.event_id; refusing fresh ID generation."
        )
    event_id = compute_deterministic_event_id(...)
```

**Impact:** Replay mode now errors if trying to invent event IDs.

#### Fix 4: load_history() Clears Pending Queue

```python
# BEFORE: Only replaced history
self._history = list(events)

# AFTER: Also clears pending events
self._history = list(events)
self._events.clear()
```

**Impact:** Loaded history fully resets pending queue state.

---

### 2. ReplayEngine — `src/app/rpg/core/replay_engine.py`

#### Fix: Exception-Safe Replay Teardown

```python
# BEFORE: Replay mode turn-off not in finally block
for event in events:
    ...
# Exit replay mode
loop.event_bus.set_replay_mode(False)

# AFTER: Wrapped in try/finally
try:
    for event in events:
        ...
finally:
    # Exit replay mode — always, even on exception
    if hasattr(loop, "event_bus") and hasattr(loop.event_bus, "set_replay_mode"):
        loop.event_bus.set_replay_mode(False)
    if hasattr(loop, "set_mode"):
        loop.set_mode("live")
```

**Impact:** Replay mode is guaranteed to reset even if the replay loop throws.

---

### 3. Tests

#### Unit Tests (`test_phase52_determinism.py`)

| Test | Description |
|------|-------------|
| `test_emit_applies_context_tick_and_parent` | EventContext.tick and parent_id both applied |
| `test_replay_mode_refuses_fresh_timestamp_generation` | RuntimeError on missing timestamp in replay |
| `test_replay_mode_refuses_fresh_event_id_generation` | RuntimeError on missing event_id in replay |
| `test_load_history_clears_pending_queue` | Pending queue cleared after load_history |
| `test_context_tick_does_not_get_overwritten_by_current_tick` | Context.tick preserved even when bus is at different tick |

#### Regression Tests (`test_phase52_determinism_regression.py`)

| Test | Description |
|------|-------------|
| `test_seen_event_ids_set_stays_in_sync_with_bounded_deque` | Set bounded with small deque |
| `test_load_history_restores_seq_and_tick_state` | Timeline nodes present after load |
| `test_replay_mode_flag_resets_after_exception` | Finally block resets replay mode |

---

## Test Results

All 8 new tests pass:

```
TestPhase52DeterministicHardening::test_context_tick_does_not_get_overwritten_by_current_tick  PASSED
TestPhase52DeterministicHardening::test_emit_applies_context_tick_and_parent                     PASSED
TestPhase52DeterministicHardening::test_load_history_clears_pending_queue                        PASSED
TestPhase52DeterministicHardening::test_replay_mode_refuses_fresh_event_id_generation            PASSED
TestPhase52DeterministicHardening::test_replay_mode_refuses_fresh_timestamp_generation           PASSED
TestPhase52DeterministicReplayRegression::test_load_history_restores_seq_and_tick_state           PASSED
TestPhase52DeterministicReplayRegression::test_replay_mode_flag_resets_after_exception           PASSED
TestPhase52DeterministicReplayRegression::test_seen_event_ids_set_stays_in_sync_with_bounded_deque  PASSED

Total: 8 passed
```

---

## Files Changed

| File | Change Type |
|------|------------|
| `src/app/rpg/core/event_bus.py` | Modified — 4 fixes applied |
| `src/app/rpg/core/replay_engine.py` | Modified — try/finally for replay loop |
| `src/tests/unit/rpg/test_phase52_determinism.py` | Modified — 5 new unit tests |
| `src/tests/regression/test_phase52_determinism_regression.py` | Modified — 3 new regression tests |
| `review-documents/rpg-phase52-deterministic-replay-hardening-20260402-1801.md` | Created — This review document |
| `review-documents/rpg-phase52-deterministic-replay-hardening-20260402-1801.diff` | Created — Code diff |

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Existing code emits events without timestamp/event_id in normal mode | Low | Only affects replay mode; normal mode still auto-generates |
| Tests rely on DeterministicClock constructor parameter name | Medium | Fixed to use `start_time` not `start` |
| Load_history clearing events breaks edge case | Low | Pending events are meant to be consumed; clearing is correct |

---

## Next Steps

The next patch after this should be the **LLM record/replay layer**, because that is now the biggest remaining source of nondeterminism once these core fixes are in place.