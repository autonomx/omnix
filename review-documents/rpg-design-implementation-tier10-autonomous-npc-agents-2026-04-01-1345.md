# TIER 10: Autonomous NPC Agent System - Implementation Review

**Date:** 2026-04-01 13:45  
**Design Specification:** `rpg-design.txt` - TIER 10: Autonomous NPC Agent System  
**Status:** ✅ COMPLETE (56 unit tests passing)

---

## Executive Summary

This implementation transforms RPG characters from static data containers into autonomous agents that can perceive the world, reason about goals, plan multi-step actions, execute them, and adapt based on outcomes. The core design principle is **"Agents generate events, systems react to events"** — no direct world state modification.

---

## New Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `src/app/rpg/agent/__init__.py` | Module exports for agent system | 31 |
| `src/app/rpg/agent/agent_brain.py` | Decision-making: goals + beliefs → intentions | 300+ |
| `src/app/rpg/agent/planner.py` | Multi-step plan creation and tracking | 220+ |
| `src/app/rpg/agent/action_executor.py` | Action → event generation | 380+ |
| `src/app/rpg/agent/agent_scheduler.py` | NPC selection per tick with priority | 180+ |
| `src/app/rpg/agent/agent_system.py` | Orchestrator: ties all components together | 180+ |
| `src/tests/unit/rpg/test_tier10_agents.py` | 56 unit tests | 520+ |
| `src/tests/integration/test_tier10_agents.py` | Integration/regression tests | 180+ |

---

## Architecture

```
PlayerLoop.step()
     ↓ TIER 10 (after faction/economy/quest processing)
AgentSystem.update(characters, world_state)
     ↓
1. AgentScheduler.select_agents() — pick max N NPCs by priority
     ↓
2. For each active NPC:
     ├── If has active plan → continue executing steps
     └── If no plan → AgentBrain.decide() → Planner.create_plan()
     ↓
3. ActionExecutor.execute() → events
     ↓
4. Events returned to PlayerLoop for world systems to process
```

---

## Component Details

### 1. AgentBrain (`agent_brain.py`)
**Purpose:** Convert NPC goals + beliefs + world state → intention

**Key Features:**
- **Survival-first priority** (power < 0.2 triggers resource gathering at priority 10.0)
- **Goal pattern matching** with keyword-based intent classification:
  - `gain power`, `expand`, `influence` → `expand_influence`
  - `attack`, `destroy`, `revenge` → `attack_target`
  - `gather`, `accumulate` → `gather_resources`
  - `negotiate`, `diplomacy` → `negotiate`
  - `help`, `aid`, `deliver` → `deliver_aid`
- **Belief modulation** of intention priority (strong negative beliefs amplify aggression)
- **Deterministic** — no LLM in core loop

### 2. Planner (`planner.py`)
**Purpose:** Convert intentions → multi-step action sequences

**Plan Templates:**
| Intention | Steps |
|-----------|-------|
| `expand_influence` | `increase_power` → `negotiate` |
| `attack_target` | `gather_forces` → `attack` |
| `deliver_aid` | `gather_resources` → `travel` → `deliver` |
| `gather_resources` | `scout` → `collect` |
| `negotiate` | `prepare` → `meet` → `agree` |
| `defend` | `fortify` → `wait` |
| `idle` | `wait` |

**Key Features:**
- Plans persist across ticks via `active_plans` dict
- Progress tracking (`progress` property 0.0–1.0)
- Plans can be cancelled mid-execution
- Custom templates can be registered at runtime

### 3. ActionExecutor (`action_executor.py`)
**Purpose:** Execute action steps → generate world events

**Event Types Generated:**
| Action | Event Type |
|--------|-----------|
| `increase_power` | `power_growth` |
| `attack` | `faction_conflict` |
| `deliver` | `aid_delivered` |
| `gather_forces` | `military_preparation` |
| `negotiate` | `diplomatic_meeting` |
| `travel` | `travel` |
| `scout` | `scouting` |
| `fortify` | `fortification` |
| `agree` | `agreement` |

**Critical Design Rule:** Events only — no direct state mutation.

### 4. AgentScheduler (`agent_scheduler.py`)
**Purpose:** Select which NPCs act each tick

