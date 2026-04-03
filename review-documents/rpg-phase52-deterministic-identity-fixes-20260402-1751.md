# RPG Phase 5.2 — Deterministic Identity Fixes — Review Document

**Generated:** 2026-04-02 17:51 UTC-7
**Design Spec:** `rpg-design.txt`
**Diff File:** `review-documents/rpg-phase52-deterministic-identity-fixes-20260402-1751.diff`

## Overview

This patch implements the deterministic identity fixes specified in `rpg-design.txt`. The primary goal is to replace process-global state (global event counter, class-global clock) with instance-local, seed-based deterministic identity derived from causal history.

## Key Changes

### 1. NEW FILE: `src/app/rpg/core/determinism.py`

- **DeterminismConfig**: Configuration dataclass for deterministic execution (seed, strict_replay, replay_mode)
- **SeededRNG**: Per-engine seeded RNG wrapper (never use module-level `random` directly)
- **stable_json**: Deterministic JSON serialization with sorted keys and rounded floats
- **compute_deterministic_event_id()**: SHA256-based deterministic event identity derived from seed + type + payload + source + parent_id + tick + seq

### 2. MODIFIED: `src/app/rpg/core/event_bus.py`

| Issue | Fix |
|-------|-----|
| Global counter IDs | Replaced with `compute_deterministic_event_id()` using causal hash |
| Class-global clock leakage | Replaced with instance `_clock` created in `__init__` |
| `Event.__post_init__` auto-assigning IDs | Made passive — all assignment now happens in `emit()` |
| Broken deque/set sync | Fixed eviction: remove oldest BEFORE append when at maxlen |
| Incomplete `load_history()` | Now rebuilds full deterministic state (timeline, seen_ids, seq, tick) |
| Tick overwrite on replay/live emit | Respects explicit `event.tick`; only falls back to bus tick when missing |
| Added `set_replay_mode()` | Hook for replay/live isolation |

### 3. MODIFIED: `src/app/rpg/core/replay_engine.py`

- Added `set_replay_mode(True)` on bus and `set_mode("replay")` on loop before replay
- Added `set_replay_mode(False)` on bus and `set_mode("live")` on loop after replay
- Tick extraction now uses `event.tick` first-class field before falling back to `payload.get("tick")`

### 4. MODIFIED: `src/app/rpg/core/game_loop.py`

- Added `self.mode: str = "live"` for replay/live isolation
- Added `set_mode()` method to propagate mode to subsystems
- Added `self.npc_method = None` to enable planner path override
- NPC update now routes through `npc_method` when set (planner integration fix)
- `replay_to_tick()` now **requires** `loop_factory` — raises `RuntimeError` if not provided (removes unsafe live-system reuse)

### 5. MODIFIED: `src/app/rpg/core/__init__.py`

- Added exports: `DeterminismConfig`, `SeededRNG`, `compute_deterministic_event_id`

## Test Results

### Unit Tests: 38/38 PASSED

| Test Class | Tests | Status |
|------------|-------|--------|
| TestDeterministicEventIds | 5 | ✅ All passed |
| TestDeterministicClock | 7 | ✅ All passed |
| TestEventWithDeterministicClock | 4 | ✅ All passed |
| TestSeenEventIdsMemoryLeak | 2 | ✅ All passed |
| TestFirstClassTick | 6 | ✅ All passed |
| TestTimelineRebuildOnLoad | 3 | ✅ All passed |
| TestBitExactReplay | 2 | ✅ All passed |
| TestSeededRNG | 4 | ✅ All passed |
| TestStableJson | 5 | ✅ All passed |

### Functional/Regression Tests

Import issue exists in legacy test files (pre-existing, unrelated to this change).
The `app` module conflicts with `app.py` in the project root — known issue.

## Files Changed Summary

| File | Action | Description |
|------|--------|-------------|
| `src/app/rpg/core/determinism.py` | **CREATED** | Seeded deterministic primitives |
| `src/app/rpg/core/event_bus.py` | MODIFIED | Remove global counter/clock, add deterministic emit |
| `src/app/rpg/core/replay_engine.py` | MODIFIED | Add replay mode hooks, first-class tick extraction |
| `src/app/rpg/core/game_loop.py` | MODIFIED | Add mode tracking, planner path, strict replay |
| `src/app/rpg/core/__init__.py` | MODIFIED | Export new determinism classes |
| `src/tests/unit/rpg/test_phase52_determinism.py` | MODIFIED | Updated for seeded deterministic tests |

## What This Fixes

After these changes:
1. **Event identity is deterministic per causal history**, not per process call order
2. **Clock behavior is instance-local**, not global class state
3. **Dedup state no longer leaks or corrupts** (deque/set sync fixed)
4. **load_history() is replay-safe** (full state restoration)
5. **NPC planner integration affects execution** (planner path actually used)
6. **Replay path no longer silently reuses mutated live systems** (strict mode)

## Recommended Factory Pattern

```python
from app.rpg.core import EventBus, DeterministicClock, DeterminismConfig

def make_seeded_bus(seed: int) -> EventBus:
    return EventBus(
        clock=DeterministicClock(start_time=0.0, increment=0.001),
        determinism=DeterminismConfig(seed=seed),
    )
```

Every live/sandbox/replay engine must use a bus created from the same seed for cross-run equivalence.