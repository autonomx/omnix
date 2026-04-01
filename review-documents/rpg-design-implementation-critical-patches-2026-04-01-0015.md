# RPG Design Implementation — Critical Patches

**Date:** 2026-04-01 00:15  
**Design Spec:** `rpg-design.txt`  
**Status:** ✅ Complete — 53/53 tests passing

---

## Overview

This implementation addresses all 5 critical patches identified in `rpg-design.txt`:

| Patch | Description | Status |
|-------|-------------|--------|
| 1 | DirectorAgent — LLM-first multi-step planner | ✅ |
| 2 | AgentScheduler — Multi-agent orchestration | ✅ |
| 3 | AutonomousTickManager — AI-driven decisions | ✅ |
| 4 | BehaviorDriver — Memory-driven NPC behavior | ✅ |
| 5 | SceneManager — Scene/narrative structure | ✅ |

---

## New Files Created

### 1. `src/app/rpg/story/director_agent.py` (PATCH 1)

**Purpose:** Upgrade Director from single-action output to LLM-first multi-step planner.

**Key Classes:**
- `DirectorOutput` — Structured output with plan, actions, reasoning, tension_delta
- `DirectorAgent` — LLM-driven director that generates multi-step plans

**Key Methods:**
- `decide(player_input, context, world, memory_context, beliefs)` → DirectorOutput
- `quick_decision(player_input, tension, active_arcs)` → DirectorOutput (heuristic fallback)
- `_build_prompt(...)` → LLM prompt with world state, memory, beliefs, available actions
- `_parse_response(response)` → Parses JSON from LLM (handles fenced code blocks)

**Design Compliance:**
```python
# From rpg-design.txt:
class DirectorAgent:
    def decide(self, input, context, world):
        prompt = f"""
You are a STORY DIRECTOR AI.
GOALS:
- Progress the story
- Maintain coherence
- Introduce conflict
- Use available actions strategically
...
Return JSON:
{{
  "plan": "...",
  "actions": [
    {{"action": "...", "parameters": {{...}}}}
  ]
}}
"""
```

**Key Changes from Design:**
- Added `reasoning` field for LLM explanation
- Added `tension_delta` for tension control
- Added `max_actions` limit to prevent runaway plans
- Added `quick_decision()` heuristic fallback when LLM unavailable
- Supports multiple directing styles: dramatic, balanced, chaotic

---

### 2. `src/app/rpg/core/agent_scheduler.py` (PATCH 2 + PATCH 3)

**Purpose:** Introduce Agent Scheduler for multi-agent coordination and autonomous ticks.

**Key Classes:**
- `AgentScheduler` — Coordinates Director → Actions → Memory → World → Narrator
- `AutonomousTickManager` — Manages AI-driven decisions during player inactivity

**AgentScheduler Turn Flow:**
```
1. Director.decide() → multi-step plan
2. For each action in plan:
   a. ActionRegistry.execute_action_dict()
   b. Collect events
3. MemoryManager.add_events() with collected events
4. WorldState.apply_event() for all events
5. NarratorAgent.generate() with events
6. Return result dict
```

**AutonomousTickManager Triggers:**
- Time-based: Player inactive for N seconds
- Turn-based: Every N turns (configurable)

**Design Compliance:**
```python
# From rpg-design.txt:
class AgentScheduler:
    def run_turn(self, input):
        plan = director.decide(...)
        for step in plan["actions"]:
            result = tools.execute_action_dict(step)
            memory.add_events(result["events"])
            world.apply_event(...)
        narration = narrator.generate(...)
        return narration
```

---

### 3. `src/app/rpg/ai/behavior_driver.py` (PATCH 4)

**Purpose:** Inject beliefs and memory into NPC decision layer.

**Key Classes:**
- `BehaviorContext` — Complete behavioral context (beliefs, relationships, memories, personality, emotion)
- `BehaviorDriver` — Bridge between memory system and NPC behavior

**Key Methods:**
- `build_decision_context(npc_id, entities, max_memories)` → BehaviorContext
- `generate_reasoning(context, proposed_action)` → Dict with reasoning/motivation
- `build_decision_prompt(context, available_actions, player_input, world_state)` → LLM prompt
- `update_beliefs_from_action(npc_id, action_result)` → Updates memory from action outcomes

**Design Compliance:**
```python
# From rpg-design.txt:
context = memory.get_context_for(entities)
beliefs = memory.semantic_beliefs

prompt += f"""
Beliefs:
{beliefs}
"""

Then require:
"reasoning": "Based on hostility between guard and player..."
```

