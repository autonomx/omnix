# Design Document: Memory Continuity System

**Branch:** `copilot/implement-memory-continuity-system`  
**Version:** 1.0  
**Date:** April 2026  
**Status:** Implemented and Merged (PR #94)

---

## 1. Executive Summary

The Memory Continuity System branch introduces a comprehensive memory management architecture (Phase 11) paired with a goal-directed planning and intent system (Phase 12), plus eleven additional RPG subsystems (Phases 13-23). The primary design goal was to give NPCs persistent, bounded, deterministic memory that influences their decisions, goals, and plans — creating more believable and coherent character behavior over long RPG sessions.

**Key Metrics:**
- **8,147 lines of new code** across 18 files
- **2,355 lines of unit tests** (130+ test cases)
- **Zero modifications to existing code** (additive-only changes)
- **All state is bounded and deterministic** (enforced by validators)

---

## 2. Design Goals

### 2.1 Primary Goals

| Goal | Description |
|------|-------------|
| **Memory Continuity** | NPCs remember past interactions, decisions, and events in bounded, searchable memory stores. |
| **Decision Influence** | Memories actively influence NPC decision-making through trust/fear modifiers and suggested intents. |
| **Goal-Directed Behavior** | NPCs generate goals from beliefs and memories, construct multi-step plans, and execute them. |
| **Plan Intelligence** | Plans support interruption, replanning, companion alignment, and faction coordination. |
| **Determinism** | All memory and planning state is deterministic — identical inputs produce identical outputs for save/load parity. |
| **Bounded State** | Every collection has strict maximum sizes to prevent memory unbounded growth. |
| **Debug Observability** | Inspector APIs provide runtime visibility into NPC memory and planning state. |

### 2.2 Non-Goals

- LLM integration (memory retrieval is deterministic, not learned)
- Real-time persistence (state is in-memory; persistence handled by save_packaging.py)
- Player-facing UI (presentation is handled by separate layers)

---

## 3. Architecture

### 3.1 System Boundaries

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RPG Game Loop                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Dialogue    │  │  NPC Agency  │  │   Scene Engine           │  │
│  │  System      │  │  System      │  │   System                 │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────────────┘  │
│         │                 │                    │                     │
│  ┌──────▼─────────────────▼────────────────────▼─────────────────┐  │
│  │              MEMORY CONTINUITY SYSTEM (Phase 11)              │  │
│  │                                                               │  │
│  │  Conversation │ Actor │ World │ Compressor │ Retriever       │  │
│  │  Memory       │ Memory│ Memory│            │ Influence Engine│  │
│  │                                                               │  │
│  └──────────────────────┬────────────────────────────────────────┘  │
│                         │                                           │
│  ┌──────────────────────▼────────────────────────────────────────┐  │
│  │              PLANNING / INTENT SYSTEM (Phase 12)              │  │
│  │                                                               │  │
│  │  Goal Generator → Plan Builder → Plan Executor               │  │
│  │  Interrupt Handler → Companion Planner → Faction Coordinator │  │
│  │                                                               │  │
│  └──────────────────────┬────────────────────────────────────────┘  │
│                         │                                           │
│  ┌──────────────────────▼────────────────────────────────────────┐  │
│  │              ADDITIONAL SYSTEMS (Phases 13-23)                │  │
│  │  Performance │ GM Tools │ Director │ Encounters │ Economy    │  │
│  │  Quest Deepening │ Social Sim │ Travel │ Save │ UX Polish    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Hierarchy

```
MemoryContinuitySystem
├── ConversationMemory          (short-term, bounded)
├── ActorMemory                 (long-term, bounded)
├── WorldMemory                 (world events + rumors, bounded)
├── MemoryCompressor            (importance-based compression)
├── DialogueMemoryRetriever     (contextual retrieval)
├── MemoryInfluenceEngine       (decision modifiers)
├── MemoryInspector             (debug introspection)
└── MemoryDeterminismValidator  (state validation)

PlanningSystem (intent_system.py)
├── GoalGenerator               (belief → goal generation)
├── PlanBuilder                 (goal → multi-step plan)
├── PlanExecutor                (step-by-step execution)
├── PlanInterruptHandler        (dynamic replanning)
├── CompanionPlanner            (leader-aligned companion plans)
├── FactionIntentCoordinator    (multi-actor coordination)
├── PlannerInspector            (debug introspection)
└── PlanningDeterminismValidator (state validation)
```

---

## 4. Memory Continuity System (Phase 11)

### 4.1 Memory Model

The memory model is a **four-tier bounded hierarchy**:

| Tier | Storage | Max Size | Purpose |
|------|---------|----------|---------|
| Short-term | `ConversationMemory.entries` | 20 turns | Recent dialogue context |
| Long-term | `ActorMemory.entries` | 200 entries | Significant actor experiences |
| World | `WorldMemory.world_events` | 50 entries | Shared world state |
| Rumors | `WorldMemory.rumors` | 30 entries | Gossip and information spread |

### 4.2 Memory Lifecycle

```
1. CREATE
   Dialogue turn or event → Memory entry with salience score
   ↓
2. DECAY
   Each tick → Salience multiplied by decay factor (0.95^age or 0.8 after window)
   ↓
3. COMPRESS
   When bounds exceeded → Low-salience entries removed, summary added
   ↓
4. RETRIEVE
   Query → Scored retrieval with recency, relevance, and salience weighting
   ↓
5. INFLUENCE
   Decision point → Trust/fear modifiers computed from memories
   ↓
6. CLEANUP
   Bounds check → Excess entries trimmed, values clamped
```

### 4.3 Salience Scoring

Salience is a float in range `[0.0, 1.0]` that determines memory importance:

| Event Type | Base Salience | Decay Model |
|------------|---------------|-------------|
| Dialogue turn | 1.0 | Decay after 10 ticks → 0.8x per tick |
| Actor interaction | 0.5 | 0.95^age per tick |
| World event | 0.7 | Truncated at MAX_WORLD |
| Rumor | 0.5 credibility | 0.9x per tick |

### 4.4 Retrieval Algorithm

The `DialogueMemoryRetriever.retrieve_for_dialogue()` method scores each memory:

```python
# Short-term scoring
score = 0.3  # base
+ 0.4 if speaker matches  # identity bonus
+ 0.3 if topic matches    # relevance bonus
× 1.0 / (1.0 + age × 0.1)  # recency decay

# Long-term scoring
score = 0.2  # base
+ 0.5 if actor matches  # identity bonus
+ 0.3 if topic in event  # relevance bonus
× salience               # importance weighting

# Returns top-5 scored memories as context
```

### 4.5 Decision Influence

The `MemoryInfluenceEngine` computes three outputs:

| Output | Range | Meaning |
|--------|-------|---------|
| `trust_modifier` | -1.0 to 1.0 | Positive interactions → higher trust |
| `fear_modifier` | -1.0 to 1.0 | Hostile memories → higher fear |
| `suggested_intent` | enum | flee / defend / cooperate / None |

```
Positive interactions (help, heal, gift, trade):
  trust += salience × 0.3

Negative interactions (attack, betray, steal, threaten):
  fear  += salience × 0.3
  trust -= salience × 0.2

Neutral interactions (observe, dialogue):
  trust += salience × 0.05

If fear > 0.5 → suggest "flee"
If trust < -0.3 → suggest "defend"
If trust > 0.5 → suggest "cooperate"
```

### 4.6 Bound Enforcement

All collections enforce strict bounds:

| Collection | Max | Enforcement Strategy |
|------------|-----|---------------------|
| Short-term entries | 20 | Truncate to last N on overflow |
| Long-term entries | 200 | Keep top N by salience on overflow |
| World events per entity | 50 | Truncate to last N |
| Rumors | 30 | Keep top N by credibility on overflow |

### 4.7 Determinism Guarantees

The `MemoryDeterminismValidator` ensures:
1. **Identical state → identical dict**: `s1.to_dict() == s2.to_dict()` for same-history states.
2. **Bound compliance**: Every collection size ≤ its maximum.
3. **Value compliance**: All salience/credibility values in [0.0, 1.0].
4. **Normalization**: `normalize_state()` clamps all values and trims excess entries.

---

## 5. Planning / Intent System (Phase 12)

### 5.1 Goal Generation

Goals are generated from three inputs:

| Input | Source | Effect |
|-------|--------|--------|
| Beliefs | NPC belief system | Hostile targets → "neutralize" goals |
| Memory Summary | Memory continuity | Trusted allies → "protect" goals |
| World Context | World state | High threat → "survive" goals |

**Generated Goal Types:**

| Goal Type | Trigger | Priority Formula |
|-----------|---------|-----------------|
| `neutralize` | Hostile targets detected | 0.6 + count × 0.1 |
| `protect` | Trusted allies present | 0.5 + count × 0.05 |
| `survive` | World threat > 0.5 | 0.7 + threat_level × 0.2 |
| `acquire` | Resources < 0.3 | 0.4 + (1 - resources) × 0.3 |

**Constraint:** Maximum 3 goals generated per tick, maximum 5 active goals per actor.

### 5.2 Plan Construction

Plans are built from goal-type templates:

| Goal | Step 1 | Step 2 | Step 3 |
|------|--------|--------|--------|
| neutralize | approach | engage | resolve |
| protect | move_to | guard | alert |
| survive | assess | retreat_or_defend | recover |
| acquire | locate | obtain | secure |

**Constraint:** Maximum 5 steps per plan.

### 5.3 Plan Execution Flow

```
Plan.active → Get current step → Execute action → Advance step → Success/Fail
                                                          ↓
                                    Step completed → All done? → Plan complete/fail
                                                          ↓
                                                        New goal generation
```

### 5.4 Plan Interruption

**Interrupt Types:**

| Type | Severity | Triggers |
|------|----------|----------|
| `threat_detected` | Critical | Attack, ambush events |
| `goal_invalidated` | Critical | Target goal already completed |
| `ally_in_danger` | Critical | Ally attacked/down events |
| `better_opportunity` | Low-high | Opportunity events |
| `plan_blocked` | Low-high | Path blocked events |

**Replanning Rule:** If any **critical** interrupt detected → suspend plan → trigger replanning.

### 5.5 Companion Planning

Companion plans are aligned with the leader's plan:

| Leader Action | Companion Response |
|---------------|-------------------|
| approach/engage/resolve | `support_attack` |
| move_to/guard/alert | `cover_ally` |
| assess/retreat_or_defend | `cover_retreat` |
| locate/obtain/secure | `scout_ahead` |

Companion plans include 2 steps: `{aligned_action}` → `follow`.

### 5.6 Faction Coordination

The `FactionIntentCoordinator` resolves plan conflicts:

```
Collect all faction member plans
→ For each target with multiple assignees:
  → Assign 1 primary actor
  → Assign others as flanking
→ Return coordination map
```

### 5.7 Determinism Guarantees

The `PlanningDeterminismValidator` ensures:
1. Identical planning state → identical dict
2. `active_goals ≤ 5` per actor
3. `completed_goals ≤ 20` per actor
4. `global_objectives ≤ 10`
5. All priority/progress values in `[0.0, 1.0]`

---

## 6. Additional Systems (Phases 13-23)

| Module | Purpose | Key Features |
|--------|---------|--------------|
| `performance.py` | Game loop timing | Tick budget, profiling |
| `gm_tools.py` | GM controls | Scene control, NPC override |
| `director_integration.py` | Narrative direction | Pacing, tension tracking |
| `tactical_mode.py` | Combat encounters | Initiative, positioning |
| `economy.py` | In-game economy | Pricing, trade, markets |
| `emergent_endgame.py` | Story conclusions | Ending generation |
| `save_packaging.py` | Save serialization | Compression, versioning |
| `quest_deepening.py` | Quest depth | Branching, consequences |
| `social_sim_v2.py` | Social dynamics | Reputation, factions |
| `travel_system.py` | Journey simulation | Pathfinding, rest |
| `production_polish.py` | UX helpers | Display formatting |

---

## 7. State Serialization

All state classes implement `to_dict()` and `from_dict()`:

```python
# Example: MemoryState
state.to_dict() → {
    "tick": 42,
    "short_term": [{"speaker": "npc_1", "text": "...", "tick": 40, "salience": 0.9}],
    "long_term": [...],
    "world_memories": {...},
    "rumor_memories": [...]
}

MemoryState.from_dict(dict) → MemoryState
```

This enables:
- Save/load parity
- Cross-session continuity
- Debug inspection
- Determinism validation

---

## 8. Integration Points

### 8.1 With Dialogue System

```
Dialogue Turn → ConversationMemory.add_turn(speaker, text, tick)
                                        ↓
Dialogue Response ← DialogueMemoryRetriever.retrieve_for_dialogue(speaker_id, listener_id, topic)
```

### 8.2 With NPC Decision Engine

```
Beliefs + Memory → MemoryInfluenceEngine.compute_memory_influence(actor_id, context)
                                        ↓
NPC Decision Engine ← {trust_modifier, fear_modifier, suggested_intent, memory_tags}
```

### 8.3 With Goal Engine

```
Memory + Beliefs → GoalGenerator.generate_goals(actor_id, beliefs, memory, world, tick)
                                        ↓
Goal Engine ← List[GoalState]
```

### 8.4 With Save System

```
MemoryContinuitySystem.to_dict() → Save packaging
Planning System State.to_dict() → Save packaging
Load → MemoryContinuitySystem.from_dict()
     → Planning System State.from_dict()
```

---

## 9. Performance Considerations

| Aspect | Strategy |
|--------|----------|
| Memory bounds | Strict collection size limits prevent OOM |
| Decay model | Multiplicative decay is O(n) per tick |
| Retrieval | Score all entries, keep top-5 (O(n log n)) |
| Plan steps | Maximum 5 steps limits execution depth |
| Goal generation | Maximum 3 goals per tick prevents explosion |
| Companion plans | Derived from leader plan (O(1) complexity) |
| Faction coordination | Single-pass conflict resolution |

---

## 10. Testing Strategy

### 10.1 Unit Tests

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_phase11_memory_continuity.py` | 651 | All memory classes |
| `test_phase12_planning_intent.py` | 603 | All planning classes |
| `test_phase13_23_systems.py` | 1,101 | Integration across all modules |

### 10.2 Test Categories

| Category | Description |
|----------|-------------|
| Construction | State objects created with defaults and explicit values |
| Serialization | Roundtrip: `to_dict()` → `from_dict()` → equivalent state |
| Bounds | Overflow behavior, value clamping |
| Decay | Salience/credibility degradation over time |
| Retrieval | Scoring algorithm accuracy |
| Influence | Trust/fear modifier computation |
| Goals | Goal generation from beliefs |
| Plans | Plan construction from goals |
| Interruption | Interrupt detection and replanning triggers |
| Companions | Companion plan alignment |
| Factions | Role assignment and conflict resolution |
| Determinism | State equivalence and normalization |

---

## 11. Design Rationale

### 11.1 Why Bounded State?

Unbounded memory causes:
- **Memory leaks** over long sessions
- **Non-deterministic behavior** from accumulated state
- **Performance degradation** as collections grow

Bounded state guarantees:
- **Predictable memory usage**
- **Deterministic replay** (critical for save/load)
- **Consistent performance**

### 11.2 Why Determinism Validators?

Determinism is essential for:
- **Save/load parity**: Reloaded state must match pre-save state
- **Replay debugging**: Same inputs → same outputs
- **Simulation integrity**: Divergent state breaks game logic

### 11.3 Why Facade Pattern?

Both `MemoryContinuitySystem` and the implicit planning facade:
- **Simplify integration**: Single entry point vs. 8+ classes
- **Encapsulate complexity**: Callers don't manage sub-objects directly
- **Enable testing**: Facade can be mocked or stubbed

### 11.4 Why Plan Templates?

Templates provide:
- **Goal-specific behavior**: Different goals have different step sequences
- **Extensibility**: New goal types → new templates
- **Predictability**: Limited step count (max 5) ensures bounded execution

---

## 12. Future Work

| Area | Proposed Improvement |
|------|---------------------|
| Memory summarization | LLM-based summary generation for compressed memories |
| Cross-NPC memory sharing | Shared world memories influencing multiple NPCs |
| Plan optimization | Utility-based plan selection |
| Event-driven replanning | Reactive replanning on world state changes |
| Memory learning | Salience adjustment based on retrieval success |
| Faction coordination UI | GM visibility into faction plan alignment |

---

## 13. Appendix: Constants Reference

### Memory System

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_SHORT_TERM` | 20 | Maximum dialogue turns |
| `MAX_LONG_TERM` | 200 | Maximum actor memory entries |
| `MAX_WORLD_PER_ENTITY` | 50 | Max world events per entity |
| `MAX_RUMORS` | 30 | Maximum tracked rumors |
| `DECAY_WINDOW` | 10 | Ticks before salience decay |

### Planning System

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_ACTIVE_GOALS` | 5 | Maximum concurrent goals |
| `MAX_COMPLETED_GOALS` | 20 | Maximum completed goal history |
| `MAX_PLAN_STEPS` | 5 | Maximum steps per plan |
| `MAX_GLOBAL_OBJECTIVES` | 10 | Maximum global objectives |

---

## 14. Appendix: Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Memory bounds exceeded | Medium | Validators + normalization enforce compliance |
| Plan execution divergence | Low | Step-by-step advancement is stateless |
| Companion plan misalignment | Low | Derived deterministically from leader plan |
| Serialization incompatibility | Low | Versioned save packaging handles migration |
| Performance under load | Medium | All collections bounded; O(n) operations on bounded sets |