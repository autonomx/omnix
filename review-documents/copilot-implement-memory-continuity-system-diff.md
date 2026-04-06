# Code Diff Document: Memory Continuity System Implementation

**Branch:** `copilot/implement-memory-continuity-system`  
**Merged via:** PR #94 (commit `aff5da0`)  
**Base Commit:** `aff5da0^` (parent before merge)  
**Branch Tip:** `83aafbc` — "Phase 13-23: Social sim, Director, Encounter, Inventory, Travel, Quest, GM tools, Save, Performance, UX, Narrative systems with 130 tests"  
**Date:** April 2026  
**Total Changes:** 18 files, 8,147 insertions, 0 deletions (all new files)

---

## Summary of Changes

The branch introduces two major new subsystems (Phase 11 & 12) plus eleven additional RPG systems (Phases 13-23), along with comprehensive unit tests. All files are new additions — no existing code was modified.

### Files Added

| File | Lines | Category |
|------|-------|----------|
| `src/app/rpg/core/performance.py` | 283 | Core |
| `src/app/rpg/creator/gm_tools.py` | 317 | Creator/GM |
| `src/app/rpg/director/director_integration.py` | 419 | Director |
| `src/app/rpg/encounter/tactical_mode.py` | 536 | Encounter |
| `src/app/rpg/items/economy.py` | 445 | Items/Economy |
| `src/app/rpg/memory/continuity.py` | 629 | Memory (Phase 11) |
| `src/app/rpg/narrative/emergent_endgame.py` | 402 | Narrative |
| `src/app/rpg/persistence/save_packaging.py` | 316 | Persistence |
| `src/app/rpg/planning/__init__.py` | 1 | Planning (Phase 12) |
| `src/app/rpg/planning/intent_system.py` | 701 | Planning (Phase 12) |
| `src/app/rpg/quest/quest_deepening.py` | 497 | Quest System |
| `src/app/rpg/social/social_sim_v2.py` | 553 | Social Simulation |
| `src/app/rpg/travel/__init__.py` | 2 | Travel |
| `src/app/rpg/travel/travel_system.py` | 405 | Travel |
| `src/app/rpg/ux/production_polish.py` | 286 | UX |
| `src/tests/unit/rpg/test_phase11_memory_continuity.py` | 651 | Tests (Phase 11) |
| `src/tests/unit/rpg/test_phase12_planning_intent.py` | 603 | Tests (Phase 12) |
| `src/tests/unit/rpg/test_phase13_23_systems.py` | 1,101 | Tests (Phases 13-23) |

---

## Detailed File-by-File Analysis

### 1. `src/app/rpg/memory/continuity.py` (629 lines)

**Purpose:** Unified memory continuity system providing bounded, deterministic memory management for RPG NPCs.

#### Key Classes:

| Class | Responsibility |
|-------|---------------|
| `MemoryState` | Top-level bounded memory state container with `tick`, `short_term`, `long_term`, `world_memories`, `rumor_memories`. Enforces serialisation via `to_dict()` / `from_dict()`. |
| `ConversationMemory` | Bounded short-term dialogue memory. `MAX_TURNS = 20`, `DECAY_WINDOW = 10` ticks. Methods: `add_turn()`, `get_recent()`, `decay()`. |
| `ActorMemory` | Per-actor long-term memory with salience scoring. `MAX_ENTRIES = 200`. Methods: `record_event()`, `get_actor_memories()`, `get_all_actors()`, `decay()`. |
| `WorldMemory` | Shared world events and rumor tracking. `MAX_WORLD = 50`, `MAX_RUMORS = 30`. Methods: `record_world_event()`, `record_rumor()`, `get_world_events()`, `get_active_rumors()`, `decay_rumors()`. |
| `MemoryCompressor` | Importance-based memory compression. Static methods: `compress_short_term()`, `compress_long_term()`, `compress_world()`. |
| `DialogueMemoryRetriever` | Retrieves memories relevant to a dialogue exchange using a scoring algorithm (speaker identity, topic matching, recency decay). |
| `MemoryInfluenceEngine` | Computes how memory affects NPC decision-making. Outputs `trust_modifier`, `fear_modifier`, `suggested_intent`, `memory_tags`. |
| `MemoryInspector` | Debug inspection tools: `inspect_memory_state()`, `inspect_actor_memory()`, `inspect_world_memory()`, `get_memory_statistics()`. |
| `MemoryDeterminismValidator` | Validates memory determinism and bounds. Methods: `validate_determinism()`, `validate_bounds()`, `normalize_state()`. |
| `MemoryContinuitySystem` | Unified facade over all Phase-11 sub-systems. |

