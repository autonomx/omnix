# RPG Design Implementation - TIER 5: Experience Orchestration

**Date:** 2026-04-01 12:11  
**Design Reference:** `rpg-design.txt` - TIER 5: Experience Orchestration  
**Status:** Complete - All 25 tests passing  

---

## Overview

This implementation adds **TIER 5: Experience Orchestration** from the RPG design specification, which introduces three systems that transform the narrative from flat event reporting into a dynamic, emotionally engaging story experience:

1. **AI Director (Tension Engine)** - Controls WHAT matters
2. **Dialogue Engine (Belief-Driven Dialogue)** - Controls HOW characters speak
3. **Pacing Controller (Narrative Length Control)** - Controls WHEN/amount

---

## Files Created

### 1. `src/app/rpg/narrative/ai_director.py`
**Purpose:** Controls narrative tension and event shaping over time.

**Key Features:**
- Sine wave tension oscillation (0.0 to 1.0) over configurable period
- High tension (0.7-1.0): Prioritizes combat, danger, dramatic events
- Mid tension (0.3-0.7): Balanced mix of events
- Low tension (0.0-0.3): Prioritizes calm, dialogue, exploration events
- Manual tension override for story-driven moments

**Public API:**
- `update()` - Advance one tick and compute tension
- `filter_events(events)` - Select events based on current tension
- `set_tension(value)` - Manually set tension level
- `reset()` - Reset to initial state

**Lines:** 196

### 2. `src/app/rpg/narrative/dialogue_engine.py`
**Purpose:** Generates NPC dialogue based on beliefs, relationships, and emotional state.

**Key Features:**
- Six dialogue tones: hostile, friendly, cautious, neutral, fearful, respectful
- Template-based generation with 5 variations per tone
- Integration with MemoryManager for belief retrieval
- BeliefSystem compatibility for relationship-aware dialogue
- Self-directed dialogue support
- Standalone operation mode with manual belief injection

**Public API:**
- `generate_dialogue(speaker, target)` - Generate dialogue line
- `inject_beliefs(beliefs)` - Manual belief injection for standalone mode

**Tone Inference Logic:**
- hostile: believe value < -0.3
- respectful: belief value > 0.5
- friendly: belief value > 0.3
- cautious: -0.3 to -0.1
- neutral: no strong beliefs

**Lines:** 290

### 3. `src/app/rpg/narrative/pacing_controller.py`
**Purpose:** Controls narrative length and density based on tension level.

**Key Features:**
- Fast pace (tension > 0.7): 60 words, punchy, action-focused
- Medium pace (tension 0.3-0.7): 100 words, balanced description
- Slow pace (tension < 0.3): 150 words, rich description
- Sentence boundary trimming (avoids cutting sentences mid-way)
- Density-based adjustment for fine-grained control

**Public API:**
- `adjust(text, tension)` - Adjust narrative length
- `compute_target_length(tension)` - Get target word count
- `adjust_density(text, tension, min_words)` - Fine-grained density control

**Lines:** 196

### 4. `src/tests/unit/rpg/test_tier5_experience_orchestration.py`
**Purpose:** Comprehensive unit and integration tests for all TIER 5 systems.

**Test Coverage:**
- 25 tests total, all passing
- 9 tests for AIDirector
- 7 tests for DialogueEngine
- 5 tests for PacingController
- 4 integration tests

**Lines:** 283

---

## Files Modified

### 1. `src/app/rpg/core/player_loop.py`
**Changes:**
- Added imports for `AIDirector`, `DialogueEngine`, `PacingController`
- Added constructor parameters: `ai_director`, `dialogue_engine`, `pacing_controller`
- Auto-creation of default `AIDirector` and `PacingController` instances
- Updated pipeline: AI Director shapes events after focus selection
- Updated pipeline: Pacing Controller adjusts narration output
- Updated pipeline documentation (9 steps instead of 7)
- Added `reset()` call for AI Director

**Pipeline Before:**
```
1. Input → 2. Inject → 3. Tick → 4. Convert → 5. Select → 6. Scene → 7. Narrate
```

**Pipeline After:**
```
1. Input → 2. Inject → 3. Tick → 4. Convert → 5. Select → 6. AI Director → 7. Scene → 8. Narrate → 9. Pacing
```

**Lines Changed:** +38

### 2. `src/app/rpg/narrative/__init__.py`
**Changes:**
- Added exports: `AIDirector`, `DialogueEngine`, `PacingController`
- Updated module docstring with TIER 5 architecture
- Updated architecture diagram

**Lines Changed:** +14

### 3. `src/app/rpg/narrative/narrative_generator.py`
**Changes:**
- Added `dialogue_engine` constructor parameter
- Added `generate_with_dialogue()` method for dialogue integration
- Added `_generate_with_llm_and_dialogue()` for LLM-enhanced dialogue
- Updated `_generate_with_templates()` to accept optional dialogue lines
- Updated template generation to merge dialogue with narrative

**New Methods:**
- `generate_with_dialogue(events, scene_context)` - Generate narrative with belief-driven dialogue
- `_generate_with_llm_and_dialogue(events, scene_context, dialogue_lines)` - LLM generation with dialogue

**Lines Changed:** +108

---

## Code Diff Summary

