# RPG Phase 1 Combat Lifecycle Status

Date: 2026-05-30
Branch: `rpg`
Feature branch: `rpg-pr1-combat-lifecycle-foundation`

## PR.1 — Combat Lifecycle Foundation

Status: implemented for local validation.

## Goal

Add the first deterministic lifecycle contract around the existing fast combat delta without changing damage resolution or provider behavior.

This is a foundation step only. It does not yet implement full enemy AI, hit/miss/crit, armor, XP resolution, loot resolution, companion actions, or multiple enemies.

## Added Contracts

### `combat_lifecycle`

Schema: `combat_lifecycle_v1`

Fields:

- `source`
- `initiative`
- `enemy_turn`
- `combat_log`
- `progression_hooks`

### `initiative`

Schema: `combat_initiative_v1`

Fields:

- `order`
- `active_actor_id`
- `next_actor_id`
- `round_index`
- `turn_phase`

Current behavior:

- Player action is recorded as current active actor.
- Enemy is marked as next actor when combat continues.
- Turn phase becomes `awaiting_enemy_turn` when enemy HP remains.
- Turn phase becomes `combat_complete` when enemy is defeated.

### `enemy_turn`

Schema: `enemy_turn_skeleton_v1`

Fields:

- `pending`
- `actor_id`
- `reason`

Current behavior:

- Enemy turn is marked pending when combat continues.
- Enemy turn is not yet resolved in PR.1.

### `combat_log`

Schema: `combat_log_entry_v1`

Fields:

- `entry_id`
- `turn_index`
- `round_index`
- `phase`
- `actor_id`
- `actor_side`
- `target_id`
- `target_name`
- `target_side`
- `action_type`
- `hit`
- `damage_applied`
- `target_hp_before`
- `target_hp_after`
- `defeated`
- `combat_ended`
- `source`

### `progression_hooks`

Schema: `combat_progression_hooks_v1`

Fields:

- `xp_pending`
- `loot_pending`
- `resolved`
- `reason`

Current behavior:

- XP and loot are marked pending when the target is defeated.
- Actual XP and loot resolution is intentionally deferred to a later Phase 1 bundle.

## Files

- `src/app/rpg/session/combat_lifecycle.py`
- `src/app/rpg/session/interactive_fast_combat_result_hook.py`
- `src/tests/rpg/test_pr1_combat_lifecycle_foundation.py`

## Validation Targets

Run:

```powershell
python -m pytest `
  src/tests/rpg/test_pr1_combat_lifecycle_foundation.py `
  src/tests/rpg/test_pr02_fast_combat_presentation.py `
  src/tests/rpg/test_ce2121_fast_combat_narration_skip.py `
  src/tests/rpg/test_pr0_architecture_compliance.py `
  src/tests/rpg/test_ce213_runtime_harness_convergence.py `
  -q

ruff check `
  src/app/rpg/session/combat_lifecycle.py `
  src/app/rpg/session/interactive_fast_combat_result_hook.py `
  src/app/rpg/session/fast_combat_presentation.py `
  src/app/rpg/session/fast_combat_presentation_hook.py `
  src/app/rpg/session/__init__.py `
  src/tests/rpg/test_pr1_combat_lifecycle_foundation.py `
  src/tests/rpg/test_pr02_fast_combat_presentation.py `
  src/app/rpg/session/fast_combat_narration_skip.py `
  src/app/rpg/session/state_claim_audit.py
```

Then rerun:

```powershell
python src/tests/rpg/interactive_intent_matrix.py --live-provider
```

Expected:

- Matrix remains 8/8.
- Combat remains below 0.15s average.
- Combat LLM turn count remains 0.
- Combat transcript keeps correct damage narration.
- Combat transcript exposes `combat_lifecycle` and `combat_log` metadata.
