# TIER 9: Narrative Intelligence Layer - Implementation Review

**Date:** 2026-04-01 13:25  
**Status:** ✅ Complete  
**Design Source:** `rpg-design.txt` (TIER 9 section)

---

## Executive Summary

TIER 9 transforms the RPG from event-driven narrative into full cinematic storytelling:

| Before (Tier 8) | After (Tier 9) |
|-----------------|----------------|
| shortage → quest | shortage → crisis scene → starving city → NPC reactions → player choice → memory → future consequences → payoff arc |
| Isolated events | Connected scenes with stakes |
| State characters | Characters with beliefs, goals, memory |
| Raw event log | Token-efficient narrative memory |
| Immediate resolution | Long-term story arcs with payoff |
| Fragmented output | Unified narrative rendering |

---

## Systems Implemented

### 1. Scene Engine (Cinematic Layer)
**File:** `src/app/rpg/story/scene_engine.py`

**Purpose:** Convert raw world events into playable narrative scenes with dramatic stakes.

**Key Classes:**
- `Scene`: Dataclass representing a narrative scene (type, location, participants, stakes, resolution state)
- `SceneEngine`: Transforms events into scenes, manages active/historical scene lists

**Scene Types Supported:**
- `coup` → Leadership overthrow scenes
- `crisis` → Shortage/supply crisis scenes
- `battle` → Faction conflict scenes
- `dialogue` → Alliance/player action scenes
- `trade` → Economy/trade route scenes
- `generic` → Fallback for unknown event types

**Features:**
- Max active scene limit (default 20) with automatic history rotation
- Scene resolution tracking for narrative closure
- Stakes calculation based on event severity/importance
- Metadata preservation for downstream systems

---

### 2. Character Engine (Beliefs + Goals)
**File:** `src/app/rpg/character/character_engine.py`

**Purpose:** Track individual characters with dynamic beliefs, evolving goals, and event memory.

**Key Classes:**
- `Character`: Individual with belief map (entity→opinion), goals list, memory log
- `CharacterEngine`: Manages character lifecycle, processes events to update beliefs/goals

**Belief System:**
- Range: -1.0 (hostile) to 1.0 (supportive)
- Entities can be factions, locations, concepts, or other characters
- Updated automatically from world events

**Event-Driven Updates:**
- `coup` → Loser loses power belief, gains revenge goal; winner gains power belief
- `faction_conflict` → Faction sympathizers adjust hostility
- `faction_alliance` → Improved opinions between allied factions
- `shortage` → Characters develop help goals for afflicted locations
- `player_action` → Sentiment analysis adjusts player opinion

**Memory:** Per-character event memory with configurable capacity (default 50)

---

### 3. Narrative Memory System
**File:** `src/app/rpg/memory/narrative_memory.py`

**Purpose:** Token-efficient memory storage preventing context explosion while preserving story continuity.

**Key Class:** `NarrativeMemory`

**Architecture:**
1. **Importance Filter:** Only events with importance > 0.5 stored
2. **Raw Events:** Recent important events stored verbatim
3. **Summaries:** Older events compressed into narrative summaries
4. **Auto-Summarize:** Triggers when raw events exceed max_entries (default 100)

**Context Retrieval:**
- `get_context()` → Returns recent events (up to 20) + recent summaries (up to 5)
- Used by Narrative Renderer for prompt construction

**LLM Hook:** `_summarize()` and `_create_summary()` can be overridden for LLM-powered summarization

---

### 4. Story Arc / Payoff Engine
**File:** `src/app/rpg/story/story_arc_engine.py`

**Purpose:** Long-term narrative arcs with setup → payoff structure. Arcs complete when world state satisfies conditions.

**Key Classes:**
- `StoryArc`: Arc definition with setup description and payoff_condition callable
- `StoryArcEngine`: Monitors world state, detects arc completion

**Arc Lifecycle:**
1. **Registration:** Arc added with setup and payoff condition
2. **Monitoring:** Each tick, engine checks payoff_condition(world_state)
3. **Completion:** When condition met, arc generates payoff event
4. **Tracking:** Duration from creation to completion tracked

