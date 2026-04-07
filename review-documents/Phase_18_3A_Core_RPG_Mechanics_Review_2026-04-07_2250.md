# Phase 18.3A — Core RPG Mechanics Grounding: Implementation Review

**Date:** 2026-04-07 22:50 UTC  
**Branch:** copilot/implement-all-phases-in-order  
**Tests:** 122 passed (4 unit suites, 1 functional, 1 regression)

---

## Summary

Phase 18.3A grounds the RPG system in stat-driven, deterministic mechanics. All player actions now route through an authoritative resolution engine; the LLM narrates outcomes but never decides hit/miss/damage/XP. Items have full combat stats, inventory is world-grounded, and dynamic world expansion is budget-controlled.

---

## Implementation Passes

### Pass 1 — Foundations (4 new files, 4 modified)
| File | Change |
|------|--------|
| `player/player_progression_state.py` | **NEW** — Canonical player stats, skills, XP, level-up, progression log (bounded 50) |
| `player/player_creation.py` | **NEW** — Point-buy character creation with validation |
| `items/item_stats.py` | **NEW** — Weapon/armor/shield classification, combat stat normalization |
| `items/generated_item_builder.py` | **NEW** — LLM item clamping to power bands by world tier + rarity |
| `player/player_scene_state.py` | Modified — Added progression, nearby_npc_ids, equipped slots, available_checks |
| `items/item_registry.py` | Modified — 7 weapon/armor items (rusty_sword → pistol_9mm), normalize_item_definition |
| `items/inventory_state.py` | Modified — Expanded stacks (combat_stats, equipment, quality, instance_id, durability), equip/unequip/find helpers |
| `player/__init__.py`, `items/__init__.py` | Modified — Updated exports |

### Pass 2 — Authoritative Mechanics (1 new file, 3 modified)
| File | Change |
|------|--------|
| `action_resolver.py` | **REWRITTEN** — 16 action types, resolve_attack_roll (hit/miss/crit/graze), resolve_noncombat_check (DC-based), weapon damage formula, defense rating, legacy wrapper |
| `items/world_items.py` | **NEW** — World item state: spawn/pickup/drop/list by location |
| `items/item_effects.py` | Modified — restore_resource, grant_status, spawn_loot effect types |
| `encounter/resolver.py` | Modified — resolve_combat_round routes through action_resolver |
| `encounter/encounter_resolver.py` | Modified — Deprecation header |

### Pass 3 — Active Path Wiring (1 new file, 5 modified)
| File | Change |
|------|--------|
| `player/player_xp_rules.py` | **NEW** — Deterministic XP formulas: enemy difficulty, quest rank, skill use, stat influence |
| `session/runtime.py` | Modified — ensure progression+world items, derive_action_candidates (keyword→action mapping), XP awarding in apply_turn, enriched bootstrap payload |
| `creator/world_scene_generator.py` | Modified — enrich_scene_with_world_state (present NPCs, items, available checks) |
| `creator/world_player_actions.py` | Modified — enrich_action_metadata (difficulty_tier, skill_id, xp_category) |
| `choice/consequence_engine.py` | Modified — build_reward_events (xp, items, reputation, skill xp) |
| `api/rpg_session_routes.py` | Modified — player_level, player_xp, player_skills, level_up, skill_level_ups in turn response |

### Pass 4 — Presentation/UI (7 modified)
| File | Change |
|------|--------|
| `presentation/speaker_cards.py` | Modified — build_nearby_npc_cards (dynamic scene-scoped NPC cards) |
| `presentation/memory_inspector.py` | Modified — build_memory_ui_summary (compact/important/recent/expanded) |
| `presentation/__init__.py` | Modified — Export build_nearby_npc_cards |
| `services/adventure_response_adapter.py` | Modified — Player stats/skills/level/XP/inventory/equipment/nearby/memory in bootstrap |
| `ai/world_scene_narrator.py` | Modified — apply_narration_emphasis (deterministic markdown bold for items, quests, damage, level-ups) |
| `api/rpg_player_routes.py` | Modified — 6 new endpoints: equip, unequip, drop, pickup, progression, allocate |
| `static/rpg/rpg.js` | Modified — buildTurnSummaryBanner, summarizeMemoryEntries, dedupeMemoryEntries, toggleMemoryPanel |

### Pass 5 — World Growth (1 new file, 2 modified)
| File | Change |
|------|--------|
| `creator/world_expansion.py` | **NEW** — Budget-controlled dynamic NPC/location/faction spawning with deterministic IDs |
| `creator/startup_pipeline.py` | Modified — mark_seed_origins, add_world_expansion_caps |
| `creator/world_simulation.py` | Modified — evaluate_world_expansion hook after major events/thread escalation |

---

## Test Coverage (122 tests)

| Suite | File | Tests | Type |
|-------|------|-------|------|
| Player Progression | test_phase183a_player_progression.py | 28 | Unit |
| Action Resolver | test_phase183a_action_resolver.py | 21 | Unit |
| Inventory/World | test_phase183a_inventory_world.py | 27 | Unit |
| XP/Memory/Expansion | test_phase183a_xp_memory_expansion.py | 22 | Unit |
| End-to-End Flows | test_phase183a_functional.py | 5 | Functional |
| Backward Compat | test_phase183a_regression.py | 19 | Regression |

**Key test categories:**
- Stat allocation valid/invalid, level-up thresholds, skill XP growth, bounded logs
- Melee hit/miss, weapon damage differences, stat affects damage, armor reduces damage
- Pickup→inventory, drop→world, equip/unequip updates, world item lifecycle
- Action awards XP/skill XP, level-up in payload, NPC cards change with scene
- Compact memory summary, duplicate collapse, expanded accessible
- Startup seeds preserved, dynamic growth bounded, deterministic generated IDs
- Legacy compatibility (old items, old inventory format, old resolve_action signature)
- Determinism (same seed = same outcome)
- Bounded state (progression log ≤50, inventory ≤50, stats ≤20, items clamped to power band)

---

## Design Rules Enforced

1. **Simulation decides outcomes** — LLM never determines hit/miss/damage/XP
2. **Every narrated item interaction matches state** — world_items grounding
3. **Every action maps to stats + skill** — 16 action types with stat/skill profiles
4. **Skill progression is use-based** — archery improves through bow use
5. **Generated item stats normalized and bounded** — power bands by world tier
6. **XP from structured sources only** — deterministic formulas from tags
7. **Nearby NPCs are scene-scoped** — known NPC registry separate from active cards

---

## Stats

- **24 files changed** (7 new, 17 modified)
- **~1,880 lines added**, ~8 lines removed
- **0 security issues** (CodeQL clean)
- **122/122 tests passing**
