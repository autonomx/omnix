# RPG Design Implementation — Narrative Layer (Steps 1-7)

**Date:** 2026-04-01 01:34 AM (America/Vancouver)
**Author:** Cline
**Status:** ✅ Complete — All 32 tests passing

---

## Overview

This implementation fulfills Steps 1-7 from `rpg-design.txt`, introducing the narrative layer that bridges the simulation engine with storytelling. Seven new/modified files were created:

| Step | File | Description | Status |
|------|------|-------------|--------|
| 1 | `narrative/narrative_event.py` | NarrativeEvent dataclass | ✅ New |
| 2 | `narrative/narrative_director.py` | NarrativeDirector for scoring | ✅ New |
| 3 | `narrative/scene_manager.py` | SceneManager for scene tracking | ✅ New |
| 4 | `narrative/narrative_generator.py` | LLM/template narrative generator | ✅ New |
| 5 | `core/player_loop.py` | PlayerLoop main game loop | ✅ New |
| 6 | `core/world_loop.py` | Event structure enhancement | ✅ Modified |
| 7 | `test_player_loop_integration.py` | Integration tests (32 tests) | ✅ New |

---

## Architecture

```
Player Input → PlayerLoop → World Tick → Narrative Director → SceneManager → Generator → Prose
                            ↓                                      ↓
                    NarrativeEvents                          Scene Context
```

### Data Flow

1. **Player Input** — Raw text from player ("I attack the guard")
2. **World Tick** — `WorldSimulationLoop.world_tick()` produces raw event dicts
3. **Event Conversion** — `NarrativeDirector.convert_events()` converts to `NarrativeEvent` objects with importance/emotion scores
4. **Focus Selection** — `NarrativeDirector.select_focus_events()` picks top events
5. **Scene Tracking** — `SceneManager.update_scene()` batches related events and tracks context
6. **Narration** — `NarrativeGenerator.generate()` produces immersive prose

---

## Code Diffs

### STEP 1: Narrative Event Model (`narrative/narrative_event.py`) — NEW FILE

Full file implementing the `NarrativeEvent` dataclass:

```python
@dataclass
class NarrativeEvent:
    """A narrative event with metadata for storytelling."""
    id: str
    type: str
    description: str
    actors: List[str] = field(default_factory=list)
    location: str | None = None
    importance: float = 0.5
    emotional_weight: float = 0.0
    tags: List[str] = field(default_factory=list)
    raw_event: Dict[str, Any] = field(default_factory=dict)
```

Key methods:
- `to_dict()` — Serialization for JSON/API
- `from_dict()` — Deserialization from raw data
- `narrative_priority()` — Combined importance + emotion score for sorting

---

### STEP 2: Narrative Director (`narrative/narrative_director.py`) — NEW FILE

Full file implementing event conversion and scoring:

```python
class NarrativeDirector:
    """Converts raw world events into scored NarrativeEvents."""
    
    IMPORTANCE_MODIFIERS: Dict[str, float] = {
        "combat": 0.3, "death": 0.5, "betrayal": 0.4, ...
    }
    EMOTION_WEIGHTS: Dict[str, float] = {
        "death": 1.0, "combat": 0.6, "critical_hit": 0.7, ...
    }
    
    def convert_events(self, world_events: List[Dict]) -> List[NarrativeEvent]:
        """Convert raw world events into narrative events."""
        
    def score_importance(self, event: Dict) -> float:
        """Score how narratively important an event is."""
        
    def score_emotion(self, event: Dict) -> float:
        """Score the emotional weight of an event."""
        
    def select_focus_events(self, events: List[NarrativeEvent], max_events: int = 5) -> List[NarrativeEvent]:
        """Select the most narratively significant events for focus."""
```

Design notes:
- Deterministic scoring (no LLM) for fast, predictable results
- Player involvement bonus (+0.2 importance)
- Multiple actor bonus (+0.1 importance)
- Event buffer for recent event queries

---

### STEP 3: Scene Engine (`narrative/scene_manager.py`) — NEW FILE

Full file implementing scene state tracking:

```python
@dataclass
class Scene:
    """An active scene being tracked by the SceneManager."""
    id: str
    location: str
    participants: List[str] = field(default_factory=list)
    recent_events: List[Dict[str, Any]] = field(default_factory=list)
    mood: str = "neutral"
    tick_started: int = 0
    event_count: int = 0

class SceneManager:
    """Manages the active scene and scene transitions."""
    
    MOOD_SCORES = {
        "combat": 1, "death": 2, "heal": -1, "speak": 0, ...
    }
```

Key features:
- Auto scene creation from first event
- Scene transition on location change
- Memory bounded (configurable max_events_per_scene)
- Mood system: neutral → calm → peaceful → tense → dark
- Scene history tracking (completed scenes)

---

### STEP 4: Narrative Generator (`narrative/narrative_generator.py`) — NEW FILE

Full file implementing narrative text generation:

```python
STYLE_PROMPTS: Dict[str, str] = {
    "cinematic": "Write in a cinematic, immersive style...",
    "dramatic": "Write in a dramatic style...",
    "literary": "Write in a literary style...",
    "minimal": "Write in a sparse, minimal style...",
    "first_person": "Write in first person...",
    "epic": "Write in an epic, mythic style...",
}

class NarrativeGenerator:
    """Converts narrative events into narrative prose text."""
    
    def generate(self, events: List[NarrativeEvent], scene_context: Dict) -> str:
        """Turn structured events into narrative text (main entry point)."""
        
    def generate_from_dicts(self, events: List[Dict], scene_context: Dict) -> str:
        """Generate narrative from raw event dicts (convenience wrapper)."""
```