**Factory Functions:**
- `create_war_arc(factions, duration_threshold)` → War exhaustion arc
- `create_crisis_arc(location, good, severity_threshold)` → Crisis escalation arc
- `create_rising_power_arc(faction, power_threshold)` → Power consolidation arc

---

### 5. Narrative Renderer
**File:** `src/app/rpg/story/narrative_renderer.py`

**Purpose:** Unified narrative output combining all layers into LLM prompt-ready context.

**Key Class:** `NarrativeRenderer`

**Input Aggregation:**
- Active scenes with stakes and participants
- Character beliefs and active goals
- Memory summaries for continuity
- World state context

**Output Format:**
```json
{
  "scene_text": "Current scene descriptions",
  "memory_summary": "Historical summaries",
  "character_updates": "Character goal status",
  "world_context": "World state summary",
  "full_narrative": "Combined formatted narrative"
}
```

**Features:**
- Custom template support
- `render_for_prompt()` with max_length truncation
- Section-based formatting (scenes, history, characters, world)

---

## PlayerLoop Integration

**File Modified:** `src/app/rpg/core/player_loop.py`

### New Imports:
```python
from rpg.story.scene_engine import SceneEngine
from rpg.character.character_engine import CharacterEngine
from rpg.memory.narrative_memory import NarrativeMemory
from rpg.story.story_arc_engine import StoryArcEngine
from rpg.story.narrative_renderer import NarrativeRenderer
```

### New Constructor Parameters:
- `scene_engine`, `character_engine`, `narrative_memory`, `story_arc_engine`, `narrative_renderer`

### New Integration Points in `step()`:

**Pipeline Position (after Tier 8, before event conversion):**
```python
# TIER 9: Generate scenes from all events
scenes = self.scenes.generate_from_events(world_events)

# TIER 9: Update character beliefs from events
self.characters.update_from_events(world_events)

# TIER 9: Store events in narrative memory
self.memory.add_events(world_events)

# TIER 9: Check story arcs for completion
completed_arcs = self.story_arcs.update({"tick": self._tick})
world_events.extend(completed_arcs)
```

**Result Augmentation:**
```python
narrative = self.renderer.render(
    scenes=self.scenes.get_active_scenes(),
    memory=self.memory,
    characters=self.characters.characters,
    world_state=self._get_world_state_for_renderer(),
)

result = {
    ...
    "scenes": scenes,
    "narrative": narrative,
    "completed_arcs": completed_arcs,
}
```

### New Method: `_get_world_state_for_renderer()`
Provides renderer with current faction conflicts, shortages, and economy state.

### Reset Updated:
All TIER 9 systems reset in `PlayerLoop.reset()`.

---

## Tests Created

**File:** `src/tests/integration/test_tier9_narrative.py`

### Test Classes:

