# RPG Design Implementation — TIER 7: Faction Simulation + Reputation Economy

**Date:** 2026-04-01  
**Time:** 12:50 PM  
**Design Source:** `rpg-design.txt` — TIER 7 specification

---

## Executive Summary

This implementation adds **TIER 7: Faction Simulation + Reputation Economy** to the RPG system, transforming the world from "story reacting to player" to "world evolving with or without the player."

### What Changed
- **2 new modules** created (FactionSystem, ReputationEngine)
- **1 existing module** updated (PlayerLoop integration)
- **2 test files** created (62 tests total, all passing)

---

## Files Created

### 1. `src/app/rpg/world/faction_system.py`
**New file** — Faction model and simulation engine.

#### Classes Added

**`Faction`** (dataclass)
- Represents a political/military/social organization with:
  - State: `power`, `resources`, `morale` (0.0–1.0)
  - Relations: dict of `faction_id → relationship` (-1.0 to 1.0)
  - Goals: list of strategic objectives
  - Traits: personality tags (e.g., "aggressive", "diplomatic")
  - Influence: dict of `location_id → control` (0.0–1.0)
- Methods: `set_relation()`, `get_relation()`, `adjust_relation()`, `set_influence()`, `to_dict()`

**`FactionSystem`**
- Simulates faction dynamics: resources, morale, conflicts, alliances
- Core method: `update()` → returns emergent event list
  - Phase 1: Update individual faction state (resources → morale → power)
  - Phase 2: Detect inter-faction events (conflicts, alliances, power shifts)
- Event types generated:
  - `"faction_conflict"`: Relations below -0.6 threshold
  - `"faction_alliance"`: Relations above 0.6 threshold
  - `"faction_rising"`: Power > 0.8
  - `"faction_declining"`: Power < 0.2
- Methods: `add_faction()`, `remove_faction()`, `get_faction()`, `get_summary()`, `reset()`

#### Constants
| Constant | Value | Purpose |
|----------|-------|---------|
| `CONFLICT_THRESHOLD` | -0.6 | Relations below this trigger conflict |
| `RESOURCE_GROWTH_RATE` | 0.01 | Per-tick resource growth (scaled by power) |
| `MORALE_ADJUSTMENT_RATE` | 0.05 | Morale change rate (scaled by resource delta) |

---

### 2. `src/app/rpg/world/reputation_engine.py`
**New file** — Per-faction reputation tracking and attitude classification.

#### Classes Added

**`FactionStanding`** (dataclass)
- Tracks reputation details for a single faction:
  - `reputation`: Score (-1.0 to 1.0)
  - `history`: List of (action, delta, tick) tuples
  - `last_change_tick`: When reputation last changed
  - `locked`: If True, reputation cannot be modified

**`ReputationEngine`**
- Core methods:
  - `apply_action(action, effects, tick)` → Scans `effects["faction_rep"]` for changes
  - `get(faction_id)` → Returns current reputation (0.0 if unknown)
  - `get_attitude(faction_id)` → Returns attitude classification
  - `set()`, `lock()`, `unlock()`, `decay()`, `reset()`
- Query methods:
  - `get_top_factions(count)` → Highest reputation
  - `get_bottom_factions(count)` → Lowest reputation
  - `get_attitude_summary()` → All non-neutral attitudes
  - `has_interaction_with(faction_id)` → History check
  - `get_history(faction_id)` → Full change log

#### Attitude Thresholds
| Attitude | Reputation Range |
|----------|-----------------|
| hostile | rep < -0.5 |
| unfriendly | -0.5 ≤ rep < 0.0 |
| neutral | 0.0 ≤ rep < 0.3 |
| friendly | 0.3 ≤ rep < 0.6 |
| ally | rep ≥ 0.6 |

---

## Files Modified

### 3. `src/app/rpg/world/__init__.py`

**Added exports:**
```python
from rpg.world.faction_system import Faction, FactionSystem
from rpg.world.reputation_engine import ReputationEngine, FactionStanding

__all__ = [
    "WorldState", "ResourcePool", "ResourceManager",
    "Faction", "FactionSystem",
    "ReputationEngine", "FactionStanding",
]
```

### 4. `src/app/rpg/core/player_loop.py`

**Added imports:**
```python
from rpg.world.faction_system import FactionSystem
from rpg.world.reputation_engine import ReputationEngine
```

