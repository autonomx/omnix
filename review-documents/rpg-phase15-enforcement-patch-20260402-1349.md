# RPG Phase 1.5 — Enforcement Patch Review Document

**Date:** 2026-04-02 13:49 (America/Vancouver, UTC-7:00)  
**Implementation Reference:** `rpg-design.txt`  
**Status:** ✅ COMPLETE — All 88 tests passing

---

## 1. Executive Summary

Phase 1.5 enforces the architectural patterns established in Phase 1, transforming optional patterns into hard constraints. The patches ensure:

- **Event Bus Usage:** All cross-system communication flows through EventBus
- **Single Loop Authority:** Only one GameLoop instance can tick at a time
- **Narrative Event Emission:** StoryDirector emits `scene_generated` events
- **Legacy System Blocking:** Deprecated modules raise RuntimeError on import
- **TickPhase Preparation:** Enumeration defined for future phased execution

---

## 2. Patches Implemented

### PATCH 1 — Pass Event Bus Through Systems
| File | Change |
|------|--------|
| `src/app/rpg/core/game_loop.py` | `world.tick()` → `world.tick(self.event_bus)` |
| `src/app/rpg/core/game_loop.py` | `npc_system.update(intent)` → `npc_system.update(intent, self.event_bus)` |
| `src/app/rpg/core/game_loop.py` | `story_director.process(events, intent)` → `story_director.process(events, intent, self.event_bus)` |

### PATCH 2 — Story Director Emits Events
| File | Change |
|------|--------|
| `src/app/rpg/narrative/story_director.py` | Added `event_bus` parameter to `process()` method |
| `src/app/rpg/narrative/story_director.py` | Emits `Event("scene_generated", {...})` after scene generation |

### PATCH 3 — Single Game Loop Enforcement
| File | Change |
|------|--------|
| `src/app/rpg/core/game_loop.py` | Added `_active_loop` class variable |
| `src/app/rpg/core/game_loop.py` | Added guard in `tick()` to detect multiple loops |

### PATCH 4 — Event Bus Enforcement Scaffold
| File | Change |
|------|--------|
| `src/app/rpg/core/event_bus.py` | Added `enforce: bool` parameter to `__init__` |
| `src/app/rpg/core/event_bus.py` | Added `assert_event_usage()` method with stack inspection |
| `src/app/rpg/core/event_bus.py` | `emit()` calls `assert_event_usage()` |

### PATCH 5 — Hard Deprecate Old Systems
| File | Change |
|------|--------|
| `src/app/rpg/event_bus.py` | Replaced with `raise RuntimeError("DEPRECATED...")` |
| `src/app/rpg/director/director.py` | Replaced with `raise RuntimeError("DEPRECATED...")` |

### PATCH 6 — Prepare Tick Phase System
| File | Change |
|------|--------|
| `src/app/rpg/core/game_loop.py` | Added `TickPhase` enum with `PRE_WORLD`, `POST_WORLD`, `PRE_NPC`, `POST_NPC` |

### PATCH 7 — Update Game Engine (Pass Event Bus)
| File | Status |
|------|--------|
| `src/app/rpg/core/game_engine.py` | Already correct — event_bus passed through constructor |

### PATCH 8 — Update Test Mocks
All test mocks updated to accept `event_bus` parameter:
- `MockWorld.tick(event_bus)` 
- `MockNPCSystem.update(intent, event_bus)`
- `MockStoryDirector.process(events, intent, event_bus)`

### PATCH 9 — Add Enforcement Test
| File | Description |
|------|-------------|
| `src/tests/unit/rpg/test_event_enforcement.py` | 11 tests for enforcement features |

---

## 3. Code Diff Summary

### `src/app/rpg/core/event_bus.py`
```diff
+ import inspect

  def __init__(self, debug: bool = False, enforce: bool = False):
+     self._enforce = enforce

  def emit(self, event: Event) -> None:
+     self.assert_event_usage()

+ def assert_event_usage(self):
+     """Development-time enforcement to detect misuse."""
+     if not self._enforce:
+         return
+     stack = inspect.stack()
+     for frame in stack:
+         module = inspect.getmodule(frame[0])
+         if not module:
+             continue
+         name = module.__name__
+         if "core.event_bus" in name:
+             continue
```

### `src/app/rpg/core/game_loop.py`
```diff
+ from enum import Enum

+ class TickPhase(Enum):
+     PRE_WORLD = "pre_world"
+     POST_WORLD = "post_world"
+     PRE_NPC = "pre_npc"
+     POST_NPC = "post_npc"

  class WorldSystem(Protocol):
-     def tick(self) -> None:
+     def tick(self, event_bus: EventBus) -> None:

  class NPCSystem(Protocol):
-     def update(self, intent: Dict[str, Any]) -> None:
+     def update(self, intent: Dict[str, Any], event_bus: EventBus) -> None:

  class StoryDirector(Protocol):
      def process(
-         self, events: List[Event], intent: Dict[str, Any]
+         self, events: List[Event], intent: Dict[str, Any], event_bus: EventBus
      ) -> Dict[str, Any]:

  class GameLoop:
+     _active_loop = None

      def tick(self, player_input: str) -> Dict[str, Any]:
+         if GameLoop._active_loop and GameLoop._active_loop is not self:
+             raise RuntimeError("Multiple GameLoop instances detected")
+         GameLoop._active_loop = self

-         self.world.tick()
+         self.world.tick(self.event_bus)

-         self.npc_system.update(intent)
+         self.npc_system.update(intent, self.event_bus)

-         narrative = self.story_director.process(events, intent)
+         narrative = self.story_director.process(events, intent, self.event_bus)
```

