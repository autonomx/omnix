# Phase 2 — Critical Replay Engine Fixes Review

**Date:** 2026-04-02 14:37  
**Status:** ✅ Implemented & Tested  
**Tests:** 57 passed (27 unit, 13 functional, 17 regression)

## Summary

Implemented 5 critical fixes from `rpg-design.txt` to make the replay engine
deterministic and production-ready. These fixes address architectural problems
that would break determinism, memory systems, branching timelines, and save/load.

## Fixes Implemented

### Fix #1 — History Duplication Prevention

**Problem:** During replay, events were added to history, causing:
- Duplicated causal chain
- Broken temporal reasoning
- NPC memory double-counting events
- Analytics becoming garbage

**Solution:** Added `replay` parameter to `EventBus.emit()`:
```python
- def emit(self, event: Event) -> None:
-     self._history.append(event)
+ def emit(self, event: Event, *, replay: bool = False) -> None:
+     if not replay:
+         self._history.append(event)
```

**File:** `src/app/rpg/core/event_bus.py`

### Fix #2 — System Factory Pattern (No State Leaks)

**Problem:** Replay reused system instances (world, npc_system, etc.) causing
state leaks that broke determinism. Replay was NOT a fresh simulation.

**Solution:** `GameEngine` now requires factory functions to create FRESH system
instances for each replay/load:
```python
engine = GameEngine(
    intent_parser_factory=MyParser,     # Factory, not instance
    world_factory=MyWorld,
    npc_system_factory=MyNPCs,
    story_director_factory=MyDirector,
    scene_renderer_factory=MyRenderer,
)
```

**Files:** `src/app/rpg/core/game_engine.py`, `src/app/rpg/core/game_loop.py`

### Fix #3 — Replay Advances Tick Count

**Problem:** Replay did not update `loop._tick_count`, causing:
- `loop.tick_count == 0` after replay
- Future tick collisions
- Temporal logic breaking

**Solution:** Replay now advances `_tick_count` to match max replayed tick:
```python
for event in events:
    tick = event.payload.get("tick")
    if tick is not None:
        loop._tick_count = max(loop._tick_count, tick)
    self._apply_event(loop, event)
```

**File:** `src/app/rpg/core/replay_engine.py`

### Fix #4 — Removed load_history() from Replay Path

**Problem:** `load_history()` preloaded history instead of building it naturally,
breaking the causality model.

**Solution:** Replay no longer calls `load_history()`. History builds naturally
from event dispatch during replay. The `load_history()` method remains available
for manual bootstrap scenarios.

**File:** `src/app/rpg/core/replay_engine.py`

### Fix #5 — Event Dispatch to System Handlers

**Problem:** Replay emitted events but nothing consumed them — no world.tick(),
no npc.update(), no story_director.process(). Replay was just logging events,
not reconstructing state.

**Solution:** Added `EventConsumer` protocol and event dispatch:
```python
class EventConsumer(Protocol):
    def handle_event(self, event: Event) -> None: ...

# In replay:
if hasattr(loop.world, "handle_event"):
    loop.world.handle_event(event)
if hasattr(loop.npc_system, "handle_event"):
    loop.npc_system.handle_event(event)
if hasattr(loop.story_director, "handle_event"):
    loop.story_director.handle_event(event)
```

**File:** `src/app/rpg/core/replay_engine.py`

## Files Modified

| File | Lines Changed | Description |
|------|--------------|-------------|
| `event_bus.py` | +155, -30 | Added replay parameter, history management, tick tracking |
| `replay_engine.py` | ~200 total | Complete rewrite with all 5 fixes |
| `game_engine.py` | +90, -30 | Added factory pattern, save/load methods |
| `game_loop.py` | +60, -30 | Added contextvar safety, replay_to_tick with factory |
| `__init__.py` | +8 | Export new classes |

## Test Coverage

### Unit Tests (27 tests)
- `TestReplayHistoryNoDuplication` (4 tests)
- `TestSystemFactoryPattern` (2 tests)
- `TestTickAdvancement` (3 tests)
- `TestEventDispatchToSystems` (4 tests)
- `TestNoLoadHistory` (1 test)
- `TestReplayEngineBasic` (1 test)
- `TestReplayEngineUpToTick` (2 tests)
- `TestReplayEngineEdgeCases` (3 tests)
- `TestTickRange` (3 tests)
- `TestEventBusEmitReplay` (4 tests)

### Functional Tests (13 tests)
- `TestSaveAndLoadCycle` (5 tests)
- `TestTimeTravelDebug` (3 tests)
- `TestReplayIntegration` (5 tests)

### Regression Tests (17 tests)
- `TestHistoryDuplicationRegression` (3 tests)
- `TestSystemStateLeakRegression` (3 tests)
- `TestTickAdvancementRegression` (2 tests)
- `TestNoLoadHistoryRegression` (2 tests)
- `TestEventDispatchRegression` (4 tests)
- `TestEndToEndRegression` (3 tests)

## Capabilities After Fixes

| Capability | Before | After |
|-----------|--------|-------|
| Deterministic replay | ❌ Broken | ✅ Fixed |
| History clean | ❌ Duplicated | ✅ Clean |
| Fresh systems | ❌ Reused | ✅ Factory |
| Tick collision | ❌ Possible | ✅ Prevented |
| State reconstruction | ❌ Logging only | ✅ Dispatched |
| Save/load | ❌ Corrupt | ✅ Working |
| Time-travel debug | ❌ Broken | ✅ Working |

## Result

The replay engine now provides a proper **Event-Sourced Engine Core**:
- ✅ Deterministic replay
- ✅ Time travel debugging
- ✅ Save/load via event logs
- ✅ Event log as source of truth
- ✅ Branching timeline support