Two modes:
1. **LLM mode** — Full LLM prompt with style guidance, event list, and scene context
2. **Template mode** — Fast fallback with event-type templates and narrative transitions

Robust error handling:
- LLM errors → template fallback
- Unknown event types → use description or empty

Word count trimming applied to both modes.

---

### STEP 5: Player Loop (`core/player_loop.py`) — NEW FILE

Full file implementing the main game loop:

```python
class PlayerLoop:
    """Main game loop connecting player input to narrative output."""
    
    def step(self, player_input: str) -> Dict[str, Any]:
        """Execute one complete game loop step.
        
        Pipeline:
        1. Convert player input to world event
        2. Inject player event into world
        3. Run world simulation tick
        4. Convert raw events to narrative events
        5. Select focus events for narration
        6. Update scene
        7. Generate narrative
        """
```

Adapter patterns:
- Flexible narrator interface (NarrativeGenerator, NarratorAgent, callable)
- Flexible world interface (world_tick(), tick(), or simulate_fn)
- Graceful fallbacks for missing dependencies

---

### STEP 6: World Loop Hook (`core/world_loop.py`) — MODIFIED

Small change at end of `world_tick()`:

```diff
        # [STEP 6 - Hook Into Existing World Loop]
        # Ensure events include structured fields for narrative conversion
        for e in tick_events:
            e.setdefault("description", e.get("type", "unknown event"))
            e.setdefault("actors", [])
```

This ensures all events from the world simulation have `description` and `actors` fields, making them compatible with the NarrativeDirector without requiring changes to existing world systems.

---

### STEP 7: Integration Tests (`test_player_loop_integration.py`) — NEW FILE

32 tests covering all components:

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestNarrativeEvent | 4 | Dataclass creation, serialization, priority |
| TestNarrativeDirector | 7 | Conversion, scoring, focus selection, buffer |
| TestSceneManager | 9 | Scene creation, transitions, mood, memory |
| TestNarrativeGenerator | 5 | Template generation, LLM fallback, word trim |
| TestPlayerLoop | 7 | Full pipeline, fallbacks, reset, simulate_fn |

**All 32 tests passing.**

---

## Changes Summary

### New Files (6)
1. `src/app/rpg/narrative/narrative_event.py` — 105 lines
2. `src/app/rpg/narrative/narrative_director.py` — 198 lines
3. `src/app/rpg/narrative/scene_manager.py` — 247 lines
4. `src/app/rpg/narrative/narrative_generator.py` — 267 lines
5. `src/app/rpg/core/player_loop.py` — 287 lines
6. `src/tests/unit/rpg/test_player_loop_integration.py` — 320 lines

### Modified Files (2)
1. `src/app/rpg/narrative/__init__.py` — Updated exports for new modules
2. `src/app/rpg/core/world_loop.py` — Added event description/actors defaults

### Total Lines Added: ~1,424 lines

---

## Design Compliance

| Requirement | rpg-design.txt Step | Implementation |
|------------|-------------------|----------------|
| Narrative Event Model | STEP 1 | ✅ NarrativeEvent dataclass with all fields |
| Narrative Director | STEP 2 | ✅ convert_events + score_importance + score_emotion + select_focus_events |
| Scene Engine | STEP 3 | ✅ SceneManager with context, transitions, mood |
| Narrative Generator | STEP 4 | ✅ LLM + template generation with styling |
| Player Loop | STEP 5 | ✅ Full pipeline from input to narration |
| World Loop Hook | STEP 6 | ✅ Event field enhancement in world_tick() |
| Integration Test | STEP 7 | ✅ 32 tests, all passing |

---

## Key Design Decisions

1. **Deterministic Scoring** — Importance and emotion weights use lookup tables, not LLM calls, for speed and predictability.

2. **Narrative Priority** — Combined formula `(importance × 0.6) + (emotional_weight × 0.4)` provides balanced event ranking.

3. **Scene Memory Bounds** — Both SceneManager and NarrativeDirector use configurable buffer limits to prevent memory growth during long sessions.

4. **Template Fallback** — NarrativeGenerator always falls back to template generation if LLM is unavailable or errors, ensuring system resilience.

5. **Adapter Pattern** — PlayerLoop adapts to any world simulation (world_tick, tick, or simulate_fn) and any narrator (NarrativeGenerator, NarratorAgent, or callable).

---

## Test Results

```
============================= test session starts =============================
collected 32 items

TestNarrativeEvent: 4 passed
TestNarrativeDirector: 7 passed
TestSceneManager: 9 passed
TestNarrativeGenerator: 5 passed
TestPlayerLoop: 7 passed

============================= 32 passed in 0.11s ==============================
```

---

## Future Work

1. **LLM Integration** — Replace mock LLM with actual LLM service (OpenAI API or local model) for rich narrative generation. The `NarrativeGenerator` already accepts any callable with signature `llm(prompt: str) -> str`, making integration straightforward.
2. **Performance Benchmarks** — Add benchmarks for tick throughput with various actor counts. Test with 10, 50, 100 NPCs to identify bottlenecks in event scoring and focus selection.
3. **Event Persistence** — Consider adding NarrativeEvent serialization to database for save/load functionality. The `to_dict()`/`from_dict()` methods already provide clean JSON serialization.
4. **Multi-language Narration** — Add locale support for narrative translation. Could integrate with existing TTS system (`parakeet_stt_server.py`) for voice output in multiple languages.
5. **Voice Generation** — Hook up TTS for spoken narration. The project already has TTS infrastructure (`parakeet_stt_server.py`, `start_faster_qwen3_tts.bat`) that could be extended for narration output.
