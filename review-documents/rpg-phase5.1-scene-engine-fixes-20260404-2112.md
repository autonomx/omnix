# Phase 5.1 — Scene Engine Critical Fixes

**Date:** 2026-04-04 21:12 UTC-7
**Status:** ✅ All 63 tests passing

---

## Overview

This patch addresses 4 critical issues identified in the Phase 5 review before entering AI-driven gameplay (Phase 6).

---

## Fixes Applied

### ❗ Fix 1: LLM Output Structural Enforcement

**Problem:** `parse_scene_response(text)` was best-effort parsing — would break with real LLM usage.

**Solution:** All prompts now enforce JSON output with explicit schema:

```python
# Scene response prompt
Respond ONLY in JSON format:
{
  "narrative": "...",
  "choices": [{"text": "..."}]
}

# NPC reaction prompt
Respond ONLY in JSON format:
{
  "reaction": "...",
  "dialogue": "...",
  "emotion": "...",
  "intent": "..."
}

# Choice prompt
Respond ONLY in JSON format:
{
  "choices": [
    {
      "text": "...",
      "type": "action|observe|dialogue|...",
      "action": {
        "type": "intervene_thread|...",
        "target_id": "..."
      }
    }
  ]
}
```

Parsers now attempt `json.loads()` first, falling back to text extraction for backward compatibility.

**Files changed:**
- `parse_scene_response()` — JSON-first parsing
- `parse_npc_reaction()` — JSON-first parsing
- `parse_choices()` — JSON-first parsing with action binding
- `build_npc_reaction_prompt()` — JSON output enforced
- `build_choice_prompt()` — JSON output enforced

---

### ❗ Fix 2: NPC Reactions Now Stateful

**Problem:** NPC reactions were stateless — no memory, beliefs, or relationships.

**Solution:** `build_npc_reaction_prompt()` now injects:

```python
npc_memory = npc.get("memory_summary", "")
npc_beliefs = npc.get("beliefs", {})
npc_relationships = npc.get("relationships", {})
```

Prompt now includes:
```
Recent memory: {npc_memory}
Current beliefs: {beliefs_info}
Relationships: {relationships_info}

Consider their memory, beliefs, and relationships when forming their reaction.
```

**Files changed:**
- `build_npc_reaction_prompt()` — added memory, beliefs, relationships injection

---

### ❗ Fix 3: Player Choices Connected to Action System

**Problem:** Generated choices were not mapped to `apply_player_action`.

**Solution:** Every choice now includes an `action` field:

```python
{
  "id": "choice_1",
  "text": "Take decisive action",
  "type": "action",
  "action": {
    "type": "intervene_thread",
    "target_id": "scene_001"
  }
}
```

**Files changed:**
- `parse_choices()` — now accepts `source` parameter for target binding
- `build_choice_prompt()` — includes action hooks and action mapping instructions
- `_simulate_choices()` — now includes action binding
- `_generate_choices()` — passes action hooks and source to prompt/parser

---

### ❗ Fix 4: Scene → Action Mapping

**Problem:** No binding between scenes and actions.

**Solution:** Scenes can now include `action_hooks`:

```python
scene = {
    "id": "scene_001",
    "title": "...",
    "action_hooks": [
        {"type": "intervene_thread", "target_id": "thr_x"},
        {"type": "escalate_conflict", "target_id": "thr_x"}
    ]
}
```

If no `action_hooks` provided, defaults are generated:
- `intervene_thread`
- `escalate_conflict`
- `observe_situation`

**Files changed:**
- `build_choice_prompt()` — accepts `action_hooks` parameter
- `_generate_choices()` — extracts and passes `action_hooks` from scene

---

## Test Results

```
63 passed in 0.25s
- 31 unit tests
- 10 functional tests
- 22 regression tests
```

All existing tests pass — backward compatibility maintained through fallback parsing.

---

## System Status After Fixes

| System | Status |
|--------|--------|
| Simulation | ✅ |
| World graph | ✅ |
| Incidents | ✅ |
| Scenes | ✅ |
| Player actions | ✅ |
| Narrative | ✅ |
| NPC reactions | ✅ (now stateful) |
| Choice → action binding | ✅ |
| Scene action hooks | ✅ |
| Narrative → simulation feedback | ⏳ (Phase 5.5) |

**Progress: ~90% of full AI RPG engine**

---

## Remaining Work (Phase 5.5+)

1. **Narrative → simulation feedback loop**
   - Extract signals from narrative
   - Generate consequences
   - Feed back into simulation

2. **Narrative effects system**
   - Narrative generates status effects
   - Effects influence world state
   - Effects persist across scenes

---

## Diff File

`review-documents/rpg-phase5.1-scene-engine-fixes-20260404-2112.diff`