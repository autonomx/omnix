# RPG Design & Architecture Document

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture Pattern](#architecture-pattern)
3. [Core Systems](#core-systems)
4. [NPC AI System](#npc-ai-system)
5. [Memory System](#memory-system)
6. [Story Director](#story-director)
7. [Scene System](#scene-system)
8. [Combat System](#combat-system)
9. [Event Bus & Processing](#event-bus--processing)
10. [Spatial System](#spatial-system)
11. [Game Loop](#game-loop)
12. [Data Flow](#data-flow)
13. [Extension Points](#extension-points)

---

## Project Overview

The RPG module is a text-based role-playing game engine with autonomous NPCs driven by GOAP (Goal-Oriented Action Planning), emergent story generation, and an event-driven architecture. The system is designed for dynamic narrative generation where stories emerge from NPC interactions rather than being pre-scripted.

**Key Design Principles:**
- Event-driven decoupling: Systems communicate via published events, avoiding direct dependencies
- Emergent behavior: Story and NPC behavior arises from systems interacting, not hardcoded scripts
- Priority-based execution: Deterministic processing order ensures reproducible simulation
- Memory-based reasoning: NPCs build beliefs from accumulated experiences, not global state

---

## Architecture Pattern

### Event-Driven Architecture

The core architecture follows a publish-subscribe pattern using the `EventBus`. Systems subscribe to specific event types (or wildcard `*`) and process events in priority order.

```
┌─────────────────────────────────────────────────────────────┐
│                         Game Loop                           │
│   1. NPC Decisions → Events    2. System Processing         │
│   3. Story Director Update      4. Advance Time              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        EventBus                             │
│   Priority Queue → Batch Processing → Tick-Bound            │
└─────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│   Combat   │ │  Emotion   │ │   Memory   │ │   Scene    │
│  (Pri -10) │ │  (Pri  0)  │ │ (Pri  5-10)│ │  (Pri  5)  │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
```

### System Registration

Systems register handlers with the event bus during initialization:

| System | Priority | Events Subscribed | Purpose |
|--------|----------|-------------------|---------|
| Combat | -10 | `damage`, `death` | State mutation (HP → death) |
| Emotion | 0 | `damage`, `death` | NPC emotional responses |
| Scene | 5 | `*` (wildcard) | Event collection for narrative |
| Memory - Relationships | 5 | `damage`, `death`, `heal`, `dialogue` | Trust/fear/anger tracking |
| Memory - Beliefs | 7 | `damage`, `death`, `heal`, `assist` | Derived truth layer |
| Memory - General | 10 | `*` (wildcard) | Episodic memory storage |
| Debug | 20 | `*` (wildcard) | Optional logging |

---

## Core Systems

### Data Models

#### GameSession
The root container for a game session, holding all entities and systems.
- `world`: World state with entities, locations, time, size
- `player`: Player stats and profile
- `npcs`: List of NPCs in the session
- `event_bus`: EventBus instance for event processing
- `event_log`: History of game events
- `story_arcs`: Active narrative arcs
- `narrative_state`: Current narrative metadata (tension, phase, etc.)

#### World
- `entities`: Dictionary of all game entities
- `locations`: Location registry
- `time`: Current world tick/time
- `size`: Grid dimensions (width, height)

#### Player
- `id`: Unique player identifier
- `hp`: Health points
- `profile`: Player metadata/preferences

#### SceneOutput
Output of scene generation system:
- `location`: Current location
- `scene_type`: Type of scene (combat, dialogue, etc.)
- `tone`, `tension`: Narrative mood
- `narration`: Generated narrative text
- `characters`: Character dialogue and emotions
- `choices`: Available player choices
- `event`: Associated game event

---

## NPC AI System

### GOAP Planner (Goal-Oriented Action Planning)

Located in `ai/goap/`, the planner enables NPCs to autonomously select actions to achieve goals.

#### Planner (`ai/goap/planner.py`)
A-star search over game state space:
```python
plan(initial_state, goal, actions, max_depth=5)
```
- Uses priority queue for optimal path finding
- Returns ordered list of actions to achieve goal

#### Actions (`ai/goap/actions.py`)
Available NPC actions with preconditions and effects:

| Action | Preconditions | Effects |
|--------|---------------|---------|
| `attack` | enemy_visible, target_in_range | enemy_hp reduced |
| `move_to_target` | has_target, target_in_range:False | target_in_range:True |
| `flee` | low_hp | safe:True |
| `approach` | has_target, enemy_visible:False | enemy_visible:True |
| `idle` | None | None |

#### State Builder (`ai/goap/state_builder.py`)
Builds GOAP state from NPC memories and relationships:
- `has_target`, `enemy_visible`, `target_in_range`
- `low_hp` (from current HP)
- `safe` (environmental awareness)
- `has_hostile_memory` (from past damage events)
- `has_ally` (from trust relationships)
- `has_healer_nearby` (from healing memories)

### NPC Planner (`ai/npc_planner.py`)
High-level decision making wrapper:
- Integrates GOAP planning with belief/emotion/story systems
- Translates NPC state into action selection
- Handles target selection using belief-weighted scoring

### NPC Decision Loop
```
1. Decay emotions
2. Periodic belief decay (every 10 ticks)
3. Build GOAP state from memories
4. Select goal based on beliefs/emotions/story pressure
5. Run GOAP planner
6. Execute first action in plan
```

---

## Memory System

Located in `memory/` and `systems/memory_system.py`.

### Memory Types

#### Episodic Memory
Raw event records with metadata:
```python
{
    "memory_type": "episodic",
    "timestamp": world_time,
    "type": "damage/heal/death/dialogue",
    "source": entity_id,
    "target": entity_id,
    "data": {full_event},
    "importance": float,
    "actor": entity_id,
    "meaning": "I was attacked / violence nearby",
    "tick": world_time,
    "visibility": [npc_ids]
}
```

#### Consolidation (`memory/consolidation.py`)
Compresses frequently repeated episodic memories into summarized forms:
- Groups similar events
- Maintains count of occurrences
- Preserves first/last timestamp

#### Reflection (`memory/reflection.py`)
Higher-order processing of consolidated memories:
- Extracts patterns and insights
- Forms narrative-level understanding

### Relationship System (`memory/relationships.py`)
Tracks interpersonal dynamics between NPCs:
- `trust`: Positive relationship value
- `fear`: Fear of specific entity
- `anger`: Hostility toward specific entity
- Updated via `update_relationship_from_event()`

### Belief System (`memory/belief_system.py`)
The derived truth layer that converts memories into stable beliefs influencing all downstream systems.

**Belief Categories:**
- `hostile_targets`: Entities that have directly harmed the NPC
- `trusted_allies`: Entities that have directly helped the NPC
- `subjugated_targets`: Entities the NPC has harmed
- `dangerous_entities`: Entities observed being aggressive (not necessarily toward NPC)
- `helpful_entities`: Entities observed being helpful (not necessarily toward NPC)
- `world_threat_level`: Overall assessment of world danger

**Event Processing:**
```
EVENT → update_from_event() → _increment() → _recompute_fast() → BELIEFS
```

**Incremental Updates:**
- Direct experience: Full weight
- Observed events: Half weight (0.5x)
- No full memory rescan needed

**Temporal Decay:**
```
decay(dt): counter *= decay_rate^dt; remove if < threshold
```
Default: 5% decay per tick, remove below 0.5 threshold

**Conflict Resolution:**
- Hostility > Trust → hostile target
- Trust > Hostility → trusted ally
- Equal or below threshold → neutral

### Memory System Event Flow
```
Events → [Priority 5] → Relationship Updates
       → [Priority 7] → Belief Updates (incremental)
       → [Priority 10] → Episodic Memory Recording
       → Pruning (importance-based retention)
```

---

## Story Director

Located in `story/director.py`.

The Story Director is the narrative control system that manages story arcs, tracks global tension, and provides narrative pressure that influences NPC behavior.

### Arc Types
- **Revenge**: Created when an NPC is harmed/killed; originator pursues target
- **Betrayal**: Created when trust is violated
- **Alliance**: Created through repeated positive interactions

### Arc Phases
```
intro → build → tension → climax → resolution
```

### Phase Transitions
| Phase | Entry Condition | Narrative Effect |
|-------|-----------------|------------------|
| intro | tension < 0.2 | Calm, exploratory |
| build | tension < 0.5 | Suspicion rising |
| tension | tension < 0.8 | Cautious, reactive |
| climax | tension >= 0.8 | Decisive, emotional |
| resolution | arc resolved | Consequences applied |

### Arc Progression
Arcs advance based on:
- Relevant events involving arc entities (+0.3 progress)
- Irrelevant events (+0.05 progress)
- Global tension for tension→climax transition

### Forced Goals
During tension and climax phases, the Director can mandate NPC behavior:
- Primary arcs get 0.6x force influence
- Secondary arcs get 0.3x force influence (arc conflict resolution)
- Goal shaping biases, not overrides, normal GOAP planning

### Tension System

#### Global Tension
- Rises from combat events
- Decays over time (0.95x per tick)
- Categories: calm (<2), tense (<5), intense (<8), climax (>=8)

#### Local Tension
- Per-entity tension to prevent unrealistically worldwide escalation
- Effective tension = local * 0.7 + global * 0.3
- NPCs react primarily to nearby events

### Memory-Driven Arc Detection
The Director scans NPC memories to detect emergent arcs:
- 3+ damage events from same source → revenge arc
- Ally killed by another → revenge arc
- 3+ healing events from same source → alliance arc

### Anti-Repetition System
- Arc cooldowns prevent revenge loops (15-25 tick cooldowns)
- Goal cooldowns prevent NPCs from repeating same action (3 ticks)

### Narrative Pressure
```python
get_narrative_pressure(entity_id) → {
    "aggression": float(-1.0 to 1.0),
    "caution": float(-1.0 to 1.0),
    "urgency": float(-1.0 to 1.0)
}
```

### Story State for LLM Grounding
```python
get_entity_story_state(entity_id) → {
    "phase": str,
    "tension": float,
    "local_tension": float,
    "arc": str,
    "tension_level": str,
    "active_arcs": [...],
    "arc_count": int
}
```

---

## Scene System

### Scene Generation (`scene_generator.py`)
Generates narrative scenes from game events:
- Integrates story director state
- Builds context from recent events
- Produces narration text with character dialogue

### Grounding (`scene/grounding.py`)
Prevents hallucination in generated scenes:
- Builds grounding block from actual game state
- Validates scene content against real entities, positions, events

### Scene Validation (`scene/validator.py`)
Cross-references generated scenes against grounding data:
- Checks character presence is factual
- Verifies events actually occurred
- Rejects scenes with hallucinated content

### Scene Rendering (`scene/renderer.py`)
Formats scenes for presentation:
- Structures narration output
- Arranges character dialogue and emotions
- Formats player choices

### Scene Collection (`systems/scene_system.py`)
Records all events for later narrative processing:
- Subscribes to all events (wildcard)
- Stores events for scene generation
- Priority 5 (before memory recording)

---

## Combat System

Located in `systems/combat_system.py`.

### Event Processing
**Damage Handler (Priority -10):**
```python
on_damage(session, event):
    target.hp -= amount
    if target.hp <= 0:
        publish("death" event)
```

**Death Handler (Priority -10):**
```python
on_death(session, event):
    target.is_active = False
```

### Attack Resolution
- Spatial constraint: attack only if distance <= 2
- Fixed damage amount (5 in current implementation)
- Death event includes position metadata and cause

---

## Emotion System

Located in `emotion.py` and `systems/emotion_system.py`.

### Emotional State Model
Each NPC maintains:
```python
emotional_state = {
    "neutral": float,
    "angry": float,
    "happy": float,
    "fearful": float,
    "anger": float,
    "fear": float,
    "loyalty": float,
    "last_update": tick,
    "top_threat": entity_id
}
```

### Event Response

**Damage Response:**
- Victim: intensity = 2.0 (anger + fear)
- Attacker: intensity = 0.5 (reduced response)
- Nearby NPCs: intensity = 1.0 (if within perception radius)

**Death Response:**
- Nearby NPCs receive fear increases
- Higher intensity (2.0) if close to death
- Lower intensity (1.0) if at distance

### Emotion Decay
```python
decay_emotions(emotion, decay_rate=0.9):
    for each emotion_type:
        emotion *= decay_rate
```

---

## Event Bus & Processing

Located in `event_bus.py`.

### Core Design
```python
EventBus:
    subscribe(event_type, handler, priority)
    publish(event)  # Queue, don't execute immediately
    process(session)  # Process all queued events at tick end
```

### Event Types
| Event | Required Fields | Triggered By |
|-------|-----------------|--------------|
| `damage` | source, target, amount | Combat, abilities |
| `death` | target | HP reaches 0 |
| `move` | source, position | Movement actions |
| `heal` | source, target, amount | Healing abilities |

### Processing Semantics
1. **Tick-bound**: Events queued during processing go to next tick
2. **Immutable events**: Frozen via `MappingProxyType` to prevent handler mutation
3. **Schema validation**: Required fields checked before queuing
4. **Priority ordering**: Lower priority runs first (combat before emotion before memory)
5. **Wildcard support**: "*" handlers receive all events

---

## Spatial System

Located in `spatial.py`.

### Movement & Positioning
- Grid-based world (configurable size)
- Manhattan distance for pathfinding
- Euclidean distance for range checks (combat)

### Pathfinding (`astar`)
A* algorithm with:
- 8-directional movement
- Obstacle avoidance via occupancy map (active NPCs)
- Manhattan distance heuristic

### Spatial Queries
| Function | Purpose |
|----------|---------|
| `distance(a, b)` | Manhattan distance |
| `euclidean_distance(a, b)` | Euclidean distance |
| `in_range(a, b, r)` | Circular range check |
| `is_near(a, b, radius)` | Proximity check |
| `heuristic(a, b)` | A* heuristic |
| `neighbors(pos, world)` | Valid neighbor cells |

### Perception
NPCs have `perception_radius` (default 5) for:
- Event perception filtering (memory)
- Emotional response filtering
- Spatial awareness in decision making

---

## Game Loop

Located in `game_loop/main.py`.

### Tick Processing
```python
def game_tick(session):
    # 1. Process each NPC
    for npc in session.npcs:
        decay_emotions(npc)
        periodic_belief_decay()
        action = decide(npc, session)
        handle_action(session, action)  # Publishes events

    # 2. Process all events (batch)
    session.event_bus.process(session)

    # 3. Update story director
    session.story_director.update(session, events)

    # 4. Advance time
    session.world.time += 1
```

### Turn Execution
The `execute_turn()` function wraps a complete player turn:
1. Build narrative context
2. Process unified brain (player intent)
3. Run simulation
4. Process NPC actions
5. Process all events
6. Update story director
7. Advance world time
8. Build grounding block
9. Generate scene
10. Validate scene against grounding
11. Update tension
12. Return scene to player

---

## Data Flow

### Complete Event Flow
```
Player Input ───────────────────────────────────────┐
NPC Decisions ─────────────────────────────────────┤
                                                    ▼
                                            ┌──────────────┐
                                            │  handle_action │
                                            │ (actions → events)
                                            └──────┬───────┘
                                                   │
                                          publish() │
                                                   ▼
                                            ┌──────────────┐
                                            │   EventBus   │
                                            │   (Queue)    │
                                            └──────┬───────┘
                                                   │
                                          process() │
                                                   ▼
                          ┌──────────┬───────────┬┴──────────┬──────────┐
                          ▼          ▼           ▼           ▼          ▼
                    ┌─────────┐┌────────┐┌──────────┐┌────────┐┌────────┐
                    │ Combat  ││Emotion ││ Relationship││Beliefs  ││Memory │
                    │ (-10)   ││ (0)    ││ (5)        ││ (7)    ││ (10)  │
                          └─────────┘└────────┘└──────────┘└────────┘└────────┘
                                                   │
                                          events │
                                                   ▼
                                            ┌──────────────┐
                                            │Story Director│
                                            │  (update)    │
                                            └──────┬───────┘
                                                   │
                                          advance_time()
                                                   ▼
                                              World.time += 1
```

### Belief Update Flow
```
Event (damage/heal/death)
    │
    ├──► Relationship Update (priority 5)
    │    └──► update_relationship_from_event()
    │
    ├──► Belief Update (priority 7)
    │    └──► belief_system.update_from_event(event)
    │         └──► _increment(counter, entity, weight)
    │              └──► _recompute_fast()
    │                   └──► beliefs: hostile/trusted/dangerous/helpful
    │
    └──► Episodic Memory (priority 10)
         └──► npc.memory["events"].append(memory_entry)
```

---

## Extension Points

### Adding New Event Types
1. Add schema to `REQUIRED_FIELDS` in `event_bus.py`
2. Subscribe handlers with appropriate priority

### Adding New NPC Actions
1. Add new Action to `default_actions()` in `ai/goap/actions.py`
2. Handle action in `handle_action()` in `game_loop/main.py`

### Adding New Systems
1. Create system module with `register(bus, session)` function
2. Subscribe handlers with appropriate priorities
3. Register in `init_systems()` in `game_loop/main.py`

### Adding New Story Arc Types
1. Add arc type to `_create_*_arc()` methods
2. Update `get_forced_goal()` for arc-specific forced goals
3. Update arc detection in `_detect_*_arc()` methods

---

## Module Structure

```
src/app/rpg/
├── __init__.py
├── models.py                  # Core data models (SceneOutput, GameSession, etc.)
├── models/
│   ├── __init__.py
│   ├── npc.py                 # NPC model with personality, stats, emotions
│   ├── world.py               # World state definitions
│   ├── game_state.py          # Game state definitions
│   └── action_result.py       # Action result definitions
├── event_bus.py               # Event-driven pub/sub system
├── emotion.py                 # Emotion calculations and decay
├── spatial.py                 # Pathfinding and spatial reasoning
├── scene_graph.py             # Scene graph management
├── scene_generator.py         # Scene generation from events
├── game_loop/
│   ├── __init__.py
│   └── main.py                # Main game loop and turn execution
├── ai/
│   ├── npc_planner.py         # High-level NPC decision making
│   ├── memory_context.py      # Memory context for AI
│   └── goap/
│       ├── __init__.py
│       ├── planner.py         # GOAP planning algorithm
│       ├── actions.py         # GOAP action definitions
│       └── state_builder.py   # State construction from memories
├── memory/
│   ├── __init__.py
│   ├── belief_system.py       # Belief derivation from memories
│   ├── consolidation.py       # Memory consolidation
│   ├── reflection.py          # Memory reflection/insight
│   ├── relationships.py       # Relationship system
│   ├── retrieval.py           # Memory retrieval
│   └── memory.py              # Memory management
├── systems/
│   ├── __init__.py
│   ├── combat_system.py       # Damage/death processing
│   ├── emotion_system.py      # Emotional response system
│   ├── memory_system.py       # Memory recording system
│   ├── scene_system.py        # Scene event collection
│   └── debug_system.py        # Optional debug logging
├── story/
│   ├── __init__.py
│   └── director.py            # Story Director (arcs, tension, pacing)
├── scene/
│   ├── __init__.py
│   ├── grounding.py           # Hallucination prevention
│   ├── renderer.py            # Scene rendering
│   ├── scene.py               # Scene model
│   └── validator.py           # Scene validation
├── utils/
│   ├── __init__.py
│   └── entity_lookup.py       # Centralized entity lookup
└── world/
    └── __init__.py            # World system initialization