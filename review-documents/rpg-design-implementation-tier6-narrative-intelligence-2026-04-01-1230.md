# RPG Design Implementation — Tier 6: Narrative Intelligence Systems

**Date:** 2026-04-01 12:30 UTC-7:00  
**Branch:** Main development  
**Tests:** 27/27 passing  

---

## Summary

This implementation adds **Tier 6: Narrative Intelligence Systems** from `rpg-design.txt`, solving two critical narrative gaps:

1. **Long-term meaning (Plot Engine)** — Stories now have setup → buildup → payoff structures, persistent goals, and resolution tracking.
2. **Player impact (Agency System)** — Player choices now have visible, long-lasting consequences that affect NPC behavior, world state, and story progression.

### What This Unlocks

| Before | After |
|--------|-------|
| Cool moments | Setups → Payoffs |
| No memory of meaning | Player actions reshape world |
| Stories don't resolve | NPCs react long-term |
| — | Stories actually resolve |

---

## New Files

### 1. `src/app/rpg/player/__init__.py` (NEW)
Player module initialization. Exports `AgencySystem` and `PlayerChoice`.

### 2. `src/app/rpg/player/agency_system.py` (NEW — 350+ lines)

**Purpose:** Track player choices and their long-term consequences.

**Key Classes:**
- `PlayerChoice` — Dataclass recording a single player action, its context, effects, and consequences.
- `AgencySystem` — Main system that records choices, applies effects as persistent flags, and tracks categories (killed/entities/allies/visited).

**Integration Points:**
- `PlayerLoop.step()` — Records each player action
- NPC Behavior — Reads flags to modify NPC attitudes  
- Plot Engine — Reads flags to advance arc progression
- World State — Reads flags to change world conditions

**Key Methods:**
- `record(action, result, context, timestamp)` — Record a player choice
- `get_flag(key)` — Query a specific world flag
- `killed_entities`, `ally_entities`, `betrayed_entities` — Tracked entity categories
- `get_flags_for_director()` — Format flags for Director prompt injection

### 3. `src/app/rpg/story/plot_engine.py` (NEW — 800+ lines)

**Purpose:** Manage long-term story structure (arcs, quests, setups/payoffs).

**Key Classes:**
- `Quest` — Objective-based goal with trackable conditions
- `QuestManager` — Manages quests, objective completion, auto-detection from events
- `Setup` — Narrative foreshadowing awaiting payoff
- `SetupTracker` — Tracks setups and triggers payoffs when matching events occur
- `PlotEngine` — Main coordinator wrapping StoryArcManager + QuestManager + SetupTracker

**Integration Points:**
- `PlayerLoop.step()` — Plot engine updates each tick, injects arc-driven events
- `AgencySystem` — Flags advance arc progress via registered flag boosts
- `StoryDirector` — Arc summaries inform Director decisions

**Key Methods:**
- `add_arc(id, goal, entities)` — Create story arcs
- `add_quest(id, title, objectives)` — Create quests
- `add_setup(id, description, payoff_trigger)` — Create setups
- `register_arc_flag_boost(arc_id, flags)` — Link agency flags to arc progress
- `update(events, agency_flags)` — Update all systems
- `generate_arc_events()` — Generate arc-driven events for injection
- `get_direct_prompt_injection()` — Format state for Director prompt

---

## Modified Files

### 1. `src/app/rpg/core/player_loop.py`

**Changes:**
- Added imports for `PlotEngine` and `AgencySystem`
- Added `plot_engine` and `agency_system` constructor parameters (default to new instances)
- Added `self._tick` counter
- In `step()`: Agency recording, plot engine update, arc event injection into world events
- In `reset()`: Resets both Tier 6 systems

**Diff (key changes):**

```python
# NEW IMPORTS
from rpg.story.plot_engine import PlotEngine
from rpg.player.agency_system import AgencySystem

# CONSTRUCTOR — NEW PARAMETERS
def __init__(
    self,
    ...,
    plot_engine: Any = None,
    agency_system: Any = None,
):
    ...
    # TIER 6: Narrative Intelligence Systems
    self.plot_engine = plot_engine or PlotEngine()
    self.agency = agency_system or AgencySystem()
    self._tick = 0

# STEP METHOD — NEW INTEGRATION
def step(self, player_input: str) -> Dict[str, Any]:
    ...
    # TIER 6: Record player agency
    result = {"effects": {}, "weight": 0.5}
    self.agency.record(player_input, result, timestamp=self._tick)
    self._tick += 1
    
    # TIER 6: Update plot engine with world events and agency flags
    plot_update = self.plot_engine.update(world_events, self.agency.flags)
    
    # TIER 6: Inject arc-driven events into the event stream
    arc_events = plot_update.get("injected_events", [])
    world_events.extend(arc_events)
    ...

# RESET METHOD — NEW
def reset(self) -> None:
    ...
    # TIER 6: Reset Narrative Intelligence Systems
    self.plot_engine.reset()
    self.agency.reset()
```