| Class | Coverage |
|-------|----------|
| `TestSceneEngine` | Scene generation from coup/crisis/battle events, resolution, max limit |
| `TestCharacterEngine` | Creation, beliefs, coup updates, goals, memory storage |
| `TestNarrativeMemory` | Importance filtering, summarization trigger, context retrieval |
| `TestStoryArcEngine` | Registration, completion, duration, factory functions |
| `TestNarrativeRenderer` | Scenes, memory, characters, empty state, truncation |
| `TestPlayerLoopIntegration` | Step returns scenes/narrative/arcs, memory growth, reset |
| `Test100TickNarrative` | 100-tick stability with single action and varied scenarios |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      PlayerLoop.step()                       │
│                                                              │
│  World Events ─────────────────────────────────────────┐     │
│       ↓                                                 │     │
│  ┌─────────────────────────────────────────────────┐    │     │
│  │ TIER 9: SceneEngine                             │    │     │
│  │ events → Scene[ coup, battle, crisis, trade ]   │    │     │
│  └─────────────────────────────────────────────────┘    │     │
│       ↓                                                 │     │
│  ┌─────────────────────────────────────────────────┐    │     │
│  │ TIER 9: CharacterEngine                        │    │     │
│  │ events → update beliefs, goals, memory          │    │     │
│  └─────────────────────────────────────────────────┘    │     │
│       ↓                                                 │     │
│  ┌─────────────────────────────────────────────────┐    │     │
│  │ TIER 9: NarrativeMemory                        │    │     │
│  │ events → filter(>0.5) → store → summarize       │    │     │
│  └─────────────────────────────────────────────────┘    │     │
│       ↓                                                 │     │
│  ┌─────────────────────────────────────────────────┐    │     │
│  │ TIER 9: StoryArcEngine                         │    │     │
│  │ world_state → check conditions → payoff events  │    │     │
│  └─────────────────────────────────────────────────┘    │     │
│       ↓                                                 │     │
│  ┌─────────────────────────────────────────────────┐    │     │
│  │ TIER 9: NarrativeRenderer                      │    │     │
│  │ scenes + memory + characters + world → output   │    │     │
│  └─────────────────────────────────────────────────┘    │     │
│                                                          │     │
│  Result: narration, scenes, narrative, completed_arcs   │     │
└─────────────────────────────────────────────────────────┘
```

---

## Files Created/Modified

### New Files (5):
| File | Lines | Description |
|------|-------|-------------|
| `src/app/rpg/story/scene_engine.py` | ~270 | Scene Engine - event-to-scene conversion |
| `src/app/rpg/character/__init__.py` | ~10 | Package init |
| `src/app/rpg/character/character_engine.py` | ~290 | Character Engine - beliefs, goals, memory |
| `src/app/rpg/memory/narrative_memory.py` | ~175 | Narrative Memory - importance filtering |
| `src/app/rpg/story/story_arc_engine.py` | ~280 | Story Arc Engine - setup→payoff |
| `src/app/rpg/story/narrative_renderer.py` | ~250 | Narrative Renderer - unified output |
| `src/tests/integration/test_tier9_narrative.py` | ~300 | Integration + 100-tick tests |

### Modified Files (1):
| File | Changes |
|------|---------|
| `src/app/rpg/core/player_loop.py` | +45 imports, +5 constructor params, +pipeline integration, +renderer hook |

---

## Design Spec Compliance

| Spec Requirement | Implementation | Status |
|-----------------|----------------|--------|
| Scene Engine with type classification | `SceneEngine` with 6 scene builders | ✅ |
| Scene stakes calculation | Severity/importance-based stakes | ✅ |
| Character beliefs (-1.0 to 1.0) | `Character.add_belief()/adjust_belief()` | ✅ |
| Character goals | `Character.add_goal()/remove_goal()` | ✅ |
| Character memory | `Character.add_memory()` with capacity limit | ✅ |
| Event-driven belief updates | `_handle_coup/conflict/alliance/shortage/player` | ✅ |
| Importance-filtered memory | `NarrativeMemory` filters > 0.5 | ✅ |
| Summarization | `_summarize()` compresses old events | ✅ |
| Story arc registration | `register_arc/register_arc_simple` | ✅ |
| Payoff condition checking | `update(world_state)` checks conditions | ✅ |
| Arc completion events | Returns payoff event dicts | ✅ |
| Narrative renderer | Combines all layers into output | ✅ |
| LLM prompt-ready output | `render()` + `render_for_prompt()` | ✅ |
| 100-tick test | `Test100TickNarrative.test_100_tick_narrative_stability` | ✅ |

---

## Summary

**Before TIER 9:** World events generated isolated quests. Characters were data containers. Story had no memory or structure.

**After TIER 9:** World events become cinematic scenes. Characters develop beliefs, pursue goals, and remember events. Important events are stored efficiently. Long-term story arcs create dramatic structure. Everything combines into rich, unified narrative output.

**The transformation is complete:** `shortage → crisis scene → starving city → NPC reactions → player choice → memory → future consequences → payoff arc`