**Constructor changes:**
- Added `faction_system` parameter (defaults to new `FactionSystem()`)
- Added `reputation_engine` parameter (defaults to new `ReputationEngine()`)

**Step pipeline changes (in `step()`):**
1. Record player agency (existing)
2. **NEW:** Apply reputation changes from action
3. Run world simulation tick (existing)
4. Plot engine update (existing)
5. **NEW:** Faction simulation tick → extends world_events
6. **NEW:** Update faction relations based on player reputation
7. Convert to narrative events (existing)
8. ...rest of pipeline unchanged

**Reset changes:**
- Added `self.factions.reset()` and `self.reputation.reset()`

**New method:**
- `_update_faction_relations()`: Updates faction relations based on player reputation
  - High rep with faction improves relations with faction's allies
  - Low rep hurts faction morale

---

## Tests Created

### 5. `src/tests/unit/rpg/test_faction_system.py`
**28 tests** covering:

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestFaction` | 6 | Creation, relations, influence, serialization |
| `TestFactionSystem` | 4 | Add/remove/get factions |
| `TestFactionConflictDetection` | 5 | Conflict/alliance detection, dedup, importance scaling |
| `TestFacterResourceUpdates` | 6 | Resources, morale, power updates, clamping |
| `TestPowerShiftDetection` | 3 | Rising/declining/mid-power detection |
| `TestFactionSystemSummary` | 2 | Summary, reset |
| `TestFactionWorldEvolution` | 2 | 100-tick conflict generation, alliance stability |

### 6. `src/tests/unit/rpg/test_reputation_engine.py`
**34 tests** covering:

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestFactionStanding` | 2 | Defaults, serialization |
| `TestReputationEngine` | 11 | Apply action, set, clamping, history, locking |
| `TestAttitudeClassification` | 7 | All 5 attitudes, boundary values, unknown faction |
| `TestReputationLocking` | 3 | Lock prevents changes, unlock allows, lock creates |
| `TestReputationDecay` | 5 | Positive/negative decay, locked, disabled, near-zero |
| `TestReputationQueries` | 4 | Top/bottom factions, summary, history |
| `TestReputationEngineReset` | 1 | Full reset |
| `TestReputationIntegration` | 1 | Attitude shifts over time |

---

## Integration Architecture

```
Player Action
     ├─→ AgencySystem.record() (TIER 6)
     └─→ ReputationEngine.apply_action()
              └─→ Updates per-faction reputation

PlayerLoop.step():
     1. Convert player input → world event
     2. Run world simulation tick
     3. Agency.record() — TIER 6
     4. Reputation.apply_action() — TIER 7 (NEW)
     5. PlotEngine.update() — TIER 6
     6. FactionSystem.update() — TIER 7 (NEW)
          └─→ Extends world_events with:
              • faction_conflict events
              • faction_alliance events
              • faction_rising/declining events
     7. _update_faction_relations() — TIER 7 (NEW)
     8. Convert to narrative events
     9. Generate narration
```

---

## Test Results

```
src/tests/unit/rpg/test_faction_system.py — 28 passed
src/tests/unit/rpg/test_reputation_engine.py — 34 passed
Total: 62 tests, all passing
```

---

## Design Compliance

| Design Spec | Implementation | Status |
|-------------|---------------|--------|
| `class Faction` with id, name, power, resources, morale, relations, goals, traits, influence | `Faction` dataclass with all fields | ✅ |
| `class FactionSystem` with add_faction, update, resource/morale/conflict methods | Full implementation with extra features | ✅ |
| `class ReputationEngine` with apply_action, get, get_attitude | Full implementation with decay and locking | ✅ |
| PlayerLoop integration with factions and reputation | Step pipeline updated | ✅ |
| Conflict generation when relations < -0.6 | Implemented with importance scaling | ✅ |
| 100-tick faction world evolution test | Implemented and passing | ✅ |

---

## Summary of Changes by Type

| Type | Count | Files |
|------|-------|-------|
| New modules | 2 | faction_system.py, reputation_engine.py |
| Modified modules | 2 | __init__.py, player_loop.py |
| New tests | 2 | test_faction_system.py, test_reputation_engine.py |
| **Total lines added** | ~1,200 | Implementation + Tests |