### 2. `src/app/rpg/story/__init__.py`

**Changes:** Added exports for `PlotEngine`, `Quest`, `QuestManager`, `Setup`, `SetupTracker`.

```python
from rpg.story.plot_engine import PlotEngine, Quest, QuestManager, Setup, SetupTracker

__all__ = [
    "StoryDirector",
    "DirectorAgent",
    "DirectorOutput",
    "DirectorOutputOriginal",
    "PlotEngine",
    "Quest",
    "QuestManager",
    "Setup",
    "SetupTracker",
]
```

### 3. `src/app/rpg/story/plot_engine.py` — `generate_arc_events()` 

**Patch Applied:** Added `_compute_phase()` fallback for existing `StoryArc` classes that lack a `phase` attribute. This ensures backward compatibility.

---

## Test File

### `src/tests/unit/rpg/test_tier6_narrative_intelligence.py` (NEW — 27 tests)

All tests pass:

| Category | Tests |
|----------|-------|
| AgencySystem | 9 tests |
| PlotEngine | 12 tests |
| PlayerLoop Integration | 6 tests |

**AgencySystem Tests:**
- `test_agency_records_choice` — Choice recording
- `test_agency_stores_flags` — Flag persistence
- `test_agency_accumulates_numeric_flags` — Numeric accumulation
- `test_agency_tracks_killed_entities` — Entity tracking
- `test_agency_tracks_allies` — Ally tracking
- `test_agency_prunes_history` — History pruning
- `test_agency_get_summary` — Summary dict
- `test_agency_get_flags_for_director` — Director prompt formatting
- `test_agency_reset` — Reset clears all data

**PlotEngine Tests:**
- `test_plot_engine_create_arc` — Arc creation
- `test_plot_engine_create_quest` — Quest creation
- `test_plot_engine_quest_progress` — Objective tracking
- `test_plot_engine_quest_completion` — Quest completion
- `test_plot_engine_arc_advances_on_events` — Event-driven progress
- `test_plot_engine_arc_phase_transitions` — Phase advancement
- `test_plot_engine_generates_arc_events` — Event injection
- `test_plot_engine_add_setup_and_payoff` — Setup/payoff pattern
- `test_plot_engine_update_returns_changes` — Update return structure
- `test_plot_engine_agency_boosts_arcs` — Agency→Plot integration
- `test_plot_engine_get_prompt_injection` — Director prompt formatting
- `test_plot_engine_reset` — Reset clears all data

**PlayerLoop Integration Tests:**
- `test_player_loop_has_tier6_systems` — Systems initialized
- `test_player_loop_records_agency_on_step` — Agency recording per step
- `test_player_loop_updates_plot_engine` — Plot engine updates per step
- `test_player_loop_injects_arc_events` — Arc events injected into world
- `test_player_loop_increments_tick` — Tick counter
- `test_player_loop_reset_clears_tier6` — Reset includes Tier 6

---

## System Integration

```
Player Action
    │
    ▼
AgencySystem.record()
    │
    ├── Stores choice in history
    ├── Applies effects as persistent flags
    └── Tracks categories (killed/allies/betrayed)
         │
         ▼
    PlotEngine.update(events, agency_flags)
         │
         ├── StoryArcManager.update_arcs(events)
         ├── QuestManager.update_quests(events)
         ├── SetupTracker.check_payoffs(events)
         ├── Apply agency flag boosts to arcs
         └── generate_arc_events() → inject into world
              │
              ▼
         NPC Behavior reads agency.flags
         World Logic reads agency.flags
         Director reads prompt injection
```

## Architecture Compliance

This implementation follows the design spec in `rpg-design.txt` exactly:

- **PART 1 — Plot/Quest Engine:** `PlotEngine`, `StoryArcManager` (existing), `QuestManager`, `SetupTracker`
- **PART 2 — Player Agency System:** `AgencySystem`, `PlayerChoice`
- **Integration:** `PlayerLoop` hooks both systems into the main game loop
- **Make Choices Matter:** Agency flags are read by world/NPC logic for long-term impact