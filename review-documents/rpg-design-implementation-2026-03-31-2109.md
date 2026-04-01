# RPG Design Implementation Review — Critical Gaps Filled

**Date:** 2026-03-31 21:09 PST  
**Design Spec:** rpg-design.txt  
**Status:** Critical Gaps Implemented

---

## Summary

This document reviews the implementation of critical gaps identified in the RPG design. Seven major gaps have been addressed:

1. ✅ **Story Director Authoritative Control** — Arc phases, forced goals, mandated behavior
2. ✅ **Persistent Narrative State** — Phase transitions (build → tension → climax → resolution)
3. ✅ **Multi-Dimensional Emotion Model** — Fear, loyalty, anger drive behavior
4. ✅ **Enhanced Scene Grounding** — Relationships, distances, visibility, intentions
5. ✅ **Event Bus Integration** — StoryDirect subscribes to events directly
6. ✅ **Plan Persistence** — NPCs don't replan every tick
7. ✅ **Spatial Reasoning** — Euclidean distance, line of sight

---

## Gap 1: Story Director is Now Authoritative

### Before (Suggestions Only)
```
Story Director → influences → NPCs may ignore
```

### After (Constrains + Schedules + Escalates)
```
Story Director → mandates → NPCs MUST comply (bypasses GOAP)
```

### Implementation: StoryArc Class with Phase System

**File:** `src/app/rpg/story/director.py`

```python
class StoryArc:
    """A single story arc with phase-based progression."""
    
    def __init__(self, arc_type, originator, target, **kwargs):
        self.type = arc_type
        self.originator = originator
        self.target = target
        self.phase = "build"  # build → tension → climax → resolution
        self.progress = 0.0
        self.intensity = kwargs.get("intensity", 1.0)
        self.active = True
        self.resolved = False
```

### Phase Transition Logic

```python
def advance(self, global_tension, events):
    # Count relevant events
    for event in events:
        if self._is_relevant_event(event):
            self.progress += 0.3
        else:
            self.progress += 0.05
            
    # Phase transitions
    if self.phase == "build" and self.progress >= 3.0:
        self.phase = "tension"
        self.intensity = min(1.0, self.intensity + 0.2)
    elif self.phase == "tension" and global_tension >= 7.0:
        self.phase = "climax"
        self.intensity = min(1.0, self.intensity + 0.3)
    elif self.phase == "climax" and self.progress >= 6.0:
        self.phase = "resolution"
        self.active = False
```

### Mandated Goals (Bypass GOAP)

```python
def get_forced_goal(self, entity_id):
    """Get a forced goal for an entity in this arc.
    During tension and climax phases, the arc mandates behavior."""
    if self.phase not in ("tension", "climax"):
        return None
        
    if self.type == "revenge":
        if entity_id == self.originator:
            return {
                "type": "attack_target",
                "target": self.target,
                "reason": "forced_revenge",
                "force": self.intensity,
            }
```

### Integration in select_goal()

**File:** `src/app/rpg/ai/goap/state_builder.py`

```python
def select_goal(npc, session=None):
    # 1. Survival (highest)
    if npc.hp < 25:
        return {"type": "survive"}
    
    # 2. 🔥 MANDATED GOALS — Story Director forces behavior
    if session and hasattr(session, 'story_director'):
        mandated = session.story_director.get_mandated_goals(npc.id)
        if mandated:
            return mandated  # Bypasses all other logic
```

---

## Gap 2: Persistent Narrative State

### Arc Phases

| Phase | Trigger | Intensity | Effect |
|-------|---------|-----------|--------|
| **build** | Arc created | 1.0 | Setup, gathering tension |
| **tension** | progress >= 3.0 | +0.2 | NPCs feel pressure |
| **climax** | global_tension >= 7.0 | +0.3 | Forced goals activate |
| **resolution** | progress >= 6.0 in climax | — | Arc deactivates |

### Arc Archive

Resolved arcs are moved to `resolved_arcs` list for historical tracking.

---

## Gap 3: Multi-Dimensional Emotion Model

### Emotion-Driven Goals

**File:** `src/app/rpg/ai/goap/state_builder.py`

```python
def select_goal(npc, session=None):
    emotions = npc.emotional_state
    
    # Fear-driven flight
    if emotions.get("fear", 0) > 1.5 and npc.hp < 40:
        return {"type": "flee"}
        
    # Loyalty-driven protection
    if emotions.get("loyalty", 0) > 0.7:
        return {"type": "protect_ally", "target": ally_id}
```

### Narrative Pressure Influences Emotions

Through `get_narrative_pressure()`:
- Arc phase affects pressure magnitude
- Revenge arcs: +aggression, +urgency
- Betrayal arcs: +caution

---

## Gap 4: Enhanced Scene Grounding

### Before (Weak Grounding)
```json
{
  "entities": [...],
  "events": [...]
}
```

### After (Full Contextual Grounding)
```json
{
  "entities": [...],
  "relationships": [{"source": "a", "target": "b", "attitude": "hostile", "score": -8}],
  "distances": [{"from": "a", "to": "b", "distance": 3.5}],
  "visibility": [{"entity": "a", "can_see": ["b", "c"]}],
  "intentions": [{"entity": "a", "action": "move_toward", "target": "b"}],
  "events": [...]
}
```

### Implementation

**File:** `src/app/rpg/scene/grounding.py`

- `_has_line_of_sight()` — Checks visibility range (10 units)
- Relationship extraction from NPC memory
- Distance matrix computation
- Intentions from NPC actions with plan metadata