**Belief Sources:**
- BeliefSystem (hostile_targets, trusted_allies, dangerous_entities)
- MemoryManager semantic_beliefs
- Relationship values

---

### 4. `src/app/rpg/scene/scene_manager.py` (PATCH 5)

**Purpose:** Add Scene/Narrative Structure Layer with goal-based scenes.

**Key Classes:**
- `Scene` — Narrative scene with goal, participants, progress tracking
- `SceneManager` — Manages scene lifecycle, transitions, templates

**Scene Lifecycle:**
```
1. Create scene with goal
2. Feed events to update progress
3. Scene completes when progress threshold reached
4. Transition to next scene
```

**Key Methods:**
- `new_scene(goal, participants, tags, max_progress)` → Scene
- `new_scene_from_events(events)` → Auto-inferred scene from events
- `update_scene(events)` → Feed events for progress tracking
- `advance_scene(new_goal, participants, tags)` → Force scene transition
- `get_scene_context()` → Dict for LLM prompts
- `register_template(name, goal, tags)` / `create_from_template(name, participants)`

**Event Progress Weights:**
| Event Type | Progress Delta |
|------------|---------------|
| damage, death, critical_hit | 0.15 |
| attack, combat | 0.10 |
| story_event | 0.10 |
| speak, dialogue (participant) | 0.05 |
| move | 0.05 |
| other | 0.02 |

---

## Modified Files

### `src/app/rpg/core/__init__.py`
- Added exports: `AgentScheduler`, `AutonomousTickManager`

### `src/app/rpg/story/__init__.py`
- Added exports: `DirectorAgent`, `DirectorOutput`
- Preserved backward compat: `DirectorOutputOriginal`

### `src/app/rpg/ai/__init__.py`
- Added exports: `BehaviorDriver`, `BehaviorContext`

### `src/app/rpg/scene/__init__.py`
- Added exports: `Scene`, `SceneManager`

---

## Test Coverage

**File:** `src/tests/unit/rpg/test_rpg_design_patches.py`

| Test Class | Tests | Status |
|------------|-------|--------|
| TestDirectorOutput | 5 | ✅ |
| TestDirectorAgent | 10 | ✅ |
| TestAgentScheduler | 5 | ✅ |
| TestAutonomousTickManager | 5 | ✅ |
| TestBehaviorContext | 3 | ✅ |
| TestBehaviorDriver | 4 | ✅ |
| TestScene | 7 | ✅ |
| TestSceneManager | 14 | ✅ |
| **Total** | **53** | **✅ 53/53** |

---

## Code Diff Summary

### New Files (4 modules + 1 test)
```
src/app/rpg/story/director_agent.py     ~350 lines
src/app/rpg/core/agent_scheduler.py     ~320 lines
src/app/rpg/ai/behavior_driver.py       ~340 lines
src/app/rpg/scene/scene_manager.py      ~400 lines
src/tests/unit/rpg/test_rpg_design_patches.py  ~400 lines
```

### Modified Files (4 init files)
```
src/app/rpg/core/__init__.py   +4 lines
src/app/rpg/story/__init__.py  -53/+7 lines
src/app/rpg/ai/__init__.py     +4 lines
src/app/rpg/scene/__init__.py  -6/+4 lines
```

### Total Lines Added: ~1,825
### Total Lines Modified: ~60

---

## Architecture Integration

### How Patches Connect

```
Player Input
    │
    ▼
┌─────────────────────────────────────────────────┐
│  PATCH 1: DirectorAgent                         │
│  - LLM decides multi-step plan                  │
│  - Uses world state, memory, beliefs            │
│  - Returns: plan, actions[], reasoning          │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  PATCH 2: AgentScheduler                        │
│  - Executes each action in plan                 │
│  - Collects events                              │
│  - Updates memory + world state                 │
│  - Generates narration                          │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  PATCH 4: BehaviorDriver                        │
│  - Injects beliefs into NPC decisions           │
│  - Provides reasoning from memories             │
│  - Updates beliefs from action outcomes         │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  PATCH 5: SceneManager                          │
│  - Tracks scene progress from events            │
│  - Handles scene transitions                    │
│  - Provides scene context for LLM               │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  PATCH 3: AutonomousTickManager                 │
│  - Triggers during player inactivity            │
│  - Director decides autonomous story beats      │
│  - World continues to evolve                    │
└─────────────────────────────────────────────────┘
```

