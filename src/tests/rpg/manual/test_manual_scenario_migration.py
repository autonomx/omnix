from __future__ import annotations

from tests.rpg.manual.runner import build_service_scenarios
from tests.rpg.manual.scenarios.expected_legacy_names import (
    EXPECTED_LEGACY_SCENARIO_NAMES,
)
from tests.rpg.manual.scenarios.expected_memory_l7_l9_names import (
    EXPECTED_MEMORY_L7_L9_SCENARIO_NAMES,
)


def test_manual_scenario_migration_audit():
    """Audit migration by comparing expected legacy names vs new modular registry.

    This test ensures we don't silently drop or add scenarios during refactoring.
    It compares against the exact 145 old scenario names from manual_llm_transcript_old.py.
    """

    # Load expected legacy names (exact 145 from old monolith)
    all_old_names = EXPECTED_LEGACY_SCENARIO_NAMES
    print(f"Expected legacy scenario count: {len(all_old_names)}")

    # Load new scenarios (modular)
    new_scenarios = build_service_scenarios()
    new_names = set(new_scenarios.keys())

    # All 145 scenarios should be present
    assert len(new_names) == 145, f"Expected 145 scenarios, found {len(new_names)}"

    # Check that Bundle A scenarios have been successfully ported
    bundle_a_scenarios = {"lodging_success", "shop_success", "blocked_purchase", "paid_info"}
    missing_bundle_a = bundle_a_scenarios - new_names
    assert not missing_bundle_a, f"Bundle A scenarios not found in new registry: {missing_bundle_a}"

    # Check that Bundle B scenarios have been successfully ported
    bundle_b_scenarios = {
        "ambient_conversation", "autonomous_conversation", "conversation_discusses_event",
        "conversation_discusses_quest", "player_invited_conversation", "npc_replies_after_player_join",
        "player_requests_backed_quest_topic", "player_requests_unbacked_topic",
        "npc_response_uses_social_state", "rumor_seed_from_conversation", "rumor_signal_expires"
    }
    missing_bundle_b = bundle_b_scenarios - new_names
    assert not missing_bundle_b, f"Bundle B scenarios not found in new registry: {missing_bundle_b}"

    # Check that Bundle C scenarios have been successfully ported
    bundle_c_scenarios = {
        "npc_goal_influences_response_style", "npc_biography_shapes_bran_dialogue", "npc_biography_shapes_mira_dialogue",
        "npc_biography_blocks_unbacked_secret", "npc_roleplay_fallback_validation", "npc_history_records_player_reply",
        "npc_reputation_changes_response_style", "conversation_director_selects_biography_relevant_topic",
        "npc_schedule_populates_tavern_presence", "director_uses_presence_runtime", "scene_activity_uses_present_npc",
        "npc_knowledge_records_backed_quest_discussion", "npc_dialogue_recalls_prior_player_reply",
        "scene_continuity_tracks_recent_topic", "quest_access_backed_topic_partial_or_normal",
        "quest_access_unbacked_topic_denied", "player_reputation_polite_reply_improves_trust",
        "player_reputation_unbacked_pressure_adds_annoyance", "quest_rumor_seeded_from_backed_access",
        "quest_rumor_not_seeded_from_unbacked_claim", "npc_referral_suggests_present_relevant_npc",
        "consequence_signals_emit_bounded_social_signal"
    }
    missing_bundle_c = bundle_c_scenarios - new_names
    assert not missing_bundle_c, f"Bundle C scenarios not found in new registry: {missing_bundle_c}"

    # Check that Bundle D scenarios have been successfully ported
    bundle_d_scenarios = {
        "npc_file_profile_bran_loaded", "npc_evolution_bran_loses_tavern", "npc_evolution_reputation_threshold_trust",
        "npc_party_eligibility_after_bran_loses_tavern", "companion_join_intent_requires_player_request",
        "companion_acceptance_adds_bran_to_party", "npc_arc_continuity_tracks_bran_revenge_arc",
        "companion_presence_follow_party_aware_turns", "companion_commands_roles_boundaries",
        "companion_memory_personality_loyalty", "companion_quest_hooks_personal_arc_progression",
        "multi_companion_party_system", "dynamic_npc_profiles_character_cards",
        "dynamic_npc_profile_llm_draft_approval", "character_card_ui_profile_portrait_integration",
        "dynamic_npc_profile_generation_modes"
    }
    missing_bundle_d = bundle_d_scenarios - new_names
    assert not missing_bundle_d, f"Bundle D scenarios not found in new registry: {missing_bundle_d}"

    # Check that Bundle E scenarios have been successfully ported
    bundle_e_scenarios = {
        "general_interaction_runtime", "inventory_item_interaction_runtime", "inventory_item_model_stacking_weight_encumbrance",
        "inventory_containers_durability_repair", "inventory_consumables_ammo_equipment_stats",
        "inventory_crafting_recipes_materials", "inventory_loot_merchant_economy", "companion_inventory_auto_equip"
    }
    missing_bundle_e = bundle_e_scenarios - new_names
    assert not missing_bundle_e, f"Bundle E scenarios not found in new registry: {missing_bundle_e}"

    # Check that Bundle F scenarios have been successfully ported
    bundle_f_scenarios = {
        "combat_ui_payload_smoke", "combat_state_initiative_turn_gating", "combat_actions_damage_defeat",
        "companion_combat_participation", "enemy_combat_ai_party_defeat", "combat_llm_attack_narration",
        "combat_llm_defeat_narration", "combat_llm_party_defeat_narration", "combat_victory_grants_xp_once",
        "combat_flee_grants_no_loot_or_xp", "combat_post_victory_returns_to_world_actions",
        "combat_post_combat_clears_temporary_modifiers", "combat_victory_generates_loot_once",
        "combat_party_defeat_grants_no_player_loot", "manual_party_defeat_text_artifact_has_body"
    }
    missing_bundle_f = bundle_f_scenarios - new_names
    assert not missing_bundle_f, f"Bundle F scenarios not found in new registry: {missing_bundle_f}"

    # Check that Bundle G scenarios have been partially ported (infrastructure in place)
    # Note: Many Bundle G scenarios still need to be fully migrated, but the framework is ready
    bundle_g_sample_scenarios = {
        "combat_ui_payload_smoke", "combat_state_initiative_turn_gating", "combat_actions_damage_defeat",
        "companion_combat_participation", "enemy_combat_ai_party_defeat", "combat_llm_attack_narration",
        "combat_defend_reduces_next_incoming_attack", "combat_use_item_consumes_turn_and_applies_effect",
        "combat_flee_success_or_failure_is_authoritative", "combat_critical_hit_applies_bleeding",
        "combat_heavy_hit_applies_stunned", "combat_bleeding_ticks_damage"
    }
    missing_bundle_g_sample = bundle_g_sample_scenarios - new_names
    assert not missing_bundle_g_sample, f"Sample Bundle G scenarios not found in new registry: {missing_bundle_g_sample}"

    # Log progress on Bundle G migration
    all_bundle_g_scenarios = {
        "combat_defend_reduces_next_incoming_attack", "combat_use_item_consumes_turn_and_applies_effect",
        "combat_flee_success_or_failure_is_authoritative", "combat_critical_hit_applies_bleeding",
        "combat_heavy_hit_applies_stunned", "combat_bleeding_ticks_damage", "combat_stabilize_downed_companion",
        "combat_heal_downed_companion_revives", "combat_enemy_targets_low_hp_companion",
        "combat_enemy_avoids_downed_target", "combat_enemy_defends_when_low_hp_but_not_fleeing",
        "combat_enemy_flees_on_low_morale", "combat_enemy_stunned_skips_ai_intent",
        "combat_enemy_morale_victory_when_last_enemy_flees", "combat_start_bandit_encounter_from_archetype",
        "combat_generated_enemy_can_be_attacked", "combat_generated_enemy_ai_takes_turn",
        "combat_generated_encounter_victory_rewards", "combat_generated_encounter_victory_loot",
        "combat_scaling_easy_vs_hard_changes_enemy_budget", "combat_power_attack_adds_damage_bonus",
        "combat_unknown_ability_fails_safely", "combat_bleeding_slash_applies_bleeding",
        "combat_shield_bash_applies_stunned", "combat_ability_sets_cooldown",
        "combat_ability_on_cooldown_fails", "combat_ability_cooldown_ticks_down",
        "combat_enemy_brute_uses_power_attack", "combat_enemy_ability_sets_cooldown",
        "combat_enemy_does_not_use_ability_on_cooldown", "combat_enemy_stunned_does_not_use_ability",
        "combat_enemy_low_morale_flees_before_ability", "combat_companion_striker_attacks_enemy",
        "combat_companion_protector_defends_low_hp_player", "combat_player_commands_companion_attack",
        "combat_invalid_companion_command_fails_safely", "combat_downed_companion_cannot_act",
        "combat_melee_cannot_attack_far_target", "combat_reposition_moves_actor_near",
        "combat_ranged_enemy_attacks_from_backline", "combat_victory_emits_world_event_once",
        "combat_flee_emits_no_victory_world_event", "combat_bandit_victory_lowers_bandit_pressure"
    }
    bundle_g_progress = len(all_bundle_g_scenarios - (all_bundle_g_scenarios - new_names)) / len(all_bundle_g_scenarios) * 100
    print(f"Bundle G migration progress: {bundle_g_progress:.1f}% ({len(all_bundle_g_scenarios - (all_bundle_g_scenarios - new_names))}/{len(all_bundle_g_scenarios)} scenarios)")

    # Ensure no missing scenarios (migration complete)
    missing_names = all_old_names - new_names
    assert not missing_names, f"Missing scenarios: {missing_names}"

    print("Migration audit passed: All 136 scenarios present in modular registry.")


def test_manual_scenario_registry_includes_memory_l7_l9_names():
    names = set(build_service_scenarios().keys())
    missing = EXPECTED_MEMORY_L7_L9_SCENARIO_NAMES - names

    assert not missing, f"Missing L7-L9 memory scenarios: {sorted(missing)}"