#### Constants:
```python
MAX_SHORT_TERM = 20
MAX_LONG_TERM = 200
MAX_WORLD_PER_ENTITY = 50
MAX_RUMORS = 30
```

#### Design Patterns:
- **Facade Pattern:** `MemoryContinuitySystem` provides a single entry point to all 8 sub-systems.
- **Strategy Pattern:** Different compression strategies for short-term, long-term, and world memory.
- **Bounds Enforcement:** All collections are strictly bounded; `normalize_state()` clamps all values.
- **Data Class Pattern:** `MemoryState` uses `@dataclass` with serialization support.

---

### 2. `src/app/rpg/planning/intent_system.py` (701 lines)

**Purpose:** Goal generation, multi-step plan construction, execution, interruption, companion planning, faction coordination.

#### Key Classes:

| Class | Responsibility |
|-------|---------------|
| `GoalState` | Goal definition with `goal_id`, `actor_id`, `goal_type`, `priority`, `status`, `progress`, `deadline_tick`. |
| `PlanStep` | Individual plan step with `action_type`, `target_id`, `preconditions`, `expected_outcome`, `status`. |
| `Plan` | Multi-step plan with plan ID, goal reference, list of steps, status. |
| `IntentState` | Per-actor intent state with `active_goals` (max 5), `completed_goals` (max 20), `plan_cache`. |
| `PlanningSystemState` | Top-level planning state: per-actor intents, global objectives, tick counter. |
| `GoalGenerator` | Generates goals from beliefs and world context. Goal types: `neutralize`, `protect`, `survive`, `acquire`. |
| `PlanBuilder` | Builds multi-step plans from goals using templates. `MAX_PLAN_STEPS = 5`. |
| `PlanExecutor` | Step-by-step plan execution: `get_current_step()`, `advance_step()`, `is_plan_complete()`, `get_plan_action()`. |
| `PlanInterruptHandler` | Handles plan interruptions (threat, opportunity, ally danger, blocked path). Detects when replanning is needed. |
| `CompanionPlanner` | Generates companion plans aligned with the leader's plan. Companion actions: `support_attack`, `cover_ally`, `cover_retreat`, `scout_ahead`. |
| `FactionIntentCoordinator` | Coordinates faction member plans to avoid conflicts, assigns primary/flank roles. |
| `PlannerInspector` | Debug inspection: `inspect_actor_plans()`, `inspect_plan_timeline()`, `get_planning_statistics()`. |
| `PlanningDeterminismValidator` | Validates determinism and bounds, normalizes state. |

#### Constants:
```python
MAX_ACTIVE_GOALS = 5
MAX_COMPLETED_GOALS = 20
MAX_PLAN_STEPS = 5
MAX_GLOBAL_OBJECTIVES = 10
GOAL_TYPES = {"neutralize", "protect", "survive", "acquire", "explore", "negotiate"}
INTERRUPT_TYPES = {"threat_detected", "goal_invalidated", "better_opportunity", "ally_in_danger", "plan_blocked"}
```

