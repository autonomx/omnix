# Phase 9.2 — Companion Intelligence Layer — Review Document

**Date:** 2026-04-05 13:25
**Status:** Implemented and Tested
**Engine Version:** phase_9_2
**Schema Version:** 6 (migrated from 5)

## Summary

This phase adds companion intelligence features including:
- Dynamic companion stats (HP, max_hp, loyalty, morale, status, equipment)
- Role-based deterministic companion AI
- Shared inventory consumption hooks
- Companion equipment management (set/clear)
- Save migration v5 → v6

## Files Changed

| File | Lines Changed | Description |
|------|---------------|-------------|
| `src/app/rpg/party/party_state.py` | +~200 | Added companion state management functions |
| `src/app/rpg/party/companion_ai.py` | +~80 | Replaced placeholder AI with deterministic behavior |
| `src/app/rpg/party/companion_effects.py` | NEW | Companion item/effect hooks |
| `src/app/rpg/party/__init__.py` | +~20 | Updated exports |
| `src/app/rpg/player/__init__.py` | +~10 | Added party view exports |
| `src/app/rpg/persistence/migrations/v5_to_v6.py` | NEW | Migration script |
| `src/app/rpg/persistence/migrations/__init__.py` | +4 | Added migration export |
| `src/app/rpg/persistence/migration_manager.py` | +3 | Added v5→v6 migration step |
| `src/app/rpg/persistence/save_schema.py` | +4 | Bumped version numbers |

## New API Functions

### Party State (`src/app/rpg/party/party_state.py`)
- `update_companion_hp(player_state, npc_id, delta)` — Update HP with clamping
- `update_companion_loyalty(player_state, npc_id, delta)` — Update loyalty [-1.0, 1.0]
- `update_companion_morale(player_state, npc_id, delta)` — Update morale [0.0, 1.0]
- `set_companion_status(player_state, npc_id, status)` — Set status enum
- `set_companion_equipment(player_state, npc_id, slot, item_id)` — Equip item
- `clear_companion_equipment(player_state, npc_id, slot)` — Unequip item
- `build_party_summary(player_state)` — Build UI/timeline summary
- `_normalize_companion(companion)` — Normalize companion dict (internal)

### Companion AI (`src/app/rpg/party/companion_ai.py`)
- `choose_companion_action(companion, encounter_state)` — Deterministic action selection
- `run_companion_turns(simulation_state, encounter_state)` — Execute companion actions (guard: skips resolved encounters)

### Companion Effects (`src/app/rpg/party/companion_effects.py`)
- `apply_party_item_to_companion(simulation_state, npc_id, item_id)` — Apply inventory item to companion

## Invariants

```python
0 <= hp <= max_hp
-1.0 <= loyalty <= 1.0
0.0 <= morale <= 1.0
status in {"active", "downed", "absent"}
len(unique npc_ids) == len(companions)
```

## Test Results

### Unit Tests (22 tests)
```
test_update_companion_hp_damage_does_not_go_below_zero    PASSED
test_update_companion_hp_heal_does_not_exceed_max         PASSED
test_update_companion_hp_sets_downed_when_zero            PASSED
test_update_companion_loyalty_clamps_upper                PASSED
test_update_companion_loyalty_clamps_lower                PASSED
test_update_companion_morale_clamps                       PASSED
test_set_companion_status                                 PASSED
test_set_and_clear_companion_equipment                    PASSED
test_choose_companion_action_hesitate_on_low_loyalty      PASSED
test_choose_companion_action_defend_on_low_hp             PASSED
test_choose_companion_action_attack_when_hostile          PASSED
test_choose_companion_action_heal_self_when_support_low_hp PASSED
test_run_companion_turns_does_not_run_on_resolved         PASSED
test_build_party_summary_empty_party                      PASSED
test_build_party_summary_with_companions                  PASSED
test_companions_deduplicated_on_ensure                    PASSED
test_add_companion_respects_max_size                      PASSED
test_get_active_companions_filters_downed                 PASSED
test_build_party_summary_returns_valid_shape              PASSED
test_companion_loyalty_updates_persist                    PASSED
test_migration_v5_to_v6_adds_fields                       PASSED
test_migration_manager_handles_v5                         PASSED

22 passed in 0.14s
```

## Review Checklist ✅

- [x] Migration v5→v6 adds all new fields to companions
- [x] Migration manager correctly processes v5 packages
- [x] HP clamped to [0, max_hp]
- [x] Loyalty clamped to [-1.0, 1.0]
- [x] Morale clamped to [0.0, 1.0]
- [x] Companion duplicates filtered on ensure_party_state
- [x] Resolved encounters do not run companion AI
- [x] Companion determinism via sorted npc_id
- [x] Equipment set/clear works correctly
- [x] Schema version bumped to 6
- [x] Engine version bumped to phase_9_2

## Known Issues / Notes

- Companion AI supports four action types: hesitate, defend, heal_self, attack, support
- Support role with healing potion triggers heal_self when HP < 60%
- Downed companions (HP <= 0) are excluded from active companions list
- Equipment slots are stored as dict with {slot: {item_id, qty}}