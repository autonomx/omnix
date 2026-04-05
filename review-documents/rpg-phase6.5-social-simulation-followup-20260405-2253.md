# Phase 6.5 — Social Simulation Follow-up Patches

**Date:** 2026-04-05 22:53  
**Test Result:** 62 passed ✅

## Changes Applied from User Feedback

### 1. `world_simulation.py` — Enhanced betrayal reputation effects

Added reciprocal reputation updates when betrayal occurs:

```python
if typ == "betrayal":
    if source_id and target_id:
        reputation.update(source_id, target_id, "hostility", 0.40)
        reputation.update(target_id, source_id, "trust", -0.40)
        # New: target also feels hostility and fear toward betrayer
        reputation.update(target_id, source_id, "hostility", 0.20)
        reputation.update(target_id, source_id, "fear", 0.10)
```

### 2. `world_scene_generator.py` — Scene-level social context

Added social context attachment to each scene in `generate_scenes_from_simulation()`:

```python
# Phase 6.5: attach scene-level social context
social_state = state.get("social_state") or {}
scene["active_rumors"] = [dict(item) for item in (state.get("active_rumors") or [])[:3]]
scene["active_alliances"] = [
    dict(item) for item in (social_state.get("alliances") or [])
    if item.get("status") == "active"
][:3]
scene["faction_positions"] = {
    key: dict(value)
    for key, value in sorted((social_state.get("group_positions") or {}).items())
}
```

### 3. `world_scene_narrator.py` — Social context in NPC prompts

Added `_attach_social_context()` helper and social context injection into NPC reaction prompts:

- `rumor_info` — Rumors in circulation
- `alliance_info` — Active alliances
- `faction_position_info` — Faction positions toward player

These are included in the NPC reaction prompt to allow context-aware responses.

### Review Document

- `review-documents/rpg-phase6.5-social-simulation-20260405-2248.md` — Initial implementation review
- `review-documents/rpg-phase6.5-social-simulation-20260405-2248.diff` — Initial diff
- `review-documents/rpg-phase6.5-social-simulation-followup-20260405-2252.diff` — Follow-up diff
- `review-documents/rpg-phase6.5-social-simulation-followup-20260405-2253.md` — This follow-up review