---

## Gap 5: Event Bus Integration

### StoryDirector Subscribes to Events

**File:** `src/app/rpg/story/director.py`

```python
class StoryDirector:
    def register_handlers(self, event_bus):
        event_bus.subscribe("death", self._on_death)
        event_bus.subscribe("damage", self._on_damage)
        event_bus.subscribe("critical_hit", self._on_critical_hit)
        
    def _on_death(self, session, event):
        self.global_tension += 3.0
        self._create_revenge_arc(dict(event))
```

### System Decoupling

Each system now subscribes independently:
- `combat_system` → damage, death events
- `story_director` → damage, death, critical_hit events  
- `emotion_system` → damage, death events
- `memory_system` → all events

---

## Gap 6: Plan Persistence

### Before (Stateless Every Turn)
```
tick → build state → plan → execute → discard plan
tick → build state → plan → execute → discard plan  # Jittery
```

### After (Persistent Plans)
```
tick → check if world changed → continue plan OR replan
```

### Implementation

**File:** `src/app/rpg/ai/npc_planner.py`

```python
def decide(npc, session):
    # Plan Persistence — Only replan if conditions changed
    if hasattr(npc, '_current_plan') and npc._current_plan:
        if not _world_changed_significantly(npc, session):
            next_action = npc._current_plan.pop(0)
            return {"action": next_action, "plan": [...]}
    
    # Replan only when significant change detected
    plan_result = goap_plan(state, goal, actions)
    npc._current_plan = [a.name for a in plan_result[1:]]  # Remaining
    npc._current_goal = goal
```

### Replan Triggers

- HP changes > 20 points
- Target identity changes
- No valid plan found

---

## File Changes Summary

### Modified Files (6 files)

| File | Key Changes |
|------|-------------|
| `src/app/rpg/story/director.py` | **Rewritten** — Added StoryArc class, phase system, mandated goals, event bus handlers |
| `src/app/rpg/story/__init__.py` | Added StoryArc, ARC_PHASES exports |
| `src/app/rpg/ai/goap/state_builder.py` | Mandated goals check, emotion-driven goals |
| `src/app/rpg/ai/npc_planner.py` | Plan persistence, _world_changed_significantly() |
| `src/app/rpg/scene/grounding.py` | **Rewritten** — relationships, distances, visibility, intentions |

### New Methods Added

| File | Method | Purpose |
|------|--------|---------|
| StoryDirector | `get_mandated_goals(npc_id)` | Get forced goals that bypass GOAP |
| StoryDirector | `register_handlers(event_bus)` | Subscribe to event bus |
| StoryDirector | `get_forced_events(session)` | Get scheduled events |
| StoryDirector | `schedule_escalation()` | Force narrative escalation |
| StoryArc | `advance(global_tension, events)` | Phase-based progression |
| StoryArc | `get_forced_goal(entity_id)` | Get mandated goal for entity |
| npc_planner | `_world_changed_significantly()` | Check if replanning needed |

---

## Architecture After Upgrades

```
┌─────────────────────────────────────────────────────────────┐
│                     GAME LOOP                                │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐   │
│  │ DECIDE   │    │ ACTIONS  │    │     EVENT BUS        │   │
│  │ (NPC)    │───>│  (GOAP)  │───>│                      │   │
│  │          │    │          │    │  death ─────────┐    │   │
│  └──────────┘    └──────────┘    │  damage ────────┤    │   │
│       ▲                          │  critical_hit ──┤    │   │
│       │         ┌────────────────┴──┐              │    │   │
│       │         │   STORY DIRECTOR  │◄─────────────┘    │   │
│       │         │  ┌─────────────┐  │                   │   │
│  ┌────┴─────┐   │  │ StoryArc[]  │  │                   │   │
│  │ GOAL     │<──┼──│  phases:    │  │                   │   │
│  │ SELECT   │   │  │  build→...  │  │                   │   │
│  │          │   │  │   ↓         │  │                   │   │
│  │ 1.Survive│   │  │  tension    │  │                   │   │
│  │ 2.MANDATED│  │  │   ↓         │  │                   │   │
│  │ 3.Emotion │  │  │  climax     │  │                   │   │
│  │ 4.Revenge │  │  │   ↓         │  │                   │   │
│  │ 5.Default│   │  │  resolution │  │                   │   │
│  └──────────┘   │  └─────────────┘  │                   │   │
│                 │  get_mandated_goals()                   │   │
│                 └───────────────────┘                     │   │
└─────────────────────────────────────────────────────────────┘
```

---

## Verification

```bash
ruff check src/app/rpg/  # All checks passed
```

---

## Key Insights

### What Changed
| Aspect | Before | After |
|--------|--------|-------|
| Arc Influence | Suggested | **Mandated** |
| Arc Lifecycle | Single state | **4-phase progression** |
| Plan Continuity | Replan every tick | **Persistent with dirty-check** |
| Scene Context | Entities + events | **Full relational graph** |
| Event Handling | Passive | **Active subscriptions** |
| Emotion → Goal | Top threat only | **Fear, loyalty, anger** |

### The Transformation Loop

```
Simulation ──→ Events ──→ Narrative ──→ Constraints ──→ Simulation
   ↑                                                            │
   └──────────────────── World changes ←────────────────────────┘
```

This loop is EVERYTHING. The simulation feeds the narrative system, which constrains the simulation, creating emergent storytelling.