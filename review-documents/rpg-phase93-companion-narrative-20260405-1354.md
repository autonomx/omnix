# Phase 9.3 — Companion Narrative Integration (Fix Pass)

**Date:** 2026-04-05 14:03
**Status:** Implemented, tested, and fix-hardened
**Tests:** 23 passed (8 unit + 6 functional + 9 regression)

## Summary

Phase 9.3 adds companion narrative integration to the RPG system:
- **Companion scene interjections** — deterministic, loyalty/morale-aware
- **Companion dialogue context** — narrative presence for dialogue payloads
- **Companion choice reactions** — loyalty/morale deltas from player choices
- **Bounded narrative history** — max 20 entries, oldest dropped first
- **Save migration v6 → v7** — adds narrative_state to party_state
- **Inspector/timeline visibility** — party state in tick diffs

## Key Guarantees

1. **Determinism**: Companion selection sorted by `npc_id` ensures same result across repeated calls
2. **No downed/absent narration**: Companions with `status="downed"` or `status="absent"` never appear in interjections or reactions
3. **Loyalty-aware stance**: Low loyalty (< -0.3) → resentful, low morale (< 0.3) → fearful, high both (> 0.6) → supportive
4. **Bounded history**: Narrative history capped at 20 entries; oldest removed first
5. **Builder/recorder separation**: Build functions are pure (no mutation); record functions explicitly mutate state

## Files Changed

### New Files
- `src/app/rpg/party/companion_narrative.py` — Core narrative module
- `src/app/rpg/persistence/migrations/v6_to_v7.py` — Save migration
- `src/tests/unit/rpg/test_phase93_companion_narrative.py` — Unit tests
- `src/tests/functional/test_phase93_companion_narrative_functional.py` — Functional tests
- `src/tests/regression/test_phase93_companion_narrative_regression.py` — Regression tests

### Modified Files
- `src/app/rpg/party/__init__.py` — Added narrative exports
- `src/app/rpg/player/player_party.py` — Added presence summary
- `src/app/rpg/persistence/migrations/__init__.py` — Registered v6_to_v7
- `src/app/rpg/persistence/migration_manager.py` — Added v6→v7 step
- `src/app/rpg/persistence/save_schema.py` — Bumped to v7, phase_9_3
- `src/app/rpg/analytics/tick_diff.py` — Added party keys to diff

## API Functions

| Function | Purpose |
|----------|---------|
| `build_companion_scene_context(simulation_state, scene_state)` | Build companion context for scene payloads |
| `build_companion_dialogue_context(simulation_state, dialogue_state)` | Build companion context for dialogue payloads |
| `choose_scene_interjections(simulation_state, scene_state)` | Deterministic interjections for active companions |
| `build_companion_scene_reactions(player_state, scene_state)` | Reaction summaries (omits downed/absent) |
| `apply_companion_choice_reactions(simulation_state, choice_payload)` | Apply loyalty/morale deltas from choice tags |
| `record_companion_narrative_event(player_state, event)` | Record event into bounded history |
| `build_party_narrative_summary(party_state)` | Summary for timeline/inspector display |
| `build_companion_presence_summary(player_state)` | Active companion presence with tone/loyalty/morale |

## Migration Details

**v6 → v7:**
- Adds `narrative_state` to `party_state` with keys: `history` ([]), `last_interjection` ({}), `last_scene_reactions` ([])
- Preserves all existing companion data
- Schema version: 6 → 7
- Engine version: `phase_9_2` → `phase_9_3`

## Test Coverage

### Unit Tests (8)
- `test_choose_scene_interjections_is_deterministic`
- `test_downed_companions_do_not_interject`
- `test_absent_companions_do_not_interject`
- `test_low_loyalty_companion_produces_resentful_tone`
- `test_build_companion_scene_reactions_skips_absent`
- `test_record_companion_narrative_event_is_bounded`
- `test_build_party_narrative_summary_returns_expected_keys`
- `test_build_companion_presence_summary_returns_expected_keys`

### Functional Tests (6)
- `test_build_player_party_view_returns_presence_summary`
- `test_build_companion_scene_context_returns_expected_keys`
- `test_build_companion_dialogue_context_returns_expected_keys`
- `test_record_narrative_event_updates_history`
- `test_build_companion_scene_reactions_omits_downed`
- `test_record_companion_narrative_event_keeps_history_bounded`

### Regression Tests (9)
- `test_companion_interjection_is_stable_across_repeated_calls`
- `test_interjection_order_is_deterministic_with_same_state`
- `test_v6_to_v7_migration_preserves_existing_companions`
- `test_v6_to_v7_migration_adds_narrative_state`
- `test_schema_version_and_engine_version_are_updated`
- `test_downed_companions_never_appear_in_reactions`
- `test_absent_companions_never_appear_in_reactions`
- `test_narrative_tone_reflects_loyalty_and_morale`
- `test_empty_state_does_not_crash_narrative_functions`

## Review Checklist

- [x] `choose_scene_interjections()` does not select downed/absent companions
- [x] Narrative history remains bounded (<= 20) after repeated scenes
- [x] Route payloads do not mutate state on read-only requests
- [x] Migration shape uses `package["state"]["simulation_state"]["player_state"]["party_state"]`
- [x] Schema version ends at 7, engine version matches phase_9_3
- [x] Builder/recorder separation maintained (builders are pure)
- [x] Determinism verified: sorted by npc_id, no unordered dict traversal

## Next Phase Recommendation

**Phase 10 — Presentation / Production Polish**
- Richer speaker cards / portrait hooks
- Stronger scene transitions
- More expressive companion interjection rendering
- Accessibility cleanup
- Final UX cohesion across dialogue, encounter, inventory, party, and inspector