#### Goal Plan Templates:
| Goal Type | Steps |
|-----------|-------|
| `neutralize` | approach → engage → resolve |
| `protect` | move_to → guard → alert |
| `survive` | assess → retreat_or_defend → recover |
| `acquire` | locate → obtain → secure |

---

### 3. `src/app/rpg/core/performance.py` (283 lines)

**Purpose:** Performance optimization utilities for the RPG system.

#### Key Features:
- Performance profiling and metrics collection
- Tick timing and budget management
- Resource usage tracking (memory, CPU)
- Performance optimization flags and thresholds
- Integration with game loop for timing control

---

### 4. `src/app/rpg/creator/gm_tools.py` (317 lines)

**Purpose:** GM (Game Master) tools for world manipulation and scene control.

#### Key Features:
- GM state management for world manipulation
- Scene generation controls
- NPC behavior overrides
- World event triggers
- Debug utilities for content creators

---

### 5. `src/app/rpg/director/director_integration.py` (419 lines)

**Purpose:** Integration layer for the narrative director system.

#### Key Features:
- Director hooks for narrative pacing
- Scene management integration
- Emergent story detection
- Narrative tension tracking
- Pacing controller integration

---

### 6. `src/app/rpg/encounter/tactical_mode.py` (536 lines)

**Purpose:** Tactical encounter mode with initiative, positioning, and combat actions.

#### Key Features:
- Initiative tracking
- Turn-based encounter management
- Tactical positioning system
- Combat action resolution
- Encounter state serialization

---

### 7. `src/app/rpg/items/economy.py` (445 lines)

**Purpose:** In-game economy system with pricing, trade, and market dynamics.

#### Key Features:
- Item valuation engine
- Trade resolution
- Market price fluctuation
- Merchant behavior
- Economic simulation

---

### 8. `src/app/rpg/narrative/emergent_endgame.py` (402 lines)

**Purpose:** Emergent endgame narrative generation based on accumulated world state.

#### Key Features:
- Endgame condition detection
- Narrative conclusion generators
- World state evaluation for ending types
- Multiple ending path tracking
- Legacy and epilogue generation

---

### 9. `src/app/rpg/persistence/save_packaging.py` (316 lines)

**Purpose:** Save game packaging and serialization utilities.

#### Key Features:
- Save game compression
- State snapshot packaging
- Save version management
- Cross-session state persistence
- Save integrity validation

---

### 10. `src/app/rpg/quest/quest_deepening.py` (497 lines)

**Purpose:** Quest deepening system with branching narratives and consequence tracking.

#### Key Features:
- Quest branching logic
- Consequence propagation
- Quest state deepening
- Narrative reward generation
- Quest relationship tracking

---

### 11. `src/app/rpg/social/social_sim_v2.py` (553 lines)

**Purpose:** Social simulation v2 with reputation, relationships, and faction dynamics.

#### Key Features:
- Reputation graph management
- Relationship tracking
- Faction allegiance tracking
- Social event propagation
- Group decision simulation

---

### 12. `src/app/rpg/travel/travel_system.py` (405 lines)

**Purpose:** Travel system with journey simulation and pathfinding.

#### Key Features:
- Journey planning
- Travel time calculation
- Path finding integration
- Travel event generation
- Rest and recovery during travel

---

### 13. `src/app/rpg/ux/production_polish.py` (286 lines)

**Purpose:** UX production polish with UI state management and presentation helpers.

#### Key Features:
- UI state management
- Presentation layer adapters
- UI transition helpers
- Display formatting
- Accessibility support

---

### 14. Tests (2,355 lines total)

#### `test_phase11_memory_continuity.py` (651 lines)
- Tests for `MemoryState`, `ConversationMemory`, `ActorMemory`, `WorldMemory`
- Tests for `MemoryCompressor`, `DialogueMemoryRetriever`, `MemoryInfluenceEngine`
- Tests for `MemoryInspector`, `MemoryDeterminismValidator`, `MemoryContinuitySystem`
- Validates bounds enforcement, serialization, determinism

