# Phase 5 — LLM Scene Engine + NPC Behavior: Implementation Review

**Date:** 2026-04-04 21:07 UTC-7
**Status:** ✅ All 63 tests passing

---

## Overview

This implementation delivers Phase 5 of the RPG design specification: the LLM Scene Engine + NPC Behavior system. It transforms structured scene data into immersive narrative experiences with NPC reactions, dialogue, and player choices.

**Design Goal:** Turn `Scene → Narrative → NPC reactions → Dialogue → Player response` into a fully functional AI-driven RPG loop.

---

## Files Changed

### New Files
- `src/app/rpg/ai/world_scene_narrator.py` — Core narration engine (577 lines)
- `src/tests/unit/rpg/test_phase5_scene_narrator.py` — Unit tests (320 lines)
- `src/tests/functional/test_phase5_scene_narrator_functional.py` — Functional tests (277 lines)
- `src/tests/regression/test_phase5_scene_narrator_regression.py` — Regression tests (297 lines)

### Modified Files
- `src/app/rpg/ai/__init__.py` — Added Phase 5 exports
- `src/app/rpg/creator_routes.py` — Added `POST /api/rpg/scene/play` endpoint

---

## Architecture

### Data Models

**NPCReaction** (dataclass)
- `npc_id`: unique identifier
- `npc_name`: display name
- `reaction`: internal reaction text
- `dialogue`: spoken line
- `emotion`: emotional state (calm, tense, angry, etc.)
- `intent`: immediate intent (observe, act, confront, etc.)

**NarrativeResult** (dataclass)
- `narrative`: generated narrative text
- `choices`: list of player choice dicts
- `npc_reactions`: list of NPCReaction objects
- `dialogue_blocks`: list of dialogue block dicts
- `metadata`: tone, scene_id, counts

### Pipeline

```
Scene dict + State dict
    │
    ▼
build_scene_prompt() ──► LLM Gateway ──► parse_scene_response()
    │
    ▼
_build_npc_reactions() ──► build_npc_reaction_prompt() ──► parse_npc_reaction()
    │
    ▼
_generate_choices() ──► build_choice_prompt() ──► parse_choices()
    │
    ▼
NarrativeResult
```

### LLM Integration

The `SceneNarrator` class integrates with the existing `LLMGateway` pattern:
- When `llm_gateway` is provided, calls are routed through the deterministic boundary
- When `llm_gateway` is None (default), falls back to simulation mode
- Failed LLM calls gracefully fall back to simulation
- All behavior is testable without external dependencies

---

## API Changes

### New Endpoint: `POST /api/rpg/scene/play`

**Request body:**
```json
{
    "scene": {
        "id": "scene_001",
        "title": "The Dark Forest",
        "summary": "You enter a dense forest...",
        "actors": ["Guard", "Merchant"],
        "stakes": "Finding the hidden path",
        "location": "The Whispering Woods",
        "tension": "high"
    },
    "state": {
        "player_name": "Aldric",
        "genre": "dark fantasy"
    },
    "tone": "dramatic"
}
```

**Response:**
```json
{
    "success": true,
    "narrative": "The Dark Forest\n\nYou enter a dense forest...",
    "choices": [
        {"id": "choice_1", "text": "Take decisive action", "type": "action"},
        {"id": "choice_2", "text": "Observe the situation carefully", "type": "observe"},
        {"id": "choice_3", "text": "Speak with those present", "type": "dialogue"}
    ],
    "npc_reactions": [
        {"npc_id": "guard", "npc_name": "Guard", "dialogue": "We should act quickly.", "emotion": "tense", "intent": "act"},
        {"npc_id": "merchant", "npc_name": "Merchant", "dialogue": "This changes everything.", "emotion": "curious", "intent": "observe"}
    ],
    "dialogue_blocks": [
        {"speaker": "Guard", "npc_id": "guard", "text": "We should act quickly.", "emotion": "tense"},
        {"speaker": "Merchant", "npc_id": "merchant", "text": "This changes everything.", "emotion": "curious"}
    ],
    "metadata": {
        "tone": "dramatic",
        "scene_id": "scene_001",
        "npc_count": 2,
        "choice_count": 3
    }
}
```

---

## Test Coverage

### Unit Tests (31 tests)
- `TestBuildScenePrompt` — Scene prompt construction, tone, defaults
- `TestBuildNpcReactionPrompt` — NPC reaction prompt, truncation
- `TestBuildChoicePrompt` — Choice prompt with scene context
- `TestParseSceneResponse` — Response parsing, fallbacks
- `TestParseNpcReaction` — NPC reaction field extraction
- `TestParseChoices` — Numbered choice extraction
- `TestSceneNarrator` — Full narration pipeline, LLM gateway integration, fallback
- `TestPlayScene` — Service function dict output
- `TestDataclasses` — Default value verification

### Functional Tests (10 tests)
- Full scene narration with all options
- Actor dict format handling
- Multiple tone variations
- Empty actor lists
- NPC reaction limits
- Dialogue block generation
- Choice field requirements
- Response structure validation
- State reflection in output
- Graceful empty state handling

### Regression Tests (22 tests)
- Backward compatibility with legacy formats
- Response structure stability
- Edge cases (long titles, non-string actors, missing fields)
- Parser stability with various inputs
- Deterministic simulation behavior
- Repeated call consistency

**Total: 63 tests — ALL PASSING**

---

## Design Decisions

1. **Simulation-first**: All functionality works without LLM — tests are fast and deterministic
2. **Hash-based NPC simulation**: NPC reactions use `hash(npc_name)` for deterministic but varied output
3. **Graceful degradation**: LLM errors fall back to simulation, never crash
4. **Actor format flexibility**: Supports list, dict, or scalar actors
5. **Configurable NPC limit**: `max_npc_reactions` prevents runaway generation
6. **Separation of concerns**: Prompt builders, parsers, and narrator are independent
7. **Dataclass models**: Strong typing for reactions and results
8. **Service function**: `play_scene()` provides a simple dict-to-dict interface for routes

---

## Diff Summary

```
Files changed: 6
Lines added: ~1,471
Lines modified: ~15
New endpoint: 1
New test files: 3
```

---

## Review Notes

- The diff file `rpg-phase5-llm-scene-engine-20260404-2107.diff` contains full git diff output
- No breaking changes to existing code paths
- All new code follows project conventions
- LLM gateway integration uses existing `LLMGateway` pattern from Phase 5.6
- Frontend integration point: `POST /api/rpg/scene/play` returns structured data ready for display