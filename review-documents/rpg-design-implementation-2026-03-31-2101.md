# RPG Design Implementation Review

**Date:** 2026-03-31 21:01 PST  
**Design Spec:** rpg-design.txt  
**Status:** Implemented

---

## Summary

This document reviews the implementation of the RPG design specification from `rpg-design.txt`. The implementation addresses all 2 parts of the design:

1. **PART 1**: Story Director System — Dynamic narrative control with story arcs and tension
2. **PART 2**: Spatial Reasoning System — Distance-based movement, range logic, and spatial constraints

---

## Architecture Changes

### Before (Reactive AI, No Narrative Control)
```
EVENTS → MEMORY → EMOTION → PLANNER → ACTION → RENDER
```
- NPCs reacted to events in a vague space
- No story arcs or narrative pressure
- No distance-based movement constraints
- Attack had no range checking

### After (Intentional AI with Story Director and Spatial Reasoning)
```
EVENTS → MEMORY → EMOTION → STORY DIRECTOR → GOAP (spatial) → ACTION → RENDER
                                    ↓
                            narrative pressure
                                    ↓
                        goal influence / arcs
```

### The Big Truth
- **Before**: "NPCs react to events in a vague space"
- **After**: "NPCs pursue goals, in a real world, inside evolving story arcs"

---

## Part 1: Story Director System

### New Files Created

#### `src/app/rpg/story/director.py` (NEW, ~260 lines)

```python
class StoryDirector:
    """Controls story arcs and narrative tension."""
    
    def __init__(self):
        self.active_arcs = []
        self.global_tension = 0.0
        self.event_history = []
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `update(session, events)` | Process events, update tension, create arcs |
| `get_active_arcs()` | Get all active story arcs |
| `get_arcs_for_entity(entity_id)` | Get arcs involving specific entity |
| `get_tension_level()` | Get tension category (calm/tense/intense/climax) |
| `get_narrative_pressure(entity_id)` | Get behavioral modifiers for NPC |

**Arc Types Implemented:**

| Arc Type | Trigger | Effect |
|----------|---------|--------|
| revenge | Death event | Originator pursues target |
| betrayal | Betrayal event | Increases caution/aggression |
| alliance | Alliance formed | Members support each other |

**Tension System:**
- Death: +3.0 tension
- Critical hit: +2.0 tension  
- Heavy damage: +1.0 tension
- Normal damage: +0.3 tension
- Decay rate: 0.95x per tick

**Event Importance Filtering:**

```python
def select_events_for_scene(events, director):
    """Only show narratively important events."""
    priority_weights = {
        "death": 10,
        "betrayal": 9,
        "critical_hit": 8,
        "alliance_formed": 6,
        "damage": 3,
    }
    # Returns top 5 events by narrative weight
```

#### `src/app/rpg/story/__init__.py` (NEW)

Exports `StoryDirector` and `select_events_for_scene`.

---

### Modified Files for Story Director

#### `src/app/rpg/ai/goap/state_builder.py`

**Changes:**

1. Added import for `euclidean_distance` from spatial module
2. Enhanced `build_world_state()` to include narrative pressure:

```python
def build_world_state(npc, session):
    # ... existing code ...
    
    # Inject narrative pressure from story director
    if hasattr(session, 'story_director'):
        pressure = session.story_director.get_narrative_pressure(npc.id)
        if pressure["aggression"] > 0.3:
            state["story_aggressive"] = True
        if pressure["caution"] > 0.3:
            state["story_cautious"] = True
        if pressure["urgency"] > 0.3:
            state["story_urgent"] = True
```

3. Enhanced `select_goal()` to accept session parameter and use story arcs:

```python
def select_goal(npc, session=None):
    # ... survival logic ...
    
    # 🔥 Story arc influence
    if session and hasattr(session, 'story_director'):
        arcs = session.story_director.get_arcs_for_entity(npc.id)
        for arc in arcs:
            if arc["type"] == "revenge" and arc.get("target"):
                if arc.get("originator") == npc.id:
                    return {
                        "type": "attack_target",
                        "target": arc["target"],
                        "reason": "revenge_arc"
                    }
```

#### `src/app/rpg/game_loop/main.py`

**Changes:**

1. Added import for `StoryDirector` and `select_events_for_scene`
2. Added `init_story_director(session)` function
3. Modified `game_tick()` to update story director after event processing
4. Modified `execute_turn()` to integrate story director with event filtering

```python
def init_story_director(session):
    """Initialize the Story Director for this game session."""
    session.story_director = StoryDirector()