---

## Usage Examples

### Basic Turn with DirectorAgent
```python
from rpg.story.director_agent import DirectorAgent
from rpg.tools.action_registry import ActionRegistry, register_default_actions
from rpg.core.agent_scheduler import AgentScheduler
from rpg.world.world_state import WorldState

# Setup
world = WorldState()
world.add_entity("player", {"hp": 100})
world.add_entity("guard", {"hp": 50})

registry = ActionRegistry(world=world)
register_default_actions(registry)

director = DirectorAgent(llm=my_llm, style="dramatic")
scheduler = AgentScheduler(director=director, registry=registry, world=world)

# Run turn
result = scheduler.run_turn(
    session=game_session,
    player_input="I attack the guard!",
    memory_context="The guard remembers being attacked before...",
    beliefs={"hostile": {"reason": "Player attacked me", "value": -0.5}},
)

print(result["narration"])  # Generated narrative
print(result["events"])     # All events from this turn
print(result["plan"])       # Director's plan
```

### Autonomous Tick
```python
from rpg.core.agent_scheduler import AutonomousTickManager

tick_mgr = AutonomousTickManager(scheduler, default_interval=5)

# Check if should tick (player inactive for 30s)
if tick_mgr.should_tick(player_last_active=100.0, current_time=135.0):
    result = tick_mgr.autonomous_tick(
        memory_context="Recent events suggest tension is building...",
    )
    print(result["narration"])
```

### Scene Management
```python
from rpg.scene.scene_manager import SceneManager

manager = SceneManager()

# Create scene from events
scene = manager.new_scene_from_events(
    events=[
        {"type": "damage", "source": "player", "target": "guard"},
        {"type": "speak", "speaker": "guard", "message": "You'll pay for that!"},
    ]
)

# Update scene with more events
manager.update_scene(new_events)

# Check if scene is complete
if manager.is_scene_complete():
    # Transition to next scene
    new_scene = manager.advance_scene(
        new_goal="Escape the dungeon",
        participants={"player"},
    )
```

### Behavior-Driven NPC Decisions
```python
from rpg.ai.behavior_driver import BehaviorDriver

driver = BehaviorDriver(memory_manager=memory_mgr)

# Build decision context for NPC
context = driver.build_decision_context(
    npc_id="guard",
    entities=["player"],
    max_memories=5,
)

# Generate reasoning for proposed action
reasoning = driver.generate_reasoning(context, "attack")
# {"reasoning": "Based on Player attacked me... Hostility toward player motivates aggressive response", ...}

# Build full LLM prompt
prompt = driver.build_decision_prompt(
    context=context,
    available_actions="attack, move, speak",
    player_input="I come in peace",
    world_state="World T=5: 2 active entities, 1 hostile pair",
)
```

---

## Design Spec Compliance Checklist

### PATCH 1: Director → LLM-first planner ✅
- [x] Director outputs multi-step plans (not single action)
- [x] Uses LLM prompt with world state, memory, beliefs
- [x] Returns JSON with plan, actions[], reasoning
- [x] Available actions included in prompt
- [x] Fallback when LLM unavailable

### PATCH 2: Agent Scheduler ✅
- [x] Multiple actions per turn
- [x] Multi-agent coordination (Director → Tools → Memory → Narrator)
- [x] Correct execution order
- [x] World state updates after actions
- [x] Memory updates after actions

### PATCH 3: Autonomous Tick System ✅
- [x] Triggers on player inactivity
- [x] Triggers on turn interval
- [x] Director decides without player input
- [x] World continues to evolve

### PATCH 4: Memory Drives Behavior ✅
- [x] Beliefs injected into decision layer
- [x] NPC reasoning based on memories
- [x] "reasoning" field required in output
- [x] Relationship-aware decisions
- [x] Beliefs updated from action outcomes

### PATCH 5: Scene/Narrative Structure ✅
- [x] Scenes with explicit goals
- [x] Progress tracking from events
- [x] Scene transitions
- [x] Pacing control
- [x] Director integration for scene changes
- [x] Scene context for LLM prompts

---

## Notes

- All new modules are backward compatible with existing code
- `DirectorOutput` from `director_agent.py` is distinct from `DirectorOutput` in `director_types.py` (original)
- `BehaviorDriver` works with or without `MemoryManager` (graceful degradation)
- `SceneManager` can auto-infer scenes from events or use explicit goals
- `AutonomousTickManager` is optional — only needed for AI-driven story progression