**Selection Algorithm:**
1. Calculate priority score: `base + power*0.5 + goals*0.2 + starvation_bonus`
2. Add random noise (0.7–1.3x) for variety
3. Sort by score, select top `max_per_tick`

**Starvation Prevention:** NPCs not selected recently get increasing priority bonus, ensuring all characters eventually get turns.

### 5. AgentSystem (`agent_system.py`)
**Purpose:** Single entry point orchestrating all components

**Update Pipeline:**
```python
def update(characters, world_state):
    events = []
    for cid in scheduler.select_agents(characters):
        if cid in active_plans:
            step = active_plans[cid].next()
            if step:
                events += executor.execute(char, step, world_state)
            else:
                del active_plans[cid]
        else:
            intention = brain.decide(char, world_state)
            if intention and intention["type"] != "idle":
                plan = planner.create_plan(intention)
                active_plans[cid] = plan
                step = plan.next()
                events += executor.execute(char, step, world_state)
    return events
```

---

## PlayerLoop Integration

**Position in `step()`:**
```
1. Player action injection
2. World simulation tick
3. Agency recording + reputation update
4. Plot engine update
5. Faction simulation tick
6. Economy + Politics tick
7. Quest generation
8. Scene generation + CharacterEngine updates
9. Memory + Story arc updates
10. ← TIER 10: AgentSystem.update() HERE
11. Event conversion to NarrativeEvents
12. AI Director shaping
13. Narration generation
```

**Integration Code Added to `player_loop.py`:**
```python
# TIER 10: Autonomous NPC Agent System
self.agents = agent_system or AgentSystem()

# In step():
agent_events = self.agents.update(
    characters=self.characters.characters,
    world_state=self._get_world_state_for_agents(),
)
world_events.extend(agent_events)
```

---

## Design Compliance

| Design Rule | Status | Implementation |
|-------------|--------|----------------|
| DO NOT modify world state directly | ✅ | `ActionExecutor` only generates events |
| Plans persist across ticks | ✅ | `active_plans` dict in `AgentSystem` |
| Limit agents per tick | ✅ | `max_per_tick` in `AgentScheduler` |
| Keep logic deterministic | ✅ | No LLM calls in core loop |
| Events-only communication | ✅ | All output is `List[Dict[str, Any]]` |

---

## Test Results

**Unit Tests:** 56/56 passed ✅

| Test Category | Count | Status |
|---------------|-------|--------|
| AgentBrain | 11 | ✅ All passed |
| Planner | 15 | ✅ All passed |
| ActionExecutor | 13 | ✅ All passed |
| AgentScheduler | 9 | ✅ All passed |
| AgentSystem | 8 | ✅ All passed |

**Regression Tests:** Verify existing Tier 1-9 systems unaffected ✅

---

## What This Unlocks

**Before:** World evolves → Player reacts

**After:** NPCs act → World changes → Player reacts → NPCs adapt

Characters now pursue their own agendas independently of player actions, creating emergent conflicts, alliances, and storylines that make the world feel alive.

---

## Files Modified

| File | Change |
|------|--------|
| `src/app/rpg/core/player_loop.py` | Added `AgentSystem` import, constructor param, update call, helper method, reset |

## Files Created

| File | Purpose |
|------|---------|
| `src/app/rpg/agent/__init__.py` | Module exports |
| `src/app/rpg/agent/agent_brain.py` | Decision-making engine |
| `src/app/rpg/agent/planner.py` | Multi-step planning |
| `src/app/rpg/agent/action_executor.py` | Event generation |
| `src/app/rpg/agent/agent_scheduler.py` | NPC turn scheduling |
| `src/app/rpg/agent/agent_system.py` | System orchestrator |
| `src/tests/unit/rpg/test_tier10_agents.py` | 56 unit tests |
| `src/tests/integration/test_tier10_agents.py` | 15 integration tests |

---

## Next Steps (Future Enhancements)

1. **LLM-intention mapping**: Replace keyword matching with LLM intent classification
2. **Belief-driven action selection**: Use character personality traits to weight action probabilities
3. **Memory-informed planning**: Incorporate character memory into plan creation
4. **Coalition forming**: Multiple NPCs coordinating on shared goals
5. **Learning from outcomes**: Adapt future plans based on success/failure feedback