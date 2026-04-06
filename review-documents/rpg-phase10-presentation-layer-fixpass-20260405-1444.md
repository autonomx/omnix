# Phase 10 — Presentation Layer Fix Pass

**Date:** 2026-04-05 14:44
**Status:** All 32 tests passing (was 30/32)

## Problem

Two tests were failing:
- `test_personality_profile_lazy_creation` (unit)
- `TestPresentationRegression.test_personality_profile_lazy_creation` (regression)

Both tests expected that calling `get_actor_personality_profile(simulation_state, "npc_new", "New NPC")` would mutate the original `simulation_state` dict to include the new NPC's profile, so that `profiles["npc_new"]` would be accessible after the call.

The root cause was in `ensure_personality_state()` — it was creating copies of nested dicts (`presentation_state`, `personality_state`, `profiles`) instead of mutating the original simulation state in place. This meant that when `get_actor_personality_profile` called `ensure_personality_state`, the returned dict had the personality state, but the original `simulation_state` passed by the caller was not mutated.

## Fix

Modified `ensure_personality_state()` in `src/app/rpg/presentation/personality_state.py` to:

1. Use `setdefault()` on the original dict instead of creating copies
2. Validate types before using `setdefault` to handle edge cases
3. Mutate the original `simulation_state` in place

Also updated `get_actor_personality_profile()` to use `setdefault()` consistently for lazy profile creation.

### Key Changes

**Before:**
```python
def ensure_personality_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)  # Creates a copy!
    presentation_state = _safe_dict(simulation_state.get("presentation_state"))  # Another copy!
    # ...
```

**After:**
```python
def ensure_personality_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state, dict):
        simulation_state = {}
    presentation_state = simulation_state.setdefault("presentation_state", {})
    if not isinstance(presentation_state, dict):
        presentation_state = simulation_state["presentation_state"] = {}
    personality_state = presentation_state.setdefault("personality_state", {})
    if not isinstance(personality_state, dict):
        personality_state = presentation_state["personality_state"] = {}
    # ... mutates in place
```

Additionally, `get_actor_personality_profile()` was hardened with the same defensive pattern for all three nested levels:

```python
presentation_state = simulation_state.setdefault("presentation_state", {})
if not isinstance(presentation_state, dict):
    presentation_state = simulation_state["presentation_state"] = {}

personality_state = presentation_state.setdefault("personality_state", {})
if not isinstance(personality_state, dict):
    personality_state = presentation_state["personality_state"] = {}

profiles = personality_state.setdefault("profiles", {})
if not isinstance(profiles, dict):
    profiles = personality_state["profiles"] = {}
```

This ensures that even if a future caller bypasses `ensure_personality_state()`, the defensive checks in `get_actor_personality_profile()` will still repair bad shapes.

## Test Results

```
32 passed in 9.40s
```

All unit, functional, and regression tests for Phase 10 now pass.

## Files Changed

- `src/app/rpg/presentation/personality_state.py` — Fixed `ensure_personality_state()` and `get_actor_personality_profile()` to mutate state in place

## Diff

See `review-documents/rpg-phase10-presentation-layer-fixpass-20260405-1444.diff`