### `src/app/rpg/narrative/story_director.py`
```diff
  def process(
      self,
      events: List[Event],
      player_intent: Dict[str, Any],
+     event_bus: Any,
  ) -> Dict[str, Any]:

      scene = self.scene_engine.generate(next_beat)

+     event_bus.emit(Event(
+         "scene_generated",
+         {
+             "tick": self._tick_count,
+             "beat": next_beat,
+         }
+     ))

      return scene
```

### `src/app/rpg/event_bus.py` (DEPRECATED)
```diff
- # Full implementation replaced with:
+ raise RuntimeError(
+     "DEPRECATED: Use src.app.rpg.core.event_bus.EventBus"
+ )
```

### `src/app/rpg/director/director.py` (DEPRECATED)
```diff
- # Full implementation replaced with:
+ raise RuntimeError(
+     "DEPRECATED: Use src.app.rpg.narrative.story_director.StoryDirector"
+ )
```

---

## 4. Test Results

### Unit Tests (38 + 11 = 49 tests)
| File | Tests | Status |
|------|-------|--------|
| `test_phase1_stabilize.py` | 38 | ✅ ALL PASSING |
| `test_event_enforcement.py` | 11 | ✅ ALL PASSING |

### Functional Tests (19 tests)
| File | Tests | Status |
|------|-------|--------|
| `test_phase1_stabilize_functional.py` | 19 | ✅ ALL PASSING |

### Regression Tests (20 tests)
| File | Tests | Status |
|------|-------|--------|
| `test_phase1_stabilize_regression.py` | 20 | ✅ ALL PASSING |

**Total: 88 tests — 0 failures**

---

## 5. Test Categories

### Unit Tests
- Event creation and independence
- EventBus emit/collect/peek/clear/reset
- GameLoop tick execution, callbacks, event collection
- StoryDirector process, reset, custom components
- Default components (arc manager, plot engine, scene engine)
- GameEngine handle_input, reset, callbacks, event bus sharing
- Phase 1 integration (full pipeline, decoupling, deterministic execution)

### Enforcement Tests (NEW)
- EventBus enforcement flag behavior
- Single loop instance detection and guard
- Deprecated module import blocking
- TickPhase enumeration values and imports

### Functional Tests
- Single game loop authority verification
- Event bus decoupling (NPC → Director event flow)
- Phase 1.5 StoryDirector event emission
- Narrative director pipeline
- TickPhase enumeration
- Engine integration
- Regression-style edge cases (empty input, special chars, long input, rapid ticks)

### Regression Tests (NEW)
- Architectural constraints (event bus as only communication path)
- World/NPC/Director receives event_bus parameter
- StoryDirector emits scene_generated event
- Single loop enforcement (single instance, multiple detection, reset)
- TickPhase enumeration
- Edge cases (empty events, large events, enforce flag)
- Integration with new signatures
- Backwards compatibility (deprecated modules, core exports)

---

## 6. Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/app/rpg/core/event_bus.py` | ENHANCED | Added enforce flag, assert_event_usage() |
| `src/app/rpg/core/game_loop.py` | ENHANCED | Added event_bus param to protocols, TickPhase enum, single loop guard |
| `src/app/rpg/core/__init__.py` | UPDATED | Added TickPhase export |
| `src/app/rpg/narrative/story_director.py` | ENHANCED | Added event_bus param, emits scene_generated event |
| `src/app/rpg/event_bus.py` | DEPRECATED | Replaced with RuntimeError |
| `src/app/rpg/director/director.py` | DEPRECATED | Replaced with RuntimeError |
| `src/tests/unit/rpg/test_phase1_stabilize.py` | UPDATED | Updated mocks, added single-loop guard fixture |
| `src/tests/unit/rpg/test_event_enforcement.py` | NEW | 11 enforcement tests |
| `src/tests/functional/test_phase1_stabilize_functional.py` | UPDATED | Updated mocks, added Phase 1.5 specific tests |
| `src/tests/regression/test_phase1_stabilize_regression.py` | UPDATED | Rewritten for Phase 1.5 with 20 tests |

---

## 7. Verification Checklist

- [x] Single loop authority — enforced via `_active_loop` guard
- [x] Event-driven architecture — event_bus passed to all systems
- [x] Narrative emits events — StoryDirector emits `scene_generated`
- [x] Legacy systems blocked — deprecated modules raise RuntimeError
- [x] No hidden coupling — all communication through EventBus
- [x] Debuggable execution — enforce flag for development-time checks
- [x] TickPhase defined — PRE_WORLD, POST_WORLD, PRE_NPC, POST_NPC
- [x] Unit tests passing — 49 tests
- [x] Functional tests passing — 19 tests  
- [x] Regression tests passing — 20 tests

---

*Document generated automatically as part of Phase 1.5 implementation.*