#### `test_phase12_planning_intent.py` (603 lines)
- Tests for `GoalState`, `PlanStep`, `Plan`, `IntentState`
- Tests for `GoalGenerator`, `PlanBuilder`, `PlanExecutor`
- Tests for `PlanInterruptHandler`, `CompanionPlanner`, `FactionIntentCoordinator`
- Tests for `PlanningDeterminismValidator`

#### `test_phase13_23_systems.py` (1,101 lines)
- Integration tests for all 13 system modules (Phase 13-23)
- Validates module integration points
- Tests serialization roundtrips
- Validates deterministic behavior across systems

---

## Architecture Overview

```
copilot/implement-memory-continuity-system/
├── src/app/rpg/
│   ├── core/
│   │   └── performance.py           # Performance optimization
│   ├── creator/
│   │   └── gm_tools.py             # GM tools
│   ├── director/
│   │   └── director_integration.py # Director integration
│   ├── encounter/
│   │   └── tactical_mode.py        # Tactical encounters
│   ├── items/
│   │   └── economy.py             # Economy system
│   ├── memory/
│   │   └── continuity.py          # Phase 11: Memory continuity
│   ├── narrative/
│   │   └── emergent_endgame.py    # Emergent endgame
│   ├── persistence/
│   │   └── save_packaging.py      # Save packaging
│   ├── planning/
│   │   ├── __init__.py            # Phase 12 package
│   │   └── intent_system.py       # Planning/intent system
│   ├── quest/
│   │   └── quest_deepening.py     # Quest deepening
│   ├── social/
│   │   └── social_sim_v2.py       # Social simulation
│   ├── travel/
│   │   ├── __init__.py            # Travel package
│   │   └── travel_system.py       # Travel system
│   └── ux/
│       └── production_polish.py   # UX polish
└── src/tests/unit/rpg/
    ├── test_phase11_memory_continuity.py   # Phase 11 tests
    ├── test_phase12_planning_intent.py     # Phase 12 tests
    └── test_phase13_23_systems.py          # Phase 13-23 tests
```

---

## Data Flow

### Memory Continuity System (Phase 11)

```
Dialogue Turn → ConversationMemory.add_turn() → Short-term memory (bounded)
                    ↓ (decay + compression)
Actor Event → ActorMemory.record_event() → Long-term memory (bounded)
                    ↓
World Event → WorldMemory.record_world_event() → World/rumor memory (bounded)
                    ↓
Dialogue Request → DialogueMemoryRetriever.retrieve_for_dialogue() → Scored memories
                    ↓
NPC Decision → MemoryInfluenceEngine.compute_memory_influence() → Trust/fear modifiers → Suggested intent
```

### Planning/Intent System (Phase 12)

```
Beliefs + Memory → GoalGenerator.generate_goals() → Bounded goals (max 5 active)
                    ↓
Goal → PlanBuilder.build_plan() → Multi-step plan (max 5 steps)
                    ↓
Plan → PlanExecutor.advance_step() → Step execution → Outcome
                    ↓
Events → PlanInterruptHandler.check_interrupts() → Replan if critical interrupt
                    ↓
Leader Plan → CompanionPlanner.generate_companion_plan() → Aligned companion plan
                    ↓
Member Plans → FactionIntentCoordinator.coordinate_faction_plans() → Coordinated assignments
```

---

## Key Design Decisions

1. **All New Files:** The branch added 18 new files with no modifications to existing code, minimizing merge risk.
2. **Bounded State:** Every collection has strict maximum sizes enforced at insertion time.
3. **Determinism First:** Every subsystem includes a determinism validator and state normalizer.
4. **Facade Pattern:** Both major systems use a unified facade for simplified integration.
5. **Serialization Built-In:** All state classes have `to_dict()` / `from_dict()` for save/load.
6. **Test Coverage:** 2,355 lines of tests across 3 test files, covering all public APIs.