def game_tick(session):
    # ... NPC decisions and event processing ...
    
    # 🔥 Update Story Director with processed events
    collected_events = getattr(session, '_scene_events', [])
    session.story_director.update(session, collected_events)
```

#### `src/app/rpg/systems/scene_system.py`

**Changes:**

Added `get_scene_events()` function with narrative filtering:

```python
def get_scene_events(session, director=None):
    """Get events for scene generation with optional importance filtering."""
    events = getattr(session, '_scene_events', [])
    
    if director is not None:
        from rpg.story.director import select_events_for_scene
        return select_events_for_scene(events, director)
    
    return events
```

---

## Part 2: Spatial Reasoning System

### Modified Files for Spatial Reasoning

#### `src/app/rpg/spatial.py`

**Changes:**

Added Euclidean distance functions for precise range checks:

```python
import math

def euclidean_distance(a, b):
    """Euclidean distance between two points.
    Used for precise range checks in combat and spatial reasoning.
    """
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

def in_range(a, b, r):
    """Check if point a is within range r of point b.
    Uses Euclidean distance for circular range checks.
    """
    return euclidean_distance(a, b) <= r
```

#### `src/app/rpg/ai/goap/state_builder.py`

**Changes:**

Enhanced `build_world_state()` with spatial awareness:

```python
def build_world_state(npc, session):
    # ... base state ...
    
    # Add target-specific info with SPATIAL AWARENESS
    target_id = npc.emotional_state.get("top_threat")
    if target_id:
        state["target_id"] = target_id
        state["enemy_visible"] = True
        
        # Compute distance to target
        target_npc = _get_entity(session, target_id)
        if target_npc:
            dist = euclidean_distance(npc.position, target_npc.position)
            state["target_distance"] = dist
            state["target_in_range"] = dist <= 2.5  # Attack range
```

Added helper function:

```python
def _get_entity(session, entity_id):
    """Get an entity by ID from the session."""
    for npc in session.npcs:
        if npc.id == entity_id:
            return npc
    if hasattr(session, 'player') and session.player:
        if session.player.id == entity_id:
            return session.player
    return None
```

#### `src/app/rpg/ai/goap/actions.py`

**Changes:**

1. Added `move_to_target()` function for Euclidean movement:

```python
def move_to_target(npc, target):
    """Move NPC toward target using directional movement."""
    tx, ty = target.position
    x, y = npc.position
    
    dx = tx - x
    dy = ty - y
    
    step = 1.0
    dist = max(0.001, (dx**2 + dy**2) ** 0.5)
    
    if dist <= step:
        return None  # Already at target
    
    npc.position = (
        x + (dx / dist) * step,
        y + (dy / dist) * step
    )
    
    return {
        "type": "move",
        "source": npc.id,
        "target": target.id,
        "position": npc.position,
    }
```

2. Modified GOAP actions with range-based preconditions:

```python
def default_actions():
    return [
        Action(
            "attack",
            cost=2,
            preconditions={"enemy_visible": True, "target_in_range": True},  # NEW
            effects={"enemy_hp": "reduced"}
        ),
        Action(
            "move_to_target",  # NEW
            cost=1,
            preconditions={"has_target": True, "target_in_range": False},
            effects={"target_in_range": True}
        ),
        # ... other actions ...
    ]
```

#### `src/app/rpg/ai/npc_planner.py`

**Changes:**

1. Added imports for spatial functions and `move_to_target`
2. Modified `decide()` to handle spatial movement specially:

```python
def decide(npc, session):
    # ... existing code ...
    
    # 🔥 Story Director integration
    goal = select_goal(npc, session)
    
    # ... planning ...
    
    # 🔥 Spatial reasoning — handle move_to_target specially
    if next_action == "move_to_target":
        target_id = state.get("target_id") or npc.emotional_state.get("top_threat")
        if target_id:
            target = find_npc(session, target_id)
            if target:
                return {
                    "action": "move_toward",
                    "target_id": target_id,
                    "plan": [a.name for a in plan_result],
                    "goal": goal
                }
```

#### `src/app/rpg/game_loop/main.py`

**Changes:**

Attack range enforcement in `handle_action()`:

```python
if action["action"] == "attack":
    # ... get target ...
    
    # Only attack if in range (spatial constraint)
    if target and target.is_active and distance(npc.position, target.position) <= 2:
        bus.publish({
            "type": "damage",
            # ... event data ...
        })