```
Files Changed: 7
New Files: 4
Modified Files: 4
Total Lines Added: ~850
Tests: 25 passing
```

### New Files:
- `src/app/rpg/narrative/ai_director.py` (196 lines)
- `src/app/rpg/narrative/dialogue_engine.py` (290 lines)
- `src/app/rpg/narrative/pacing_controller.py` (196 lines)
- `src/tests/unit/rpg/test_tier5_experience_orchestration.py` (283 lines)

### Modified Files:
- `src/app/rpg/core/player_loop.py` (+38 lines)
- `src/app/rpg/narrative/__init__.py` (+14 lines)
- `src/app/rpg/narrative/narrative_generator.py` (+108 lines)

---

## Architecture Integration

```
Events
  ↓
Importance (NarrativeDirector)
  ↓
Tension (AIDirector) ← oscillates over time
  ↓
Scene Context (SceneManager)
  ↓
Dialogue (DialogueEngine) ← based on beliefs
  ↓
Narrative (NarrativeGenerator)
  ↓
Pacing (PacingController) ← adjusts length
  ↓
Narrative Output
```

---

## Design Compliance

### From rpg-design.txt

1. **AI Director (Tension Engine)** ✅
   - Sine wave tension computation
   - Event filtering based on tension level
   - High tension → combat, danger
   - Low tension → calm, dialogue
   - Integration with PlayerLoop

2. **Belief-Driven Dialogue System** ✅
   - Dialogue based on NPC beliefs
   - Tone inference from relationship values
   - Template-based generation (enhanced beyond spec)
   - MemoryManager integration
   - Self-directed dialogue (bonus feature)

3. **Narrative Pacing Controller** ✅
   - Length adjustment based on tension
   - Fast pace → shorter text (60 words)
   - Slow pace → longer text (150 words)
   - Integration with PlayerLoop output

---

## Test Results

```
25 passed in 0.08s

TestAIDirector:
  - test_initial_state ✅
  - test_update_increases_tick ✅
  - test_tension_oscillates ✅
  - test_filter_events_high_tension ✅
  - test_filter_events_low_tension ✅
  - test_filter_events_empty ✅
  - test_set_tension ✅
  - test_set_tension_clamped ✅
  - test_reset ✅

TestDialogueEngine:
  - test_generate_dialogue_no_memory ✅
  - test_generate_dialogue_self ✅
  - test_different_speakers_different_dialogue ✅
  - test_hostile_tone_from_beliefs ✅
  - test_friendly_tone_from_beliefs ✅
  - test_belief_system_integration ✅
  - test_no_beliefs_returns_neutral ✅

TestPacingController:
  - test_fast_pace_shortens_output ✅
  - test_slow_pace_allows_longer_output ✅
  - test_medium_pace ✅
  - test_empty_text ✅
  - test_compute_target_length ✅

TestTier5Integration:
  - test_tension_affects_output_length ✅
  - test_ai_director_filters_events_for_pacing ✅
  - test_player_loop_with_tier5_systems ✅
  - test_full_pipeline_with_mock_events ✅
```

---

## Usage Examples

### Basic Usage
```python
from rpg.narrative import AIDirector, DialogueEngine, PacingController

# Create TIER 5 systems
ai_director = AIDirector(period=10)
pacing = PacingController()
dialogue = DialogueEngine(memory_manager)

# In game loop
ai_director.update()
tension = ai_director.tension  # 0.0 to 1.0

# Filter events by tension
filtered_events = ai_director.filter_events(all_events)

# Adjust narration length
final_narration = pacing.adjust(raw_narration, tension)
```

### PlayerLoop Integration
```python
from rpg.core.player_loop import PlayerLoop
from rpg.narrative import AIDirector, PacingController, DialogueEngine

loop = PlayerLoop(
    world=world,
    director=director,
    scene_manager=scene_manager,
    narrator=generator,
    ai_director=AIDirector(period=10),
    dialogue_engine=DialogueEngine(memory_manager),
    pacing_controller=PacingController(),
)

result = loop.step("I attack the guard")
# result["narration"] is automatically tension-shaped and pace-adjusted
```

### Dialogue Generation
```python
from rpg.narrative import DialogueEngine, NarrativeGenerator

# Create generator with dialogue integration
generator = NarrativeGenerator(
    llm=my_llm,
    style="cinematic",
    dialogue_engine=dialogue_engine,
)

# Generate with dialogue
narration = generator.generate_with_dialogue(events, scene_context)
```

---

## Key Behavioral Changes

### Before TIER 5:
- Events → Narration (flat, uniform)
- Same output length regardless of scene intensity
- No tension or pacing variation
- Generic NPC dialogue

### After TIER 5:
- Events → Importance → Tension → Dialogue → Pacing → Narration
- Dynamic output length matching scene intensity
- Natural story rhythm (action/calm alternation)
- Belief-driven NPC dialogue with emotional grounding
- Fast scenes = sharp writing
- Slow scenes = rich description

---

## Notes

- All new modules are fully backward compatible
- Default AIDirector and PacingController are created if not provided
- DialogueEngine is optional - systems work without it
- No breaking changes to existing PlayerLoop or NarrativeGenerator APIs
- All existing tests continue to pass