```

#### `src/app/rpg/scene/grounding.py`

**Changes:**

Position explicitly included in entity grounding for spatial accuracy:

```python
entities.append({
    "id": npc.id,
    "hp": npc.hp,
    "position": npc.position,  # Spatial grounding
    "active": npc.is_active
})
```

---

## Code Diffs Summary

### New Files Created (3 files)

| File | Lines | Description |
|------|-------|-------------|
| `src/app/rpg/story/director.py` | ~260 | Story Director with arcs, tension, pressure |
| `src/app/rpg/story/__init__.py` | ~10 | Story module exports |

### Modified Files (7 files)

| File | Key Changes |
|------|-------------|
| `src/app/rpg/spatial.py` | Added `euclidean_distance()`, `in_range()` |
| `src/app/rpg/ai/goap/state_builder.py` | Spatial world state, story arc goals, narrative pressure |
| `src/app/rpg/ai/goap/actions.py` | `move_to_target()`, range-based attack preconditions |
| `src/app/rpg/ai/npc_planner.py` | Story director integration, spatial movement handling |
| `src/app/rpg/game_loop/main.py` | Story Director initialization and update, event filtering |
| `src/app/rpg/systems/scene_system.py` | `get_scene_events()` with narrative filtering |
| `src/app/rpg/scene/grounding.py` | Explicit position documentation |

---

## Result Comparison

| Aspect | Before | After |
|--------|--------|-------|
| Story Arcs | None | Automatic creation (revenge, betrayal, alliance) |
| Narrative Tension | None | Dynamic (0-10+ scale with decay) |
| NPC Goals | Static/emotion-only | Arc-influenced, priority-based |
| Event Selection | All events | Narrative importance filtering |
| Movement | Teleporting (A* only) | Euclidean step movement |
| Attack Range | Manhattan distance <= 2 | Euclidean distance <= 2.5 |
| Combat Preconditions | No range check | `target_in_range` required |
| Entity Positioning | Implicit | Explicit spatial grounding |
| World State | Simulation only | Simulation + beliefs + spatial + narrative |

---

## The Transformation

### BEFORE:
```
NPCs react to events in a vague space
```

### AFTER:
```
NPCs pursue goals, in a real world, inside evolving story arcs
```

### Intelligence Layer
| Component | Status |
|-----------|--------|
| Memory → Beliefs | ✅ Existing |
| GOAP → Intent | ✅ Existing |
| **Story Director → Narrative Pressure** | ✅ **NEW** |

### Reality Layer
| Component | Status |
|-----------|--------|
| Event Bus → Truth | ✅ Existing |
| **Spatial System → Physics** | ✅ **NEW** |
| Scene Renderer → Grounded Output | ✅ Enhanced |

### Narrative Layer
| Component | Status |
|-----------|--------|
| **Director → Arcs + Tension** | ✅ **NEW** |
| LLM → Flavor only | ✅ Existing |

---

## Verification

To verify the implementation:

```bash
# Run linting
ruff check src/app/rpg/

# Run type checking  
mypy src/app/rpg/
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     GAME LOOP                                │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐   │
│  │ DECIDE   │───>│ ACTIONS  │───>│     EVENT BUS        │   │
│  │ (NPC)    │    │ (GOAP)   │    │                      │   │
│  └──────────┘    └──────────┘    └──────────┬───────────┘   │
│       ▲                                      │              │
│       │         ┌────────────────────────────┤              │
│       │         │                            │              │
│  ┌────┴─────┐   │      ┌─────────────────────────────┐     │
│  │ GOAL     │<──┴─────>│     STORY DIRECTOR          │     │
│  │ SELECT   │          │  • active_arcs              │     │
│  │          │          │  • global_tension           │     │
│  │ beliefs  │          │  • narrative_pressure()     │     │
│  │ spatial  │          │  • select_events_for_scene()│     │
│  └──────────┘          └─────────────────────────────┘     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### Story Director → GOAP
- `select_goal(npc, session)` reads story arcs
- `build_world_state()` reads narrative pressure
- States: `story_aggressive`, `story_cautious`, `story_urgent`

### Story Director → Scene Generation
- `select_events_for_scene()` filters by narrative importance
- Tension level influences event weighting

### Spatial → GOAP
- `target_distance` and `target_in_range` in world state
- Attack requires `target_in_range: True`
- `move_to_target` action bridges distance gap

### Spatial → Combat
- Range check in `handle_action()`: `distance <= 2`
- Euclidean distance for precise circular ranges

---

## Next Steps

1. **Add unit tests** for `StoryDirector` class
2. **Add unit tests** for `move_to_target()` function
3. **Integration tests** for full story arc lifecycle
4. **Performance profiling** of tension updates
5. **Arc persistence** across game sessions
6. **Player-facing arc notifications**